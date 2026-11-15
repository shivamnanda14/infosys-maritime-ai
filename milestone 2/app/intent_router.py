import re as _re_live
import pandas as pd
import re, math
from db import get_conn

def df_to_markdown_safe(df):
    if df is None or df.empty: return ""
    try: return df.to_markdown(index=False)
    except: pass
    headers = list(df.columns)
    lines = ["| " + " | ".join([str(h) for h in headers]) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        vals = [str(v) if v is not None else "" for v in row.values]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)

INTENT_MAP = {
    "ports": ["port", "ports", "harbor", "terminal", "congestion", "dwell"],
    "shipments": ["shipment", "shipments", "cargo", "carrier", "freight", "teu", "transit"],
    "quotes": ["quote", "spot", "price", "rate", "baf", "margin", "cost"],
    "weather": ["weather", "typhoon", "storm", "cyclone", "wind", "wave"],
    "customs": ["customs", "tariff", "duty", "hs code", "import", "export"],
    "alerts": ["alert", "incident", "delay", "disruption", "hold"]
}

def classify_intent(query):
    q = query.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(kw in q for kw in keywords):
            return intent
    return "general"

def handle_freight_intent(query):
    q_low = query.lower()
    try:
        with get_conn() as conn:
            # 1. Ports / Terminals
            if any(k in q_low for k in ["port", "ports", "harbor", "terminal", "congestion"]):
                tot_ports = conn.execute("SELECT COUNT(*) FROM ports;").fetchone()[0]
                df_ports = pd.read_sql("SELECT port_name as 'Port Name', country as 'Country', region as 'Region', congestion_index as 'Congestion (1-5)', avg_dwell_days as 'Avg Dwell Days' FROM ports ORDER BY congestion_index DESC LIMIT 5;", conn)
                return f"CRITICAL FACT: Total Monitored Ports = {tot_ports}.\n\n[Sample Subset Preview - First 5 Records Only]:\n{df_to_markdown_safe(df_ports)}", "Ports Ledger DB"

            # 2. Shipments / Cargo
            if any(k in q_low for k in ["shipment", "shipments", "carrier", "cargo"]):
                tot_shipments = conn.execute("SELECT COUNT(*) FROM shipments;").fetchone()[0]
                df_ship = pd.read_sql("SELECT shipment_id, origin_port, dest_port, carrier, status, predicted_delay_risk FROM shipments ORDER BY predicted_delay_risk DESC LIMIT 5;", conn)
                return f"CRITICAL FACT: Total Active Shipments = {tot_shipments}.\n\n[Sample Subset Preview - First 5 Records Only]:\n{df_to_markdown_safe(df_ship)}", "Shipments Ledger DB"

            # 3. Quotes / Margins
            if any(k in q_low for k in ["quote", "quotes", "spot", "margin", "price", "rate"]):
                tot_quotes = conn.execute("SELECT COUNT(*) FROM freight_quotes;").fetchone()[0]
                df_q = pd.read_sql("SELECT quote_id, shipment_id, ROUND(base_cost, 0) AS base_cost_usd, ROUND(final_price, 0) AS final_price_usd, ROUND(margin_pct, 1) AS margin_pct FROM freight_quotes ORDER BY margin_pct DESC LIMIT 5;", conn)
                return f"CRITICAL FACT: Total Active Freight Quotes = {tot_quotes}.\n\n[Sample Subset Preview - First 5 Records Only]:\n{df_to_markdown_safe(df_q)}", "Freight Quotes DB"

            # 4. Weather
            if any(k in q_low for k in ["weather", "typhoon", "storm", "wind", "wave", "cyclone", "risk", "risks"]):
                tot_weather = conn.execute("SELECT COUNT(*) FROM weather_risks;").fetchone()[0]
                df_w = pd.read_sql("SELECT port_name AS 'Port Name', current_severity AS 'Severity (1-5)', forecast AS 'Forecast', wind_speed AS 'Wind (Knots)', wave_height AS 'Wave (m)' FROM weather_risks ORDER BY current_severity DESC LIMIT 5;", conn)
                return f"CRITICAL FACT: Total Monitored Weather Risk Hubs = {tot_weather}.\n\n[Sample Subset Preview - First 5 Records Only]:\n{df_to_markdown_safe(df_w)}", "Weather Risks DB"
    except Exception:
        pass
    return None


_AGENTIC_Q = _re_live.compile(r"(need[s]? attention|what should i do|action plan|prioriti[sz]e|overall (status|health)|run (the )?agents?|full analysis|full status|why is .{0,40}(low|down|failing|underperform|risky)|what is going wrong)")
def _agentic_query(query):
    """Open-ended 'what should I do / what needs attention' questions run the whole agent graph instead of a single table lookup."""
    if not _AGENTIC_Q.search(query.lower()): return None
    try:
        from live_engine import run_cycle
        import domain_freight as _dom
        dec = run_cycle(_dom, "copilot", query)
        top = "\n".join(f"- **{a['severity']}** · {a['type']} · {a['target']}: {a['detail']}" for a in dec["actions"][:8])
        return f"### Agent orchestration result\n\n{dec['narrative']}\n\n**Top actions**\n{top}", "Agent Orchestrator (live)"
    except Exception:
        return None

def _run_centralized_orig(query):
    freight = handle_freight_intent(query)
    if freight:
        return freight

    try:
        from rag_engine import answer_with_citation
        ctx, src = answer_with_citation(query)
        return ctx, src
    except Exception:
        return f"Retrieved enterprise freight intelligence for query: '{query}'.", "General Knowledge Index"

def run_grounded_query(query):
    return run_centralized_brain_query(query)

def text_to_sql(query):
    return run_centralized_brain_query(query)

def run_centralized_brain_query(query):
    _ag = _agentic_query(query)
    return _ag if _ag else _run_centralized_orig(query)
