"""FreightQuote AI live domain (PRS v3): 7 agents, ML pricing + congestion models, vessel tracking, reroute loop, PDF documents."""
import sys, os, re, json, math, random, time, datetime, zlib
import numpy as np, pandas as pd, requests
from live_engine import AgentResult, risk_label, conn, now, _DB_LOCK, set_state, get_state, emit, run_cycle, _log_run, act, init_live_tables
from config import DB_PATH
KIND = "Freight"; NAME = "FreightQuote AI"; ENTITY_COL = "shipment_id"; SMS = False; ESCALATE_TO = "Operations Manager"
OWNER = {"quote_anomaly": "Finance Lead", "reroute": "Operations Manager", "quote_approval": "Admin", "customs_docs": "Customs Officer", "congestion_notice": "Operations Manager", "margin_review": "Finance Lead", "quote_hold": "Freight Broker"}
ACTION_AGENT = {"quote_anomaly": "anomaly_watch", "reroute": "weather_watch", "customs_docs": "customs_watch", "congestion_notice": "route_watch", "quote_approval": "quote_watch", "margin_review": "quote_watch", "quote_hold": "quote_watch"}
DATA_DIR = os.path.dirname(DB_PATH); TICK_NM = 84.0       # 1 tick = 1 sailing hour
CARGO = {"Electronics": 1.15, "Pharmaceuticals": 1.35, "Automotive Parts": 1.1, "Textiles": .95, "Heavy Machinery": 1.3, "Perishables": 1.4, "General": 1.0, "Hazardous": 1.6, "Bulk": .8}
CODES = {k: i for i, k in enumerate(CARGO)}
def Q(sql, p=()):
    with _DB_LOCK, conn() as c: return pd.read_sql(sql, c, params=p)

# ---------------------------------------------------------------- geo + routing
def nm(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1])); h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3440.065 * 2 * math.asin(min(1, math.sqrt(h)))
def chain_nm(ch): return sum(nm(ch[i], ch[i + 1]) for i in range(len(ch) - 1))
def interp(ch, frac):
    legs = [nm(ch[i], ch[i + 1]) for i in range(len(ch) - 1)]; tot = sum(legs) or 1; d = min(max(frac, 0), 1) * tot
    for i, L in enumerate(legs):
        if d <= L or i == len(legs) - 1:
            t = d / L if L else 0; return (ch[i][0] + (ch[i + 1][0] - ch[i][0]) * t, ch[i][1] + (ch[i + 1][1] - ch[i][1]) * t)
        d -= L
SUEZ_S, SUEZ_N, CAPE = (12.6, 43.4), (30.0, 32.55), (-34.4, 18.5)
_ACC = {}
def _access(xy):
    """Sea entry point for river / bay ports (Hamburg, Wuhan, Houston ...), looked up by the port's coordinates."""
    if not _ACC:
        try:
            import seanav
            for n, la, lo in Q("SELECT port_name, lat, lon FROM ports").itertuples(index=False): _ACC[(round(float(la), 2), round(float(lo), 2))] = seanav.access_for(n)
        except Exception: _ACC[None] = None
    return _ACC.get((round(float(xy[0]), 2), round(float(xy[1]), 2)))
def best_route(o, d):
    import seanav
    r = seanav.sea().route((float(o[0]), float(o[1])), (float(d[0]), float(d[1])), (), (), _access(o), _access(d))
    return {"name": "via " + " + ".join(r["via"]) if r["via"] else "direct sea route", "chain": r["pts"], "nm": round(r["nm"]), "via": r["via"]}
def route_options(o, d, avoid=()):
    """Real sea routes (water only: see seanav.py). avoid may contain 'suez', 'panama', 'malacca', 'hormuz', 'bosphorus' and/or 'storm' (steer around the active storms)."""
    import seanav
    S = seanav.sea(); blocked = tuple(a for a in avoid if a in seanav.BLOCK_GROUPS); st = tuple((s["lat"], s["lon"], s.get("r", 700)) for s in storms()) if "storm" in avoid else ()
    opts = S.options((float(o[0]), float(o[1])), (float(d[0]), float(d[1])), blocked, st, _access(o), _access(d))
    if not opts and st: opts = S.options((float(o[0]), float(o[1])), (float(d[0]), float(d[1])), blocked, (), _access(o), _access(d))
    return [{"name": x["name"], "chain": x["pts"], "nm": round(x["nm"]), "via": x["via"]} for x in opts]
def port_xy(name):
    r = Q("SELECT lat, lon, congestion_index ci, avg_dwell_days dw, country FROM ports WHERE port_name=? LIMIT 1", (name,))
    return (float(r.lat[0]), float(r.lon[0]), float(r.ci[0]), float(r.dw[0]), r.country[0]) if len(r) else None

# ---------------------------------------------------------------- weather (Open-Meteo live + cached port rows + simulated storms)
_WX = {}; _OFF = [0.0]
def storms(): return get_state("storms", []) or []
def inject_storm(lat=None, lon=None, wind=22.0):
    s = storms(); s.append({"lat": lat if lat is not None else random.uniform(-30, 45), "lon": lon if lon is not None else random.uniform(-60, 120), "r": 700, "wind": wind, "ts": now()}); set_state("storms", s[-6:])
