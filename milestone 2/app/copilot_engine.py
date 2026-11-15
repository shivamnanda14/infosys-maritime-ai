"""AI Copilot Engine for FreightQuote AI.
Whitelisted SQL queries with strict RBAC enforcement, typo tolerance,
exact database answering (no LLM/RAG hallucinations), and formatted SQL citations.
"""
import re
import sqlite3
import time
from typing import Dict, Any, List, Optional, Tuple
from db import get_conn

# Role-specific question suggestions displayed when asking outside scope or greeting
ROLE_SUGGESTIONS = {
    "Customer": [
        "What are my active shipments?",
        "Show my recent quotes",
        "Where is my cargo currently located?",
    ],
    "Admin": [
        "Which port has the highest congestion?",
        "How many shipments are on customs hold?",
        "Show quotes below 10% margin",
        "Which carrier is cheapest to Rotterdam?",
        "Show storms near the Red Sea",
    ],
    "Operations Manager": [
        "Which ports are most congested?",
        "How many shipments are on customs hold?",
        "Which shipments have a high delay risk?",
        "Show storms near the Red Sea",
        "Show active vessels progress at sea",
    ],
    "Freight Broker": [
        "Which carrier is cheapest to Rotterdam?",
        "Show quotes below 10% margin",
        "Show quotes by carrier",
        "Who are our top spending customers?",
        "Show carrier reliability rankings",
    ],
    "Auditor": [
        "How many shipments are on customs hold?",
        "Show customs rules with high duty rates",
        "Show quotes below 10% margin",
        "Which carriers have the lowest on-time percentage?",
        "What are the longest port dwell days?",
    ],
}

def get_role_suggestions(role: str) -> List[str]:
    return ROLE_SUGGESTIONS.get(role, ROLE_SUGGESTIONS["Customer"])

# -----------------------------------------------------------------------------
# Normalization & Synonym Mapping
# -----------------------------------------------------------------------------
SYNONYMS = [
    (r"\bcheepest\b", "cheapest"),
    (r"\bcheap\b", "cheapest"),
    (r"\blowest price\b", "cheapest"),
    (r"\blowest rate\b", "cheapest"),
    (r"\bcarier\b", "carrier"),
    (r"\bcarriar\b", "carrier"),
    (r"\bshipping line\b", "carrier"),
    (r"\brotterdan\b", "rotterdam"),
    (r"\broterdam\b", "rotterdam"),
    (r"\brotredam\b", "rotterdam"),
    (r"\bshanghi\b", "shanghai"),
    (r"\bshang hai\b", "shanghai"),
    (r"\bsingapor\b", "singapore"),
    (r"\bnhava\b", "nhava sheva"),
    (r"\bjnpt\b", "nhava sheva"),
    (r"\bdelyed\b", "delay"),
    (r"\bdelaied\b", "delay"),
    (r"\bdelays\b", "delayed"),
    (r"\bshipmnt\b", "shipment"),
    (r"\bshipmnts\b", "shipment"),
    (r"\bshipments\b", "shipment"),
    (r"\bcargos\b", "shipment"),
    (r"\bcargo\b", "shipment"),
    (r"\bmargn\b", "margin"),
    (r"\bmargins\b", "margin"),
    (r"\bcustom\b", "customs"),
    (r"\bcustomes\b", "customs"),
    (r"\bcostom\b", "customs"),
    (r"\brelible\b", "reliable"),
    (r"\breliablity\b", "reliability"),
    (r"\bwether\b", "weather"),
    (r"\bwheather\b", "weather"),
    (r"\bstrm\b", "storm"),
    (r"\bstorms\b", "storm"),
    (r"\bcongested\b", "congestion"),
    (r"\bconjeston\b", "congestion"),
    (r"\bvessles\b", "vessel"),
    (r"\bvessels\b", "vessel"),
    (r"\bquoat\b", "quote"),
    (r"\bqoute\b", "quote"),
    (r"\bquotes\b", "quote"),
    (r"\bquotations\b", "quote"),
    (r"\bclients\b", "customer"),
    (r"\bcustomers\b", "customer"),
    (r"\bshippers\b", "customer"),
    (r"\btariff\b", "duty"),
    (r"\bdwell time\b", "dwell days"),
]