def weather_at(lat, lon, allow_live=True):
    k = (round(lat / 2) * 2, round(lon / 2) * 2); hit = _WX.get(k); wind, wave, src = 6.0, 1.2, "cached"
    if hit and time.time() - hit[0] < 900: wind, wave, src = hit[1:]
    elif allow_live and time.time() > _OFF[0]:
        try:
            r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=wind_speed_10m&wind_speed_unit=ms", timeout=3).json()["current"]
            wind, src = float(r["wind_speed_10m"]), "Open-Meteo live"
            try: wave = float(requests.get(f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&current=wave_height", timeout=3).json()["current"]["wave_height"] or 1.2)
            except Exception: wave = 1.2
            _WX[k] = (time.time(), wind, wave, src)
        except Exception: _OFF[0] = time.time() + 120; wind, src = 5 + 4 * random.random(), "simulated (offline)"
    else: wind, src = 5 + 4 * random.random(), "simulated (offline)"
    for s in storms():
        d = nm((lat, lon), (s["lat"], s["lon"]))
        if d < s["r"]: wind = max(wind, s["wind"] * (1 - .5 * d / s["r"])); src += " + storm"
    return {"wind": round(wind, 1), "wave": round(wave, 1), "src": src, "level": "High" if wind > 15 else "Medium" if wind >= 8 else "Low"}
def wscore(level): return {"High": 1.0, "Medium": .5, "Low": .12}[level]

# ---------------------------------------------------------------- ML models
def _gen_rates(n=4000):
    R = np.random.default_rng(42); dist = R.uniform(500, 12000, n); w = R.uniform(1, 600, n); cg = R.integers(0, len(CARGO), n); cong = R.integers(0, 4, n); mult = np.array(list(CARGO.values()))
    cost = (250 + .21 * dist) * (.6 + .012 * w) * (1 + .08 * cong) * mult[cg] * R.normal(1, .06, n)
    return pd.DataFrame({"distance_nm": dist, "cargo_weight": w, "cargo_type": cg, "congestion_level": cong, "freight_cost_usd": cost})
_ML = {}
def pricing_model():
    from sklearn.ensemble import RandomForestRegressor; from sklearn.model_selection import train_test_split; from sklearn.metrics import r2_score, mean_squared_error; import joblib
    path = os.path.join(DATA_DIR, "pricing_rf.joblib")
    if "rf" in _ML: return _ML
    if os.path.exists(path): _ML.update(joblib.load(path)); return _ML
    src = "bootstrap synthetic (feed a Kaggle freight-rate CSV to replace)"
    try:
        d = Q("SELECT * FROM freight_rates")
        if len(d) >= 300: src = "fed dataset (freight_rates table)"
        else: d = _gen_rates()
    except Exception: d = _gen_rates()
    X, y = d[["distance_nm", "cargo_weight", "cargo_type", "congestion_level"]], d.freight_cost_usd
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.2, random_state=42); rf = RandomForestRegressor(100, random_state=42, n_jobs=-1).fit(Xtr, ytr)
    m = {"r2": round(r2_score(yte, rf.predict(Xte)), 3), "rmse": round(float(np.sqrt(mean_squared_error(yte, rf.predict(Xte)))), 1), "source": src, "importance": dict(zip(X.columns, rf.feature_importances_.round(3).tolist()))}
    _ML.update(rf=rf, metrics=m); joblib.dump({"rf": rf, "metrics": m}, path)
    with _DB_LOCK, conn() as c: c.execute("UPDATE ml_models SET is_active=0 WHERE model_name='rf_freight_price'"); c.execute("INSERT INTO ml_models(model_name,metrics,trained_at,is_active) VALUES(?,?,?,1)", ("rf_freight_price", json.dumps(m), now()))
    return _ML
def congestion_model():
    from sklearn.ensemble import RandomForestClassifier
    if "cg" in _ML: return _ML["cg"]
    R = np.random.default_rng(3); n = 3000; ci = R.uniform(1, 4.8, n); dw = R.uniform(1.5, 7, n); mo = R.integers(1, 13, n); dow = R.integers(0, 7, n); cg = R.integers(0, len(CARGO), n)
    lvl = np.clip(np.round((ci - 1) / 1.3 + .25 * (dw > 5) + .35 * np.isin(mo, [10, 11, 12, 1, 2]) + R.normal(0, .3, n)), 0, 3).astype(int)
    clf = RandomForestClassifier(100, random_state=42).fit(np.c_[ci, dw, mo, dow, cg], lvl); _ML["cg"] = clf; return clf
def predict_congestion(ci, dw, cargo="General"):
    t = datetime.date.today(); return int(congestion_model().predict([[ci, dw, t.month, t.weekday(), CODES.get(cargo, 6)]])[0])

# ---------------------------------------------------------------- bootstrap, simulator, vessel tracking
def bootstrap():
    from scale_data import scale_freight; scale_freight()
    with _DB_LOCK, conn() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS quote_requests(req_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, origin TEXT, dest TEXT, cargo TEXT, weight_t REAL, hs_code TEXT, customer_id TEXT, language TEXT, status TEXT DEFAULT 'new', quote_id TEXT, result TEXT, docs_provided TEXT);
        CREATE TABLE IF NOT EXISTS shipment_docs(ref TEXT, doc TEXT, ts TEXT, by TEXT, UNIQUE(ref, doc));
        CREATE TABLE IF NOT EXISTS vessels(shipment_id TEXT PRIMARY KEY, lat REAL, lon REAL, progress REAL, chain TEXT, route_name TEXT, speed_kn REAL, updated TEXT);
        CREATE TABLE IF NOT EXISTS ml_models(model_id INTEGER PRIMARY KEY AUTOINCREMENT, model_name TEXT, metrics TEXT, trained_at TEXT, is_active INT);
        CREATE TABLE IF NOT EXISTS customs_rules(chapter TEXT PRIMARY KEY, goods TEXT, duty_pct REAL, docs TEXT, restricted INT);""")
        try: c.execute("ALTER TABLE quote_requests ADD COLUMN docs_provided TEXT")
        except Exception: pass
        if not c.execute("SELECT 1 FROM customs_rules").fetchone():
            base = "Commercial Invoice;Packing List;Bill of Lading"
            for ch, g, d, ex, rs in [("30", "Pharmaceuticals", 5, "Import License;Drug Control Certificate", 1), ("84", "Machinery", 7.5, "Certificate of Origin", 0), ("85", "Electronics", 10, "BIS Certificate;Certificate of Origin", 0), ("87", "Vehicles and parts", 15, "Homologation Certificate", 0),
                                     ("10", "Cereals", 12, "Phytosanitary Certificate", 0), ("62", "Apparel", 12, "Certificate of Origin", 0), ("27", "Mineral fuels", 5, "Hazmat Declaration;IMDG Certificate", 1), ("39", "Plastics", 8, "Certificate of Origin", 0), ("72", "Iron and steel", 7.5, "Mill Test Certificate", 0), ("22", "Beverages", 20, "Excise Permit", 1)]:
                c.execute("INSERT INTO customs_rules VALUES(?,?,?,?,?)", (ch, g, d, base + ";" + ex, rs))
        n = c.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]
        if n == 0:
            R = random.Random(5)
            for sid, o, d in c.execute("SELECT shipment_id, origin_port, dest_port FROM shipments WHERE status IN ('In Transit','Port Congestion Delay','Anchorage Pending')").fetchall():
                po, pd_ = port_xy(o), port_xy(d)
                if not po or not pd_: continue
                opt = best_route(po[:2], pd_[:2]); p = R.uniform(.05, .9); la, lo = interp(opt["chain"], p)
                c.execute("INSERT OR REPLACE INTO vessels VALUES(?,?,?,?,?,?,?,?)", (sid, la, lo, p, json.dumps(opt["chain"]), opt["name"], R.uniform(12, 17), now()))
    pricing_model(); congestion_model()

def tick():
    reasons = []; R = random
    with _DB_LOCK, conn() as c:
        real = set()
        for sid, p, chain, spd in c.execute("SELECT shipment_id, progress, chain, speed_kn FROM vessels").fetchall():
            if sid in real: continue
            ch = json.loads(chain); tot = chain_nm(ch) or 1; p2 = p + spd * 1.0 / tot
            if p2 >= 1:
                c.execute("DELETE FROM vessels WHERE shipment_id=?", (sid,)); c.execute("UPDATE shipments SET status='Delivered' WHERE shipment_id=?", (sid,)); emit("delivered", sid); continue
            la, lo = interp(ch, p2); c.execute("UPDATE vessels SET lat=?, lon=?, progress=?, updated=? WHERE shipment_id=?", (la, lo, p2, now(), sid))
        _tickn = get_state("tickn", 0) + 1; set_state("tickn", _tickn)
        ports = c.execute("SELECT port_name, lat, lon FROM ports ORDER BY port_id").fetchall()
        try: import weather as _WXL; _fresh = _WXL.fresh_ports()
        except Exception: _fresh = set()
        for i in range(12):                                         # round-robin refresh of port weather + congestion drift
            nme, la, lo = ports[(_tickn * 12 + i) % len(ports)]; w = weather_at(la, lo, allow_live=False)
            if nme in _fresh:                                       # real Open-Meteo reading is recent: keep it, only drift congestion
                c.execute("UPDATE ports SET congestion_index=MIN(5,MAX(0.5,congestion_index+?)) WHERE port_name=?", (R.uniform(-.12, .12), nme)); continue
            c.execute("INSERT OR REPLACE INTO weather_risks(port_name,current_severity,forecast,wind_speed,wave_height,temperature) VALUES(?,?,?,?,?,?)", (nme, w["level"], w["src"], w["wind"] * 3.6, w["wave"], 24.0))
            c.execute("UPDATE ports SET congestion_index=MIN(5,MAX(0.5,congestion_index+?)) WHERE port_name=?", (R.uniform(-.12, .12), nme))
        for _ in range(max(0, min(4, 230 - c.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]))):   # keep the tracked fleet topped up as ships arrive
            o, d = R.sample(ports, 2); sid = f"SHP-L{R.randint(0, 10**8):08d}"; opt = best_route((o[1], o[2]), (d[1], d[2]))
            c.execute("INSERT OR REPLACE INTO shipments(shipment_id,origin_port,dest_port,carrier,status,eta,weight_kg,hs_code,predicted_delay_risk) VALUES(?,?,?,?,?,?,?,?,?)", (sid, o[0], d[0], R.choice([r[0] for r in c.execute("SELECT name FROM carriers").fetchall()]), "In Transit", (datetime.date.today() + datetime.timedelta(days=20)).isoformat(), R.uniform(2000, 25000), f"HS-{R.choice([30,84,85,87,10,62])}{R.randint(10,99)}", .1))
            c.execute("INSERT OR REPLACE INTO vessels VALUES(?,?,?,?,?,?,?,?)", (sid, o[1], o[2], R.uniform(0, .05), json.dumps(opt["chain"]), opt["name"], R.uniform(12, 17), now()))
        if _tickn % 6 == 0 and R.random() < .6:                      # incoming customer quote request
            o, d = R.sample(ports, 2); cu = c.execute("SELECT customer_id FROM customers ORDER BY RANDOM() LIMIT 1").fetchone()[0]
            hs = f"HS-{R.choice([30,84,85,87,10,62,27])}{R.randint(10,99)}"; req_docs = _required_docs(hs)[1]; given = [x for x in req_docs if R.random() < (.97 if x in ("Commercial Invoice", "Packing List", "Bill of Lading") else .82)]
            c.execute("INSERT INTO quote_requests(ts,origin,dest,cargo,weight_t,hs_code,customer_id,language,docs_provided) VALUES(?,?,?,?,?,?,?,?,?)", (now(), o[0], d[0], R.choice(list(CARGO)), round(R.uniform(5, 450), 1), hs, cu, "English", ";".join(given))); reasons.append("quote-request")
        if _tickn % 40 == 0 and R.random() < .5: inject_storm(); reasons.append("storm")
        if _tickn % 25 == 0: set_state("storms", [s for s in storms() if (time.time() % 1e9) > 0][-3:])
    return reasons

def feed():
    with _DB_LOCK, conn() as c: ports = c.execute("SELECT port_name, lat, lon FROM ports ORDER BY port_id").fetchall()
    k = get_state("feedk", 0) or 0
    for i in range(10): _, la, lo = ports[(k * 10 + i) % len(ports)]; weather_at(la, lo, allow_live=True)
    set_state("feedk", k + 1)
DEFAULT_POLICY = {"reroute": "approval"}
def process():
    for r in Q("SELECT req_id FROM quote_requests WHERE status='new' ORDER BY req_id LIMIT 3").req_id.tolist(): run_quote(int(r))

# ---------------------------------------------------------------- the 7 pipeline agents
def route_agent(s):
    req = s["req"]; po, pd_ = port_xy(req["origin"]), port_xy(req["dest"])
    if not po or not pd_: raise ValueError("unknown port")
    opts = route_options(po[:2], pd_[:2], s.get("avoid", ())); best = opts[0]
    cong = predict_congestion((po[2] + pd_[2]) / 2, (po[3] + pd_[3]) / 2, req["cargo"]); days = best["nm"] / (14 * 24) + po[3] * .5 + pd_[3] * .5
    cars = Q("SELECT name, rating, on_time_pct, avg_cost_index, risk_level FROM carriers"); cars["score"] = cars.rating / 5 * 40 + cars.on_time_pct * .4 - cars.avg_cost_index * 12 - (cars.risk_level == "High") * 8
    top = cars.sort_values("score", ascending=False).head(3)
    return AgentResult("route", 100 - cong * 20, risk_label(100 - cong * 20), f"{best['name']}, {best['nm']:,} nm, {days:.1f} days, congestion level {cong}/3 (ML)",
        {"route": best["name"], "chain": best["chain"], "distance_nm": best["nm"], "transit_days": round(days, 1), "congestion": cong, "alternatives": [o["name"] for o in opts[1:]], "carriers": top.name.tolist(), "ports": [po[:2], pd_[:2]]})
def weather_agent(s):
    r = s["results"]["route"].findings; ch = r["chain"]; pts = [interp(ch, f) for f in (0, .25, .5, .75, 1)]; ws = [weather_at(la, lo) for la, lo in pts]; worst = max(ws, key=lambda w: w["wind"])
    sc = max(wscore(w["level"]) for w in ws); delay = round(min(.95, sc * .6 + worst["wind"] / 60), 2)
    return AgentResult("weather", 100 - sc * 100, risk_label(100 - sc * 100), f"{worst['level']} risk: wind {worst['wind']} m/s, waves {worst['wave']} m ({worst['src']}), delay probability {delay}", {"level": worst["level"], "wind": worst["wind"], "wave": worst["wave"], "risk": sc, "delay_prob": delay, "src": worst["src"]})
def pricing_agent(s):
    m = pricing_model(); rt = s["results"]["route"].findings; req = s["req"]
    ml = float(m["rf"].predict(pd.DataFrame([[rt["distance_nm"], req["weight_t"], CODES.get(req["cargo"], 6), rt["congestion"]]], columns=["distance_nm", "cargo_weight", "cargo_type", "congestion_level"]))[0])
    fuel = ml * float(get_state("fuel_pct", .12) or .12); fees = 350 + 40 * rt["congestion"] * 2
    return AgentResult("pricing", 90, "Low", f"ML base ${ml:,.0f} (R2 {m['metrics']['r2']}), fuel 12% ${fuel:,.0f}, port fees ${fees:,.0f}", {"base": round(ml, 2), "fuel": round(fuel, 2), "port_fees": fees, "model": m["metrics"]})
def _required_docs(hs):
    ch = (re.findall(r"\d+", str(hs)) or ["00"])[0][:2]; r = Q("SELECT * FROM customs_rules WHERE chapter=?", (ch,))
    base = ["Commercial Invoice", "Packing List", "Bill of Lading"]
    return ch, (r.docs[0].split(";") if len(r) else base), (int(r.restricted[0]) if len(r) else 0), (float(r.duty_pct[0]) if len(r) else 10.0), (r.goods[0] if len(r) else "General cargo")
def _attached(ref):
    try: return set(Q("SELECT doc FROM shipment_docs WHERE ref=?", (ref,)).doc)
    except Exception: return set()
def customs_agent(s):
    """Customs check against the customs_rules table: duty, restricted goods, and which required documents the customer actually provided or attached later."""
    req = s["req"]; ch, docs, restricted, duty, goods = _required_docs(req["hs_code"]); prov = req.get("docs_provided")
    have = set(str(prov).split(";")) if isinstance(prov, str) and prov else set(docs)                # legacy requests without a document list count as complete
    have |= _attached(s.get("quote_id", "")); missing = [d for d in docs if d not in have]
    risk = round(min(1, .12 + .35 * restricted + .18 * len(missing)), 2)
    return AgentResult("customs", 100 - risk * 100, risk_label(100 - risk * 100), f"Chapter {ch} ({goods}): {'restricted, ' if restricted else ''}{len(missing)} document(s) missing, duty {duty}%", {"risk": risk, "docs": docs, "missing": missing, "duty_pct": duty, "restricted": bool(restricted), "status": "Hold" if len(missing) or risk > .6 else "Ready", "goods": goods})
def margin_agent(s):
    p = s["results"]["pricing"].findings; cust = Q("SELECT priority_tier t, credit_risk cr FROM customers WHERE customer_id=?", (s["req"]["customer_id"],)); tier = cust.t[0] if len(cust) else "Silver"; cr = float(cust.cr[0]) if len(cust) else .1
    target = .20 + {"Platinum": -.02, "Gold": 0, "Silver": .02, "Bronze": .04}.get(tier, .02) + (.02 if cr > .3 else 0)
    cost = p["base"] + p["fuel"] + p["port_fees"]; op = p["base"] * .15; duty = p["base"] * s["results"]["customs"].findings["duty_pct"] / 100 * .1; total_cost = cost + op + duty
    price = total_cost / (1 - target); margin = (price - total_cost) / price * 100
    return AgentResult("margin", min(100, margin * 4), "Low" if margin >= 10 else "High", f"Target {target*100:.0f}% ({tier}), price ${price:,.0f}, margin {margin:.1f}%", {"price": round(price, 2), "margin_pct": round(margin, 1), "op_cost": round(op, 2), "target": target, "tier": tier, "cost": round(total_cost, 2)})
def document_agent(s):
    q = s["quote_id"]; out = os.path.join(DATA_DIR, "docs"); os.makedirs(out, exist_ok=True); req = s["req"]; rt = s["results"]["route"].findings; paths = []
    try:
        from reportlab.lib.pagesizes import A4; from reportlab.pdfgen import canvas
        for kind, lines in (("BillOfLading", [f"Shipper/Customer: {req['customer_id']}", f"Port of loading: {req['origin']}", f"Port of discharge: {req['dest']}", f"Cargo: {req['cargo']} ({req['hs_code']}), {req['weight_t']} t", f"Carrier: {rt['carriers'][0]}", f"Route: {rt['route']}, {rt['distance_nm']:,} nm"]),
                            ("PackingList", [f"Quote: {q}", f"Cargo type: {req['cargo']}", f"Gross weight: {req['weight_t']} t", f"Documents: {', '.join(s['results']['customs'].findings['docs'])}"])):
            p = os.path.join(out, f"{q}_{kind}.pdf"); cv = canvas.Canvas(p, pagesize=A4); cv.setFont("Helvetica-Bold", 16); cv.drawString(50, 800, f"{kind} - {q}"); cv.setFont("Helvetica", 11)
            for i, ln in enumerate(lines): cv.drawString(50, 770 - 22 * i, ln)
            cv.save(); paths.append(p)
    except Exception as e: return AgentResult("document", 60, "Medium", f"PDF generation unavailable: {e}")
    return AgentResult("document", 100, "Low", f"{len(paths)} PDFs generated", {"paths": paths})
def alert_agent(s):
    val = s["results"]["margin"].findings["price"]; w = s["results"]["weather"].findings; acts = []
    if val > 50000: acts.append({"type": "quote_approval", "target": s["quote_id"], "detail": f"Quote ${val:,.0f} exceeds $50,000: admin approval required", "severity": "Critical", "owner": "Admin"})
    elif s["results"]["margin"].findings["margin_pct"] < 10: acts.append({"type": "margin_review", "target": s["quote_id"], "detail": "Margin below 10%", "severity": "Warning"})
    if w["level"] == "High": acts.append({"type": "reroute", "target": s["quote_id"], "detail": f"High weather risk on lane (wind {w['wind']} m/s)", "severity": "Warning"})
    return AgentResult("alert", 100, "Low", f"{len(acts)} alerts raised", {}, acts)

def _compute(req, qid, cid=None, avoid=()):
    """The quote pipeline as a LangGraph graph: route -> weather -> [High risk: re-plan avoiding chokepoints, retry] -> pricing -> customs -> margin.
    cid=None runs it without logging (used by the Digital Twin and the quote preview)."""
    st = {"req": req, "results": {}, "avoid": tuple(avoid), "quote_id": qid, "tries": 0}
    def step(name, fn):
        t = time.time()
        try: res = fn(st)
        except Exception as e: res = AgentResult(name, 40, "High", f"error: {e}")
        st["results"][name] = res
        if cid: _log_run(cid, "quote", res, int((time.time() - t) * 1000))
        return res
    def replan():
        st["avoid"] = ("suez",); st["tries"] += 1
        if cid: _log_run(cid, "quote", AgentResult("re-plan", 100, "Low", f"weather High: re-routing avoiding Suez/Red Sea (try {st['tries']})"), 0)
    def need_replan(): return st["results"]["weather"].findings.get("level") == "High" and st["tries"] < 1 and st["results"]["route"].findings.get("alternatives") and "suez" not in st["avoid"]
    try:
        from langgraph.graph import StateGraph, END
        from typing import TypedDict
        class G(TypedDict, total=False): n: int
        gr = StateGraph(G)
        gr.add_node("route", lambda g: (step("route", route_agent), {})[1]); gr.add_node("weather", lambda g: (step("weather", weather_agent), {})[1]); gr.add_node("replan", lambda g: (replan(), {})[1])
        gr.add_node("rest", lambda g: ([step(n, f) for n, f in (("pricing", pricing_agent), ("customs", customs_agent), ("margin", margin_agent))], {})[1])
        gr.set_entry_point("route"); gr.add_edge("route", "weather"); gr.add_edge("replan", "route"); gr.add_conditional_edges("weather", lambda g: "replan" if need_replan() else "rest"); gr.add_edge("rest", END); gr.compile().invoke({"n": 0})
    except ImportError:
        step("route", route_agent); step("weather", weather_agent)
        if need_replan(): replan(); step("route", route_agent); step("weather", weather_agent)
        for nme, fn in (("pricing", pricing_agent), ("customs", customs_agent), ("margin", margin_agent)): step(nme, fn)
    return st, step

def _decide(st):
    res = st["results"]; req = st["req"]; wr, cr, rt = res["weather"].findings["risk"], res["customs"].findings["risk"], res["route"].findings["congestion"] / 3
    risk = round(wr * .4 + cr * .3 + rt * .3, 3); m = res["margin"].findings; val = m["price"]          # PRS v3: weather x0.40 + customs x0.30 + congestion x0.30
    decision = "On Hold" if res["customs"].findings["status"] == "Hold" or risk > .7 else "Pending Approval" if val > 50000 or m["margin_pct"] < 10 else "Approved"
    narr = f"Quote {st['quote_id']}: {req['origin']} to {req['dest']}, {res['route'].findings['route']}, {res['route'].findings['transit_days']} days. Risk score {risk} (weather {wr}, customs {cr}, congestion {rt:.2f}). Price ${val:,.0f} at {m['margin_pct']}% margin. Decision: {decision}."
    return risk, decision, val, m, narr

def preview_quote(req, avoid=()):
    """Price a lane without saving anything. The Digital Twin calls this on its database copy."""
    st, _ = _compute(dict(req), "PREVIEW", None, avoid)
    if not all(k in st["results"] and st["results"][k].findings for k in ("route", "weather", "pricing", "customs", "margin")): return None
    risk, decision, val, m, narr = _decide(st); r = st["results"]
    return {"price": val, "margin_pct": m["margin_pct"], "risk": risk, "decision": decision, "route": r["route"].findings["route"], "days": r["route"].findings["transit_days"], "weather": r["weather"].findings["level"], "narrative": narr}

def run_quote(req_id):
    from live_engine import _log_run, init_live_tables, act
    import sys; dom = sys.modules[__name__]; init_live_tables()
    r = Q("SELECT * FROM quote_requests WHERE req_id=?", (req_id,)); req = r.iloc[0].to_dict(); cid = f"Q{req_id}-" + datetime.datetime.now().strftime("%H%M%S"); qid = f"QTE-L{req_id:05d}"
    st, step = _compute(req, qid, cid); res = st["results"]
    if not all(k in res and res[k].findings for k in ("route", "weather", "pricing", "customs", "margin")):
        with _DB_LOCK, conn() as c: c.execute("UPDATE quote_requests SET status='error', result=? WHERE req_id=?", (json.dumps({k: v.summary for k, v in res.items()}), req_id)); return None
    risk, decision, val, m, narr = _decide(st); step("document", document_agent); step("alert", alert_agent); wr, cr, rt = res["weather"].findings["risk"], res["customs"].findings["risk"], res["route"].findings["congestion"] / 3
    with _DB_LOCK, conn() as c:
        sid = f"SHP-{qid[4:]}"
        c.execute("INSERT OR REPLACE INTO shipments(shipment_id,origin_port,dest_port,carrier,status,eta,weight_kg,hs_code,predicted_delay_risk) VALUES(?,?,?,?,?,?,?,?,?)", (sid, req["origin"], req["dest"], res["route"].findings["carriers"][0], "Customs Hold" if decision == "On Hold" else "Quoted", (datetime.date.today() + datetime.timedelta(days=int(res["route"].findings["transit_days"]) + 3)).isoformat(), req["weight_t"] * 1000, req["hs_code"], risk))
        p = res["pricing"].findings; c.execute("INSERT OR REPLACE INTO freight_quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (qid, sid, req["customer_id"], res["route"].findings["carriers"][0], p["base"], round(p["base"] * .02, 2), round(p["base"] * res["customs"].findings["duty_pct"] / 100 * .1, 2), p["fuel"], val, m["margin_pct"], decision, now()[:10]))
        c.execute("UPDATE quote_requests SET status='done', quote_id=?, result=? WHERE req_id=?", (qid, json.dumps({"decision": decision, "risk": risk, "price": val, "narrative": narr, "missing": res["customs"].findings["missing"], "route": res["route"].findings["route"], "days": res["route"].findings["transit_days"], "weather": res["weather"].findings["level"], "margin_pct": m["margin_pct"], "parts": {"weather": wr, "customs": cr, "congestion": round(rt, 2)}}), req_id))
    dec = {"score": round((1 - risk) * 100, 1), "risk": risk_label((1 - risk) * 100), "narrative": narr, "actions": res["alert"].actions + ([{"type": "quote_hold", "target": qid, "detail": "Customs hold, missing: " + ", ".join(res["customs"].findings["missing"]), "severity": "Warning"}] if decision == "On Hold" and res["customs"].findings["missing"] else [])}
    act(dom, dec, cid, {}); return dec

def attach_doc(ref, doc, by="user"):
    """Attach a missing customs document to a quote (QTE-...) or a shipment (SHP-...). Re-runs the quote so the hold lifts when nothing is missing."""
    with _DB_LOCK, conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS shipment_docs(ref TEXT, doc TEXT, ts TEXT, by TEXT, UNIQUE(ref, doc))"); c.execute("INSERT OR IGNORE INTO shipment_docs VALUES(?,?,?,?)", (ref, doc, now(), by))
    emit("doc_attached", ref, {"doc": doc})
    if ref.startswith("QTE-L"):
        try: run_quote(int(ref[5:]))
        except Exception: pass

# ---------------------------------------------------------------- fleet monitoring cycle (the same agents, run continuously)
def route_watch(s):
    p = Q("SELECT port_name, congestion_index ci, avg_dwell_days dw FROM ports WHERE congestion_index>=4").sort_values("ci", ascending=False)
    n = Q("SELECT COUNT(*) n FROM shipments WHERE status='Port Congestion Delay'").n[0]; sc = 100 - min(60, len(p) * 3 + n * .5)
    return AgentResult("route_watch", sc, risk_label(sc), f"{len(p)} ports with congestion index >= 4, {n} shipments delayed", {"ports": p.head(8).port_name.tolist(), "n_congested": len(p), "delayed": int(n)}, [{"type": "congestion_notice", "target": r.port_name, "detail": f"Congestion index {r.ci:.1f}, dwell {r.dw:.1f} days", "severity": "Warning"} for r in p.head(6).itertuples()])
def weather_watch(s):
    v = Q("SELECT shipment_id, lat, lon, chain FROM vessels"); bad = []; acts = []
    for r in v.itertuples():
        w = weather_at(r.lat, r.lon, allow_live=False)
        if w["level"] == "High": bad.append(r.shipment_id)
    for sid in bad[:15]:
        acts.append({"type": "reroute", "target": sid, "detail": "High weather at current vessel position: alternate route proposed", "severity": "Critical"})
    sc = 100 - min(90, len(bad) / max(len(v), 1) * 400); return AgentResult("weather_watch", sc, risk_label(sc), f"{len(bad)} of {len(v)} vessels in High-risk weather ({len(storms())} active storms)", {"vessels_high": bad}, acts)
def customs_watch(s):
    """Shipments on customs hold: required documents (customs_rules by HS chapter) minus documents attached. Clears the hold when nothing is missing."""
    h = Q("SELECT shipment_id, hs_code FROM shipments WHERE status='Customs Hold'"); acts = []; cleared = 0
    for r in h.itertuples():
        ch, docs, restricted, duty, goods = _required_docs(r.hs_code); miss = [d for d in docs if d not in _attached(r.shipment_id)]
        if not miss and not restricted:
            with _DB_LOCK, conn() as c: c.execute("UPDATE shipments SET status='In Transit' WHERE shipment_id=?", (r.shipment_id,)); emit("customs_cleared", r.shipment_id); cleared += 1; continue
        acts.append({"type": "customs_docs", "target": r.shipment_id, "detail": f"Customs hold ({r.hs_code}, {goods}): missing {', '.join(miss[:4]) if miss else 'restricted goods clearance'}", "severity": "Warning"})
    n = len(h) - cleared; sc = 100 - min(70, n * 2)
    return AgentResult("customs_watch", sc, risk_label(sc), f"{n} shipments on customs hold, {cleared} cleared this cycle", {"holds": n, "cleared": cleared}, acts[:25])
def quote_watch(s):
    p = Q("SELECT q.quote_id, q.final_price, q.margin_pct, q.status, r.result FROM freight_quotes q LEFT JOIN quote_requests r ON r.quote_id=q.quote_id WHERE q.status IN ('Pending Approval','On Hold')"); acts = []
    for r in p.itertuples():
        if r.status == "Pending Approval": acts.append({"type": "quote_approval", "target": r.quote_id, "detail": f"Quote ${r.final_price:,.0f} exceeds $50,000: admin approval required" if r.final_price > 50000 else "Margin below 10%: approval required", "severity": "Critical" if r.final_price > 50000 else "Warning", "owner": "Admin"})
        else:
            try: miss = json.loads(r.result or "{}").get("missing", [])
            except Exception: miss = []
            acts.append({"type": "quote_hold", "target": r.quote_id, "detail": "Customs hold, missing: " + ", ".join(miss) if miss else "On hold: shipment risk score above 0.7", "severity": "Warning"})
    sc = 100 - min(60, len(p) * 3); return AgentResult("quote_watch", sc, risk_label(sc), f"{len(p)} quotes awaiting approval or on hold", {"pending": int((p.status == 'Pending Approval').sum()), "on_hold": int((p.status == 'On Hold').sum())}, acts[:30])

def anomaly_watch(s):
    """IsolationForest over quote economics (price/base ratio, margin, fuel share) to catch mispriced or tampered quotes."""
    from sklearn.ensemble import IsolationForest
    q = Q("SELECT quote_id, base_cost, fuel_surcharge, final_price, margin_pct FROM freight_quotes WHERE base_cost>0")
    if len(q) < 30: return AgentResult("anomaly_watch", 100, "Low", "waiting for more quotes", {"flagged": []})
    X = pd.DataFrame({"ratio": q.final_price / q.base_cost, "margin": q.margin_pct, "fuel": q.fuel_surcharge / q.base_cost}); iso = IsolationForest(contamination=.06, random_state=42).fit(X); q["flag"] = iso.predict(X) == -1
    bad = q[q.flag]; sc = 100 - len(bad) / len(q) * 250
    return AgentResult("anomaly_watch", round(max(sc, 0), 1), risk_label(sc), f"{len(bad)} of {len(q)} quotes look anomalous (IsolationForest)", {"flagged": bad.quote_id.tolist()},
        [{"type": "quote_anomaly", "target": r.quote_id, "detail": f"Price/base ratio {r.final_price / r.base_cost:.2f}, margin {r.margin_pct:.1f}%: review before sending", "severity": "Warning"} for r in bad.head(10).itertuples()])

AGENTS = {"route_watch": route_watch, "weather_watch": weather_watch, "customs_watch": customs_watch, "quote_watch": quote_watch, "anomaly_watch": anomaly_watch}
REPLAN = {"weather_watch": lambda r: ["route_watch"] if r.risk != "Low" else []}
def plan(req): return list(AGENTS)
def engine(s):
    r = s["results"]; score = float(np.mean([v.score for v in r.values()])); acts = [a for v in r.values() for a in v.actions]; order = {"Critical": 0, "Warning": 1, "Info": 2}; acts.sort(key=lambda a: order.get(a.get("severity"), 3))
    ev = {"fleet_health": round(score, 1), "vessels": int(Q("SELECT COUNT(*) n FROM vessels").n[0]), "agents": {k: {"score": v.score, "risk": v.risk, "summary": v.summary} for k, v in r.items()}, "critical": sum(a.get("severity") == "Critical" for a in acts)}
    n = f"Fleet health {ev['fleet_health']}/100 with {ev['vessels']} vessels tracked. " + " ".join(f"{k}: {v['summary']}." for k, v in ev["agents"].items())
    return {"score": round(score, 1), "risk": risk_label(score), "narrative": n, "actions": acts, "agents": ev["agents"], "evidence": ev}
def apply(a, c):
    if a["type"] == "reroute":
        sid = a["target"]; v = c.execute("SELECT lat, lon, chain FROM vessels WHERE shipment_id=?", (sid,)).fetchone()
        if v:
            ch = json.loads(v[2]); dest = ch[-1]
            if a.get("opt_idx") is not None:
                import alts; row = c.execute("SELECT s.weight_kg FROM shipments s WHERE shipment_id=?", (sid,)).fetchone(); al = alts.route_alternatives(sys.modules[__name__], (v[0], v[1]), dest, tonnes=float((row or [20000])[0] or 20000) / 1000, interp=interp); i = int(a["opt_idx"]); opt = al[i] if i < len(al) else al[0]
            else: opt = route_options((v[0], v[1]), dest, avoid=("storm",))[0]
            c.execute("UPDATE vessels SET chain=?, progress=0, route_name=? WHERE shipment_id=?", (json.dumps([(v[0], v[1])] + opt["chain"][1:]), ("rerouted: " if a.get("opt_idx") is not None else "rerouted around storm: ") + opt["name"], sid)); return f"vessel re-planned {opt['name']} ({opt['nm']:,} nm)"
    return ""
def decide(action_id, approve, by="user"):
    from live_engine import resolve_action
    with _DB_LOCK, conn() as c:
        t = c.execute("SELECT target FROM agent_actions WHERE action_id=?", (action_id,)).fetchone()
        if t and t[0].startswith("QTE"): c.execute("UPDATE freight_quotes SET status=? WHERE quote_id=?", ("Approved" if approve else "Rejected", t[0]))
    resolve_action(action_id, "approved" if approve else "rejected", f"by {by}")
def submit_request(origin, dest, cargo, weight_t, hs_code, customer_id, language="English", docs_provided=None):
    with _DB_LOCK, conn() as c: return c.execute("INSERT INTO quote_requests(ts,origin,dest,cargo,weight_t,hs_code,customer_id,language,docs_provided) VALUES(?,?,?,?,?,?,?,?,?)", (now(), origin, dest, cargo, weight_t, hs_code, customer_id, language, ";".join(docs_provided) if docs_provided is not None else None)).lastrowid
def feed_status():
    o = time.time() < _OFF[0]; return [("Open-Meteo weather and marine", "Offline: simulated winds in use" if o else "Real · live (cached 15 min)"), ("Vessel positions", "Simulated along real route waypoints (connect AIS via Data Feeder)"), ("Port congestion", "ML predicted, drifts live"), ("Freight-rate model data", "Bootstrap synthetic unless a Kaggle CSV is fed")]
def kpi_extra():
    return [("Vessels tracked", int(Q("SELECT COUNT(*) n FROM vessels").n[0])), ("Quotes awaiting approval", int(Q("SELECT COUNT(*) n FROM freight_quotes WHERE status='Pending Approval'").n[0]))]

def _prewarm():
    try:
        import seanav; seanav.sea()
    except Exception: pass
import threading as _th; _th.Thread(target=_prewarm, daemon=True).start()


# Kept from the app shell: server.py calls this at startup (the Customs page needs the table before the worker has booted).
def ensure_schema():
    with _DB_LOCK, conn() as c:
        c.executescript("CREATE TABLE IF NOT EXISTS quote_requests(req_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, origin TEXT, dest TEXT, cargo TEXT, weight_t REAL, hs_code TEXT, customer_id TEXT, language TEXT, status TEXT DEFAULT 'new', quote_id TEXT, result TEXT, docs_provided TEXT);\n        CREATE TABLE IF NOT EXISTS shipment_docs(ref TEXT, doc TEXT, ts TEXT, by TEXT, UNIQUE(ref, doc));\n        CREATE TABLE IF NOT EXISTS vessels(shipment_id TEXT PRIMARY KEY, lat REAL, lon REAL, progress REAL, chain TEXT, route_name TEXT, speed_kn REAL, updated TEXT);\n        CREATE TABLE IF NOT EXISTS ml_models(model_id INTEGER PRIMARY KEY AUTOINCREMENT, model_name TEXT, metrics TEXT, trained_at TEXT, is_active INT);\n        CREATE TABLE IF NOT EXISTS customs_rules(chapter TEXT PRIMARY KEY, goods TEXT, duty_pct REAL, docs TEXT, restricted INT);")
        # On a fresh Colab session the background worker may not have started yet.
        # Populate the same professor-provided rules required by the Customs page,
        # without touching any existing user, shipment or quotation records.
        if not c.execute("SELECT 1 FROM customs_rules LIMIT 1").fetchone():
            base = "Commercial Invoice;Packing List;Bill of Lading"
            for chapter, goods, duty, extra, restricted in [
                ("30", "Pharmaceuticals", 5, "Import License;Drug Control Certificate", 1),
                ("84", "Machinery", 7.5, "Certificate of Origin", 0),
                ("85", "Electronics", 10, "BIS Certificate;Certificate of Origin", 0),
                ("87", "Vehicles and parts", 15, "Homologation Certificate", 0),
                ("10", "Cereals", 12, "Phytosanitary Certificate", 0),
                ("62", "Apparel", 12, "Certificate of Origin", 0),
                ("27", "Mineral fuels", 5, "Hazmat Declaration;IMDG Certificate", 1),
                ("39", "Plastics", 8, "Certificate of Origin", 0),
                ("72", "Iron and steel", 7.5, "Mill Test Certificate", 0),
                ("22", "Beverages", 20, "Excise Permit", 1),
            ]:
                c.execute("INSERT OR IGNORE INTO customs_rules (chapter, goods, duty_pct, docs, restricted) VALUES(?,?,?,?,?)", (chapter, goods, duty, base + ";" + extra, restricted))