def normalize_text(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("%", " percent ")
    t = re.sub(r"[^\w\s]", " ", t)
    for pat, rep in SYNONYMS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# -----------------------------------------------------------------------------
# Markdown Table Formatter
# -----------------------------------------------------------------------------
def format_markdown_table(headers: List[str], rows: List[Tuple]) -> str:
    if not rows:
        return "_No records found matching criteria._"
    header_str = "| " + " | ".join(str(h) for h in headers) + " |"
    sep_str = "| " + " | ".join("---" for _ in headers) + " |"
    row_strs = []
    for row in rows:
        formatted_cells = []
        for cell in row:
            if cell is None:
                formatted_cells.append("-")
            elif isinstance(cell, float):
                formatted_cells.append(f"{cell:,.2f}" if abs(cell) >= 1 else f"{cell:.1%}")
            else:
                formatted_cells.append(str(cell))
        row_strs.append("| " + " | ".join(formatted_cells) + " |")
    return "\n".join([header_str, sep_str] + row_strs)

# -----------------------------------------------------------------------------
# Parameter Extractors
# -----------------------------------------------------------------------------
def extract_dest_port(norm_q: str) -> str:
    ports = ["rotterdam", "shanghai", "singapore", "tokyo", "hamburg", "dubai", "nhava sheva", "kandla", "chennai", "los angeles", "new york", "antwerp", "busan", "santos", "mundra", "colombo"]
    for p in ports:
        if p in norm_q:
            return f"%{p}%"
    m = re.search(r"to\s+([a-z\s]+)", norm_q)
    if m:
        target = m.group(1).replace("port", "").strip()
        if target:
            return f"%{target}%"
    return "%rotterdam%"

def extract_margin_threshold(norm_q: str) -> float:
    m = re.search(r"(?:below|less than|under)\s+(\d+(?:\.\d+)?)\s*(?:percent|%)?", norm_q)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 10.0

def extract_region(norm_q: str) -> str:
    regions = ["red sea", "arabian sea", "bay of bengal", "south china sea", "mediterranean", "gulf of aden", "baltic sea", "atlantic", "pacific"]
    for r in regions:
        if r in norm_q:
            return f"%{r}%"
    m = re.search(r"(?:near|in|around)\s+([a-z\s]+)", norm_q)
    if m:
        reg = m.group(1).strip()
        if reg:
            return f"%{reg}%"
    return "%red sea%"

# -----------------------------------------------------------------------------
# Whitelisted Query Definitions (18 Core Patterns + RBAC)
# -----------------------------------------------------------------------------
QUERIES = [
    # 1. Cheapest carrier to destination
    {
        "id": "cheapest_carrier_dest",
        "pattern": re.compile(r"cheapest\s+carrier|carrier\s+is\s+cheapest|lowest\s+(?:price|rate|cost)\s+to|best\s+price\s+to", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT COALESCE(q.carrier, s.carrier) AS carrier_name, ROUND(AVG(q.final_price), 2) AS avg_price, COUNT(*) AS quote_count
FROM freight_quotes q
LEFT JOIN shipments s ON q.shipment_id = s.shipment_id
WHERE LOWER(s.dest_port) LIKE ? OR LOWER(q.quote_id) LIKE ?
GROUP BY carrier_name
ORDER BY avg_price ASC
LIMIT 5;""",
        "params": lambda q, r, cid: (extract_dest_port(q), extract_dest_port(q)),
        "headers": ["Carrier", "Avg Price ($)", "Quote Count"],
        "lead": lambda count, p: f"Here are the carriers ranked by lowest average price for destination matching '{p[0].strip('%')}':",
    },

    # 2. Shipments on Customs Hold
    {
        "id": "customs_hold",
        "pattern": re.compile(r"customs\s+hold|held\s+(?:at|by|on)\s+customs|customs\s+clearance|shipments?\s+(?:are\s+)?on\s+customs", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor"],
        "sql": """SELECT shipment_id, origin_port, dest_port, carrier, status, eta
FROM shipments
WHERE LOWER(status) LIKE '%hold%' OR LOWER(status) LIKE '%customs%'
ORDER BY shipment_id ASC
LIMIT 10;""",
        "params": lambda q, r, cid: (),
        "headers": ["Shipment ID", "Origin Port", "Destination Port", "Carrier", "Status", "ETA"],
        "lead": lambda count, p: f"There are currently {count} shipment(s) held at customs requiring documentation:",
    },

    # 3. Quotes below X% margin
    {
        "id": "low_margin_quotes",
        "pattern": re.compile(r"(?:below|under|less than)\s+\d+\s*(?:percent|%)?\s*margin|margin\s*(?:below|under|less than)|low\s+margin|unprofitable\s+quote|lowest\s+margin", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT q.quote_id, q.customer_id, q.carrier, q.final_price, q.margin_pct, q.status
FROM freight_quotes q
WHERE q.margin_pct < ?
ORDER BY q.margin_pct ASC
LIMIT 10;""",
        "params": lambda q, r, cid: (extract_margin_threshold(q),),
        "headers": ["Quote ID", "Customer ID", "Carrier", "Price ($)", "Margin (%)", "Status"],
        "lead": lambda count, p: f"Found {count} quote(s) below {p[0]:.0f}% margin threshold:",
    },

    # 4. Port congestion
    {
        "id": "port_congestion",
        "pattern": re.compile(r"port\s+congestion|congested\s+ports?|highest\s+congestion|most\s+(?:congested|congestion)", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT port_id, port_name, country, congestion_index, avg_dwell_days
FROM ports
ORDER BY congestion_index DESC
LIMIT 5;""",
        "params": lambda q, r, cid: (),
        "headers": ["Port ID", "Port Name", "Country", "Congestion Index", "Avg Dwell (Days)"],
        "lead": lambda count, p: f"Top {count} ports ranked by congestion index (scale 1.0 – 5.0):",
    },

    # 5. Storms near location / Red Sea
    {
        "id": "storms_and_cyclones",
        "pattern": re.compile(r"storms?\s+(?:near|in|around)?\s*([a-z\s]+)?|show\s+storms?|active\s+storms?|cyclones?|typhoon", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT port_name, current_severity, forecast, wind_speed, wave_height
FROM weather_risks
WHERE LOWER(port_name) LIKE ? OR LOWER(forecast) LIKE ? OR wind_speed > 35
ORDER BY wind_speed DESC
LIMIT 6;""",
        "params": lambda q, r, cid: (extract_region(q), "%storm%"),
        "headers": ["Port / Marine Zone", "Severity", "Conditions", "Wind Speed (km/h)", "Wave Height (m)"],
        "lead": lambda count, p: f"Marine storm and severe weather advisory records for '{p[0].strip('%')}':",
    },

    # 6. High delay risk shipments
    {
        "id": "high_delay_risk_shipments",
        "pattern": re.compile(r"high\s+delay\s+risk|delay\s+risk|predicted\s+delay", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT shipment_id, origin_port, dest_port, carrier, status, predicted_delay_risk
FROM shipments
WHERE predicted_delay_risk IN ('High', 'Critical') OR predicted_delay_risk >= '0.6'
ORDER BY shipment_id ASC
LIMIT 10;""",
        "params": lambda q, r, cid: (),
        "headers": ["Shipment ID", "Origin", "Destination", "Carrier", "Status", "Delay Risk"],
        "lead": lambda count, p: f"Identified {count} shipment(s) with elevated delay risk prediction:",
    },

    # 7. Delayed shipments count
    {
        "id": "delayed_shipments_count",
        "pattern": re.compile(r"how\s+many\s+shipments?\s+(?:are\s+)?delayed|delayed\s+shipments?\s+count|delayed\s+shipments?", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT status, COUNT(*) AS shipment_count
FROM shipments
WHERE LOWER(status) LIKE '%delay%' OR LOWER(status) LIKE '%hold%'
GROUP BY status;""",
        "params": lambda q, r, cid: (),
        "headers": ["Status Classification", "Shipment Count"],
        "lead": lambda count, p: f"Current shipment delay summary across the network:",
    },

    # 8. Carrier reliability & on-time performance
    {
        "id": "carrier_reliability",
        "pattern": re.compile(r"carrier\s+reliability|on\s+time\s+pct|on\s+time\s+percentage|carrier\s+performance|most\s+reliable\s+carrier|lowest\s+on\s+time", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Freight Broker", "Auditor"],
        "sql": """SELECT name, rating, on_time_pct, avg_cost_index, risk_level
FROM carriers
ORDER BY on_time_pct DESC
LIMIT 8;""",
        "params": lambda q, r, cid: (),
        "headers": ["Carrier Name", "Rating", "On-Time %", "Cost Index", "Risk Level"],
        "lead": lambda count, p: f"Carrier performance ranked by on-time delivery percentage:",
    },

    # 9. Customer active shipments (Customer-scoped)
    {
        "id": "customer_active_shipments",
        "pattern": re.compile(r"my\s+active\s+shipments?|my\s+shipments?|active\s+shipments?|where\s+is\s+my\s+cargo", re.I),
        "allowed_roles": ["Customer", "Admin", "Freight Broker"],
        "sql": """SELECT q.shipment_id, s.origin_port, s.dest_port, s.carrier, s.status, s.eta
FROM freight_quotes q
JOIN shipments s ON q.shipment_id = s.shipment_id
WHERE q.customer_id = ?
ORDER BY s.eta ASC
LIMIT 10;""",
        "params": lambda q, r, cid: (cid or "CUST-001",),
        "headers": ["Shipment ID", "Origin Port", "Destination Port", "Carrier", "Status", "ETA"],
        "lead": lambda count, p: f"Active shipment tracking for your account ({p[0]}):",
    },

    # 10. Customer recent quotes (Customer-scoped)
    {
        "id": "customer_quotes",
        "pattern": re.compile(r"my\s+recent\s+quotes?|my\s+quotes?|recent\s+quotes?|show\s+my\s+quotes?", re.I),
        "allowed_roles": ["Customer", "Admin", "Freight Broker"],
        "sql": """SELECT quote_id, carrier, final_price, margin_pct, status, created_at
FROM freight_quotes
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 10;""",
        "params": lambda q, r, cid: (cid or "CUST-001",),
        "headers": ["Quote ID", "Carrier", "Price ($)", "Margin (%)", "Status", "Created At"],
        "lead": lambda count, p: f"Recent spot freight quotes for your account ({p[0]}):",
    },

    # 11. Top spending customers
    {
        "id": "top_spending_customers",
        "pattern": re.compile(r"top\s+(?:spending\s+)?customers?|highest\s+spending\s+customers?|top\s+clients?|biggest\s+customers?", re.I),
        "allowed_roles": ["Admin", "Freight Broker", "Auditor"],
        "sql": """SELECT c.name, c.industry, c.priority_tier, COUNT(q.quote_id) AS total_quotes, ROUND(SUM(q.final_price), 2) AS total_spend
FROM customers c
JOIN freight_quotes q ON c.customer_id = q.customer_id
GROUP BY c.customer_id
ORDER BY total_spend DESC
LIMIT 5;""",
        "params": lambda q, r, cid: (),
        "headers": ["Customer Name", "Industry", "Priority Tier", "Total Quotes", "Total Spend ($)"],
        "lead": lambda count, p: f"Top customer accounts by aggregate quote volume:",
    },

    # 12. Customs rules & duty rates
    {
        "id": "high_duty_customs",
        "pattern": re.compile(r"customs\s+rules|high\s+duty|highest\s+duty|tariff\s+rates?|duty\s+rates?", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor", "Freight Broker"],
        "sql": """SELECT chapter, goods, duty_pct, docs
FROM customs_rules
ORDER BY duty_pct DESC
LIMIT 6;""",
        "params": lambda q, r, cid: (),
        "headers": ["HS Chapter", "Commodity Goods", "Standard Duty (%)", "Required Documents"],
        "lead": lambda count, p: f"Customs tariff schedule ranked by standard duty percentage:",
    },

    # 13. Active vessels progress at sea
    {
        "id": "active_vessels_progress",
        "pattern": re.compile(r"vessels?\s+progress|fleet\s+progress|vessels?\s+at\s+sea|active\s+vessels?", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor"],
        "sql": """SELECT shipment_id, route_name, ROUND(progress * 100, 1) AS progress_pct, lat, lon
FROM vessels
ORDER BY progress DESC
LIMIT 8;""",
        "params": lambda q, r, cid: (),
        "headers": ["Shipment ID", "Voyage Route", "Progress (%)", "Latitude", "Longitude"],
        "lead": lambda count, p: f"Current positions and voyage completion for active vessels:",
    },

    # 14. Quotes by carrier
    {
        "id": "quotes_by_carrier",
        "pattern": re.compile(r"quotes?\s+by\s+carrier|quotes?\s+for\s+carrier|carrier\s+quotes?", re.I),
        "allowed_roles": ["Admin", "Freight Broker", "Operations Manager", "Auditor"],
        "sql": """SELECT carrier, COUNT(*) AS quote_count, ROUND(AVG(final_price), 2) AS avg_price, ROUND(AVG(margin_pct), 1) AS avg_margin
FROM freight_quotes
GROUP BY carrier
ORDER BY quote_count DESC;""",
        "params": lambda q, r, cid: (),
        "headers": ["Carrier", "Quote Count", "Avg Price ($)", "Avg Margin (%)"],
        "lead": lambda count, p: f"Spot quote breakdown and pricing performance by carrier:",
    },

    # 15. Shipments by origin port
    {
        "id": "shipments_by_origin",
        "pattern": re.compile(r"shipments?\s+(?:from|origin|by\s+origin)|origin\s+port\s+shipments?|cargo\s+from", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor"],
        "sql": """SELECT origin_port, COUNT(*) AS total_shipments, carrier, status
FROM shipments
GROUP BY origin_port
ORDER BY total_shipments DESC
LIMIT 6;""",
        "params": lambda q, r, cid: (),
        "headers": ["Origin Port", "Total Shipments", "Primary Carrier", "Status"],
        "lead": lambda count, p: f"Active cargo outbound volume by origin port:",
    },

    # 16. Port dwell days
    {
        "id": "port_dwell_days",
        "pattern": re.compile(r"dwell\s+days?|dwell\s+time|longest\s+dwell|port\s+dwell", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor", "Freight Broker"],
        "sql": """SELECT port_name, country, avg_dwell_days, congestion_index
FROM ports
ORDER BY avg_dwell_days DESC
LIMIT 6;""",
        "params": lambda q, r, cid: (),
        "headers": ["Port Name", "Country", "Avg Dwell (Days)", "Congestion Index"],
        "lead": lambda count, p: f"Ports ranked by average container dwell turnaround time:",
    },

    # 17. Severe weather risks & winds
    {
        "id": "severe_weather_risks",
        "pattern": re.compile(r"weather\s+risks?|severe\s+weather|high\s+wind|wave\s+heights?|port\s+weather", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor"],
        "sql": """SELECT port_name, current_severity, forecast, wind_speed, wave_height
FROM weather_risks
ORDER BY wind_speed DESC
LIMIT 6;""",
        "params": lambda q, r, cid: (),
        "headers": ["Port Name", "Severity", "Forecast Conditions", "Wind Speed (km/h)", "Wave Height (m)"],
        "lead": lambda count, p: f"Ports currently reporting highest wind speed and adverse weather:",
    },

    # 18. Fleet health & decision status
    {
        "id": "fleet_health_decision",
        "pattern": re.compile(r"fleet\s+health|health\s+score|system\s+health|decision\s+status|current\s+health", re.I),
        "allowed_roles": ["Admin", "Operations Manager", "Auditor", "Freight Broker"],
        "sql": """SELECT decision_id, score, risk, narrative, ts
FROM decisions
ORDER BY decision_id DESC
LIMIT 1;""",
        "params": lambda q, r, cid: (),
        "headers": ["Decision ID", "Health Score", "Risk Tier", "Operational Narrative", "Timestamp"],
        "lead": lambda count, p: f"Latest autonomous fleet health evaluation:",
    },
]

# -----------------------------------------------------------------------------
# Main Copilot Query Dispatcher
# -----------------------------------------------------------------------------
def ask_copilot(raw_query: str, user_role: str, customer_id: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.time()
    q = (raw_query or "").strip()
    norm_q = normalize_text(q)

    # 1. Greetings check
    if re.search(r"^(?:hi|hello|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening)\b", norm_q):
        suggs = get_role_suggestions(user_role)
        bullets = "\n".join(f"- *\"{s}\"*" for s in suggs)
        return {
            "status": "greeting",
            "text": f"Hello! I am your FreightQuote Copilot. I answer questions directly from our database.\n\nHere are some questions you can ask:\n{bullets}",
            "sql": "",
            "row_count": 0,
            "ms": round((time.time() - t0) * 1000),
        }

    # 2. Match whitelisted query pattern
    matched_entry = None
    for entry in QUERIES:
        if entry["pattern"].search(norm_q):
            matched_entry = entry
            break

    # 3. Handle unmapped / out-of-scope query
    if not matched_entry:
        suggs = get_role_suggestions(user_role)
        bullets = "\n".join(f"- *\"{s}\"*" for s in suggs)
        return {
            "status": "out_of_scope",
            "text": f"I can only answer questions based on verified database records (routes, quotes, carriers, weather, margins, customs).\n\nHere are three valid questions for your role:\n{bullets}",
            "sql": "",
            "row_count": 0,
            "ms": round((time.time() - t0) * 1000),
        }

    # 4. Strict RBAC validation
    if user_role not in matched_entry["allowed_roles"]:
        return {
            "status": "forbidden",
            "text": f"Access Restricted: Your role ({user_role}) does not have permission to query '{matched_entry['id'].replace('_', ' ')}'. Please refer to authorized modules in your navigation.",
            "sql": "",
            "row_count": 0,
            "ms": round((time.time() - t0) * 1000),
        }

    # 5. Customer scoping
    if user_role == "Customer":
        if matched_entry["id"] not in ("customer_active_shipments", "customer_quotes"):
            return {
                "status": "forbidden",
                "text": "Customer accounts may only query active shipments and spot quotes belonging to their registered customer ID.",
                "sql": "",
                "row_count": 0,
                "ms": round((time.time() - t0) * 1000),
            }

    # 6. Execute parameterized query against SQLite
    sql = matched_entry["sql"]
    params = matched_entry["params"](norm_q, user_role, customer_id)

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        row_count = len(rows)

        headers = matched_entry["headers"]
        table_md = format_markdown_table(headers, rows)
        lead_text = matched_entry["lead"](row_count, params)

        # Build clean SQL citation text with substituted literal parameters for inspection
        display_sql = sql
        for p in params:
            val_repr = f"'{p}'" if isinstance(p, str) else str(p)
            display_sql = display_sql.replace("?", val_repr, 1)

        result_text = f"{lead_text}\n\n{table_md}"
        return {
            "status": "success",
            "text": result_text,
            "sql": display_sql.strip(),
            "row_count": row_count,
            "ms": round((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "status": "error",
            "text": f"Database query failed: {str(e)}",
            "sql": sql.strip(),
            "row_count": 0,
            "ms": round((time.time() - t0) * 1000),
        }
