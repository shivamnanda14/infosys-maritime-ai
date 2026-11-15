"""FreightQuote AI pages (server-driven blocks)."""
import os, re, json, datetime
import numpy as np, pandas as pd
import live_engine as LE, entities as EN
import domain_freight as dom
import blocks as B
from blocks import Q, clean, L, TEAL, BLUE, AMBER, RED, VIOLET, GREEN, TONE
from views_core import can, latest, decision, ticket_block, tk_df, cross, hero, scoped

NAME = "FreightQuote AI"
MENU = [('copilot', 'AI Copilot', 'bot'), ('route', 'Agent 1 · Route AI', 'route'), ('quotes', 'Agent 2 · Spot Quotes', 'dollar'), ('carriers', 'Agent 3 · Carriers', 'truck'), ('weather', 'Agent 4 · Weather Risk', 'cloud'), ('margin', 'Agent 5 · Margin', 'trend'), ('customs', 'Agent 6 · Customs', 'file')]
SEVC = {2: RED, 1: AMBER, 0: BLUE, -1: TEAL}
FLEET_LEGEND = [("Vessel · no ticket", TEAL), ("Vessel · info ticket", BLUE), ("Vessel · warning ticket", AMBER), ("Vessel · critical ticket", RED), ("Port · low congestion (big dot)", "#8b8d98"), ("Port · congestion 3+", "#d98e04"), ("Port · congestion 4+", "#b4262b"), ("Storm cell (circle)", "#e5484d")]
def dport(ports, key, alt=0): return next((p for p in ports if key.lower() in p.lower()), ports[min(alt, len(ports) - 1)])

# ------------------------------------------------------------------ map layers
def fleet_layers(vessels=True, ports=True, storms=True, v=None):
    layers = []
    if ports:
        p = Q("SELECT port_name, lat, lon, congestion_index ci FROM ports"); layers.append({"type": "points", "id": "ports", "pts": [{"id": r.port_name, "lat": r.lat, "lon": r.lon, "color": "#b4262b" if r.ci >= 4 else "#d98e04" if r.ci >= 3 else "#8b8d98", "r": 3 + r.ci, "tip": f"<b>{r.port_name}</b><br>congestion {r.ci:.1f}", "open": r.port_name, "z": 1} for r in p.itertuples()]})
    if vessels:
        v = Q("SELECT v.shipment_id, v.lat, v.lon, v.route_name, v.progress, s.origin_port o, s.dest_port d FROM vessels v JOIN shipments s USING(shipment_id)") if v is None else v
        tk = Q("SELECT target, MAX(CASE severity WHEN 'Critical' THEN 2 WHEN 'Warning' THEN 1 ELSE 0 END) sv FROM agent_actions WHERE status IN ('open','proposed') GROUP BY target").set_index("target").sv
        layers.append({"type": "points", "id": "vessels", "pts": [{"id": r.shipment_id, "lat": r.lat, "lon": r.lon, "color": SEVC[int(tk.get(r.shipment_id, -1))], "r": 5, "tip": f"<b>{r.shipment_id}</b><br>{r.o} → {r.d}<br>{r.route_name} · {r.progress:.0%}", "open": r.shipment_id, "z": 2} for r in v.itertuples()]})
    if storms: layers.append({"type": "circles", "items": [{"lat": s["lat"], "lon": s["lon"], "r_m": float(s.get("r", 700)) * 1852, "color": RED, "tip": f"Storm · wind {s.get('wind', '?')} m/s"} for s in dom.storms()]})
    return layers

# ------------------------------------------------------------------ Command Center: Operations
def ops(c):
    d = decision(); oa = tk_df(c, limit=500); ex = dom.kpi_extra(); fl = Q("SELECT COUNT(*) n FROM vessels").n[0]
    mp = B.map_(fleet_layers(), h=510, view={"center": [20, 60], "zoom": 2}, key="ops_map", legend=FLEET_LEGEND)
    q = Q("SELECT quote_id, ROUND(final_price) price, margin_pct margin, status FROM freight_quotes ORDER BY rowid DESC LIMIT 7"); p = Q("SELECT port_name, ROUND(congestion_index,1) ci FROM ports ORDER BY congestion_index DESC LIMIT 7")
    h = Q("SELECT substr(ts,12,8) t, score FROM decisions ORDER BY decision_id DESC LIMIT 80").iloc[::-1]; by = oa.assign(agent=oa.type.map(lambda t: dom.ACTION_AGENT.get(t, "engine"))).groupby("agent").size().sort_values() if len(oa) else pd.Series(dtype=int)
    bl = [B.kpis(("Fleet health", d["score"] if d else "…", (d or {}).get("risk", "") + " risk", "Critical" if d and d["risk"] == "High" else "Warning" if d and d["risk"] == "Medium" else "Low"), ("Vessels tracked", int(fl)), ("Open tickets", int((oa.status == "open").sum()) if len(oa) else 0), ("Critical", int(((oa.severity == "Critical") & (oa.status == "open")).sum()) if len(oa) else 0, None, "Critical"),
                  ("Awaiting approval", int((oa.status == "proposed").sum()) if len(oa) else 0, "agent proposals", "Warning"), ("Active storms", len(dom.storms()), None, "Critical" if dom.storms() else None))]
    if d: bl.append({"t": "brief", "text": d["narrative"], "id": d["id"], "can_brief": True})
    bl.append(B.row(B.card("Live fleet · click a vessel or port", mp), B.col(B.card("Latest quotes", B.table(q, ["quote_id", B.num_col("price", "price", "money"), B.num_col("margin", "margin %", "num"), B.pill_col("status")], h=230, open={"col": "quote_id"}, key="lq")), B.card("Most congested ports", B.table(p, ["port_name", B.num_col("ci", "index", "bar", 5)], h=230, open={"col": "port_name"}, key="cp"))), ratio=[3, 2]))
    bl.append(B.row(B.card("Health trend", B.chart(B.line(h.t, h.score, ymin=0, ymax=100, colors=[TEAL]), h=220, key="trend")), B.card("Open tickets by agent", B.chart(B.bar(by.index, by.values, horizontal=True, colors=[BLUE]), h=220, key="byag"))))
    if can(c, "storm"): bl.append(B.button("storm", "Inject a demo storm (tests the re-route loop)", "/api/freight/storm", "ghost", payload={}))
    return bl

# ------------------------------------------------------------------ detail drawer
def detail(c, e):
    k = EN.kind_of(e)
    if k == "shipment":
        if c.get("role") == "Customer":
            cust_id = c.get("customer_id")
            if not cust_id:
                from fastapi import HTTPException
                raise HTTPException(403, "Access denied: no customer ID associated with account.")
            owned = Q("SELECT 1 FROM freight_quotes WHERE shipment_id=? AND customer_id=?", (e, cust_id))
            if not len(owned):
                from fastapi import HTTPException
                raise HTTPException(403, "Access denied: this shipment does not belong to your account.")
        v = Q("SELECT v.lat, v.lon, v.route_name, v.progress, v.chain, s.origin_port o, s.dest_port d, s.carrier, s.status, s.eta, s.weight_kg, s.hs_code, s.predicted_delay_risk risk FROM vessels v RIGHT JOIN shipments s USING(shipment_id) WHERE s.shipment_id=?", (e,))
        if not len(v): return {"title": e, "blocks": [B.callout("Unknown shipment.", "warn")]}
        r = v.iloc[0]; bl = []
        if pd.notna(r.lat):
            w = dom.weather_at(float(r.lat), float(r.lon), allow_live=False); ch = json.loads(r.chain) if r.chain else []
            bl.append(B.kpis(("Progress", f"{r.progress * 100:.0f}%"), ("Wind m/s", round(w["wind"], 1)), ("Wave m", round(w["wave"], 1)), ("Weather", w["level"], w["src"], TONE.get(w["level"]))))
            bl.append(B.map_([{"type": "lines", "lines": [{"pts": ch, "color": TEAL, "w": 3, "dash": "6 6"}]}, {"type": "points", "id": "me", "pts": [{"id": e, "lat": r.lat, "lon": r.lon, "color": "#1f2430", "r": 8, "tip": e}]}, {"type": "circles", "items": [{"lat": s["lat"], "lon": s["lon"], "r_m": float(s.get("r", 700)) * 1852, "color": RED, "tip": "storm"} for s in dom.storms()]}], h=230, view={"center": [float(r.lat), float(r.lon)], "zoom": 3}, key="d_map", legend=[("This port", "#1f2430"), ("Planned voyage route", TEAL), ("Storm cell (red circle)", RED)]))
        else: bl.append(B.callout(f"Not at sea: status {r.status}.", "info"))
        bl.append(B.table([{"field": "Route", "value": f"{r.o} → {r.d}"}, {"field": "Carrier", "value": r.carrier}, {"field": "Status", "value": r.status}, {"field": "ETA", "value": r.eta}, {"field": "Cargo weight", "value": f"{(r.weight_kg or 0) / 1000:,.1f} t"}, {"field": "HS code", "value": r.hs_code}, {"field": "Predicted delay risk", "value": r.risk}], ["field", "value"], h=250, key="d_f"))
        bl.append(ticket_block(c, target=e, title=f"Tickets for {e}", key="d_tk"))
        try:
            import alts; po, pd_ = dom.port_xy(r.o), dom.port_xy(r.d); start = (float(r.lat), float(r.lon)) if pd.notna(r.lat) else (po[0], po[1]) if po else None
            if start and pd_:
                ao = alts.route_alternatives(dom, start, (pd_[0], pd_[1]), tonnes=float(r.weight_kg or 20000) / 1000, interp=dom.interp, dwell=(pd_[3] if pd_ else 0) * .5); bl += alts.route_blocks(ao, e, "Route alternatives" + (" from the vessel's position" if pd.notna(r.lat) else ""))
                if can(c, "approve") and pd.notna(r.lat) and ao: bl.append(B.form("rr_" + e, [{"name": "opt", "label": "Switch to", "type": "select", "options": [f"{i + 1}. {x['label']} · {x['name']}" for i, x in enumerate(ao)], "value": "1. " + ao[0]["label"] + " · " + ao[0]["name"]}, {"name": "shipment", "type": "hidden", "value": e}], "Re-route this voyage", "/api/freight/reroute", title="Apply a route", sub="Needs approve rights. The vessel is re-planned from its current position and the change is audited.", tone="ghost"))
        except Exception as ex: bl.append(B.callout(f"Route alternatives unavailable: {ex}", "info"))
        return {"title": e, "sub": f"{r.o} → {r.d}", "blocks": bl}
    if k == "quote":
        q = Q("SELECT * FROM freight_quotes WHERE quote_id=?", (e,))
        if not len(q): return {"title": e, "blocks": [B.callout("Unknown quote.", "warn")]}
        r = q.iloc[0]
        if c.get("role") == "Customer":
            cust_id = c.get("customer_id")
            if not cust_id or r.customer_id != cust_id:
                from fastapi import HTTPException
                raise HTTPException(403, "Access denied: this quote does not belong to your account.")
            bl = [
                B.kpis(("Price", f"${r.final_price:,.0f}"), ("Status", r.status)),
                B.table([
                    {"field": "Quote ID", "value": r.quote_id},
                    {"field": "Carrier", "value": r.carrier},
                    {"field": "Status", "value": r.status},
                    {"field": "Created At", "value": str(r.created_at)},
                ], ["field", "value"], h=180, key="d_qcust"),
                ticket_block(c, target=e, title="Tickets", key="d_tk")
            ]
            return {"title": e, "sub": r.status, "blocks": bl}
        cost = r.base_cost + r.fuel_surcharge + r.customs_fee + r.insurance
        return {"title": e, "sub": r.status, "blocks": [B.kpis(("Price", f"${r.final_price:,.0f}"), ("Margin", f"{r.margin_pct}%"), ("Status", r.status)), B.chart(B.waterfall(["Base (ML)", "Fuel", "Customs", "Insurance", "Margin"], [r.base_cost, r.fuel_surcharge, r.customs_fee, r.insurance, r.final_price - cost]), "How the price is built", h=260, key="d_wf"), ticket_block(c, target=e, title="Tickets", key="d_tk")]}
    p = Q("SELECT * FROM ports WHERE port_name=?", (e,))
    if not len(p): return {"title": e, "blocks": [B.callout("No detail view for this entity.", "info")]}
    r = p.iloc[0]; w = Q("SELECT current_severity sev, wind_speed, wave_height FROM weather_risks WHERE port_name=?", (e,)); sh = Q("SELECT shipment_id, carrier, status FROM shipments WHERE origin_port=? OR dest_port=? LIMIT 12", (e, e))
    bl = [B.kpis(("Congestion index", round(float(r.congestion_index), 2), None, "Critical" if r.congestion_index >= 4 else None), ("Avg dwell days", r.avg_dwell_days), ("Country", r.country)), B.table(sh, ["shipment_id", "carrier", B.pill_col("status")], title="Shipments via this port", h=250, open={"col": "shipment_id"}, key="d_sh")]
    try:
        import alts; bl += alts.port_alternatives(e)
    except Exception: pass
    if len(w): bl.insert(1, B.kpis(("Weather", w.sev[0], f"wind {w.wind_speed[0]:.0f} km/h · wave {w.wave_height[0]:.1f} m", TONE.get(w.sev[0]))))
    return {"title": e, "sub": f"{r.country} · port", "blocks": bl}

# ------------------------------------------------------------------ pages
def route(c, tab=None):
    v = Q("SELECT COUNT(*) n FROM vessels").n[0]; p = Q("SELECT port_name, country, region, congestion_index ci, avg_dwell_days dw FROM ports"); sh = Q("SELECT status, COUNT(*) n FROM shipments GROUP BY status").set_index("status").n
    ports = sorted(p.port_name); pr = c.get("params") or {}; o = pr.get("o") or dport(ports, "JNPT"); d = pr.get("d") or dport(ports, "Rotterdam", 1); cg = pr.get("cargo") or "Electronics"
    bl = [hero(c, "route_watch", "Route & congestion agent", "Compares Suez and Cape routings with a RandomForest congestion classifier and a live weather check along the lane. Watches every port."),
          B.kpis(("Vessels tracked", int(v)), ("Ports monitored", len(p)), ("Congested (≥ 4)", int((p.ci >= 4).sum()), None, "Warning"), ("Active storms", len(dom.storms())))]
    bl.append(B.card("Live fleet", B.map_(fleet_layers(), h=400, view={"center": [20, 60], "zoom": 2}, key="rt_map", legend=FLEET_LEGEND)))
    top = p.sort_values("ci", ascending=False).head(12)
    bl.append(B.row(B.card("Most congested ports (click)", B.chart(B.bar(top.port_name, top.ci.round(2), horizontal=True, itemcolors=[RED if x >= 4 else AMBER for x in top.ci], max_=5), h=330, open={"bar": "y"}, key="rt_c")), B.card("Shipments by status", B.chart(B.bar(sh.index, sh.values.astype(int), colors=[BLUE]), h=330, key="rt_s"))))
    bl.append(B.form("rt_plan", [{"name": "o", "label": "Origin", "type": "select", "options": ports, "value": o}, {"name": "d", "label": "Destination", "type": "select", "options": ports, "value": d}, {"name": "cargo", "label": "Cargo", "type": "select", "options": list(dom.CARGO), "value": cg}], "Plan route", "page:route", title="Route planner", sub="Same route, weather and congestion logic as the quote pipeline.", tone="ghost"))
    # Heavy ocean-graph work is optional for rendering the Route dashboard.
    # Keep the fleet map, KPIs and route-planner inputs visible even when
    # the navigation graph cannot be loaded or a particular lane has no path.
    try:
        po, pd_ = dom.port_xy(o), dom.port_xy(d)
        if po and pd_ and o != d:
            opts = dom.route_options(po[:2], pd_[:2]); cong = dom.predict_congestion((po[2] + pd_[2]) / 2, (po[3] + pd_[3]) / 2, cg); rows, lines = [], []
            for i, op in enumerate(opts):
                ws = [dom.weather_at(*dom.interp(op["chain"], f), allow_live=False) for f in (0, .25, .5, .75, 1)]; worst = max(ws, key=lambda w: w["wind"]); days = op["nm"] / (14 * 24) + po[3] * .5 + pd_[3] * .5
                rows.append({"route": op["name"], "distance_nm": op["nm"], "transit_days": round(days, 1), "weather_risk": worst["level"], "max_wind_ms": worst["wind"]}); lines.append({"pts": op["chain"], "color": TEAL if i == 0 else AMBER, "w": 4, "dash": None if i == 0 else "8 8", "tip": op["name"]})
            bl.append(B.row(B.card("Route options", B.table(rows, ["route", B.num_col("distance_nm", "nm", "int"), B.num_col("transit_days", "days", "num"), B.pill_col("weather_risk"), B.num_col("max_wind_ms", "max wind m/s", "num")], h=150, key="rt_o"), B.callout(f"Predicted congestion level {cong}/3 (RandomForest: port congestion index, dwell time, month, weekday, cargo).", "info")),
                            B.map_([{"type": "lines", "lines": lines}, {"type": "points", "id": "ends", "pts": [{"id": o, "lat": po[0], "lon": po[1], "color": TEAL, "r": 7, "tip": o}, {"id": d, "lat": pd_[0], "lon": pd_[1], "color": BLUE, "r": 7, "tip": d}]}], h=300, key="rt_pm", view={"bounds": [[min(p[0] for ln in lines[:1] for p in ln["pts"]) - 4, min(p[1] for ln in lines[:1] for p in ln["pts"]) - 4], [max(p[0] for ln in lines[:1] for p in ln["pts"]) + 4, max(p[1] for ln in lines[:1] for p in ln["pts"]) + 4]]}, legend=[("Recommended (sea route)", TEAL), ("Alternative", AMBER)])))
    except Exception:
        import logging, traceback
        logging.getLogger("uvicorn.error").exception("Route planner calculation failed")
        bl.append(B.callout("Route options could not be calculated for the selected ports. Try another origin or destination; check the server diagnostics if the problem continues.", "warn"))
    x = cross(c, p[p.ci >= 4].port_name.tolist(), "route_watch"); bl += [x] if x else []
    bl.append(ticket_block(c, "route_watch", title="Open tickets from this agent", key="tk_rt")); return B.page("Route AI", "Agent 1 · routing, congestion, lane planning", bl, live=10)

def _docs_all(): return sorted({d for s in Q("SELECT docs FROM customs_rules").docs for d in str(s).split(";") if d})
def quote_form(c):
    ports = Q("SELECT port_name FROM ports ORDER BY port_name").port_name.tolist(); cust = Q("SELECT customer_id FROM customers").customer_id.tolist(); alld = _docs_all(); ch, base, *_ = dom._required_docs("HS-8501")
    return B.form("quote", [{"name": "o", "label": "Origin", "type": "select", "options": ports, "value": dport(ports, "JNPT")}, {"name": "d", "label": "Destination", "type": "select", "options": ports, "value": dport(ports, "Rotterdam", 1)}, {"name": "cargo", "label": "Cargo", "type": "select", "options": list(dom.CARGO), "value": "Electronics"},
                                  {"name": "weight", "label": "Weight (tons)", "type": "number", "value": 120, "min": 1, "max": 5000}, {"name": "hs", "label": "HS code", "type": "text", "value": "HS-8501"}, {"name": "customer", "label": "Customer", "type": "select", "options": cust, "value": cust[0]},
                                  {"name": "docs", "label": "Documents you are submitting (tick all that apply; the customs agent checks them against the rules for the HS code)", "type": "checks", "options": alld, "value": base}], "Generate quote", "/api/freight/quote", title="New quote", sub="Runs the 7-agent pipeline: route → weather → (re-plan loop) → pricing (RandomForest) → customs → margin → documents → alerts.")
def quote_result(rid):
    r = Q("SELECT quote_id, result FROM quote_requests WHERE req_id=?", (rid,))
    if not len(r) or not r.result[0]: return [B.callout("The pipeline did not return a result.", "warn")]
    res = json.loads(r.result[0]); bl = [B.callout(res.get("narrative", ""), "success", "Pipeline result"), B.kpis(("Price (USD)", f"{res.get('price', 0):,.0f}"), ("Decision", res.get("decision")), ("Margin", f"{res.get('margin_pct')}%"), ("Transit", f"{res.get('days')} days"))]
    if res.get("missing"): bl.append(B.callout("Missing documents: " + ", ".join(res["missing"]) + ". Attach them on the Customs page and the quote re-runs.", "warn"))
    tr = Q("SELECT agent, risk, score, latency_ms ms, summary FROM agent_runs WHERE cycle_id LIKE ? ORDER BY run_id", (f"Q{rid}-%",)); bl.append(B.table(tr, ["agent", B.pill_col("risk"), B.num_col("score", "score", "num"), B.num_col("ms", "ms", "int"), "summary"], title="Agent trace for this quote", h=260, key="q_tr"))
    ddir = os.path.join(dom.DATA_DIR, "docs"); files = [p for p in (sorted(os.listdir(ddir)) if os.path.isdir(ddir) else []) if p.startswith(r.quote_id[0])]
    for p in files: bl.append(B.button("dl_" + p, "Download " + p, f"/api/doc/{p}", "ghost", payload={"download": True}))
    return bl
def quotes(c, tab=None):
    role = c.get("role")
    cust_id = c.get("customer_id")
    if role == "Customer":
        if not cust_id:
            return B.page("My Quotes", "Your active and past freight quotes", [
                B.callout("No customer account is currently linked to your profile. Please contact an administrator to link your customer account.", "info")
            ])
        q = Q("SELECT quote_id, carrier, final_price price, status, created_at FROM freight_quotes WHERE customer_id=? ORDER BY created_at DESC", (cust_id,))
        bl = [hero(c, "quote_watch", "My Quotes", "View spot quotes and status updates for your shipments.")]
        if len(q) == 0:
            bl.append(B.callout("You do not have any quotes in your account yet.", "info"))
        else:
            bl.append(B.kpis(("My Quotes", len(q)), ("Approved", int((q.status == "Approved").sum()), None, "Low"), ("Pending", int((q.status == "Pending Approval").sum()), None, "Warning")))
            bl.append(B.table(q, ["quote_id", "carrier", B.num_col("price", "price", "money"), B.pill_col("status"), "created_at"], title="My Quotes · click a row", h=340, open={"col": "quote_id"}, key="qt_t", search=True))
        return B.page("My Quotes", "Quotes linked to your account", bl, live=10)

    bl = [hero(c, "quote_watch", "Spot quotes agent", "Every quote goes through one pipeline: ML price (RandomForest) + 12% fuel + port fees + 15% operating cost, target margin ~20%. Quotes above $50,000 need admin approval.")]
    if can(c, "quote"): bl.append(quote_form(c))
    if can(c, "view"):
        q = Q("SELECT quote_id, customer_id, carrier, final_price price, margin_pct margin, status, created_at FROM freight_quotes ORDER BY created_at DESC, quote_id DESC LIMIT 400"); st = q.status.value_counts()
        bl.append(B.kpis(("Quotes", len(q)), ("Approved", int((q.status == "Approved").sum()), None, "Low"), ("Pending approval", int((q.status == "Pending Approval").sum()), None, "Warning"), ("On hold", int((q.status == "On Hold").sum()), None, "Critical")))
        bl.append(B.row(B.card("Quote decisions", B.chart(B.pie(st.to_dict(), colors={"Approved": TEAL, "Pending Approval": AMBER, "On Hold": RED, "Rejected": "#8b8d98"}), h=280, key="qt_p")), B.card("Margin % across quotes", B.chart(B.hist(q.margin, 24, BLUE), h=280, key="qt_h"))))
        bl.append(B.table(q.head(30), ["quote_id", "customer_id", "carrier", B.num_col("price", "price", "money"), B.num_col("margin", "margin %", "num"), B.pill_col("status"), "created_at"], title="Latest quotes · click a row", h=340, open={"col": "quote_id"}, key="qt_t", search=True))
        bl.append(ticket_block(c, "quote_watch", title="Open tickets from this agent", key="tk_qt"))
    return B.page("Spot Quotes", "Agent 2 · the 7-agent quote pipeline", bl, live=10)

def carriers(c, tab=None):
    k = Q("SELECT name, rating, on_time_pct, avg_cost_index, risk_level FROM carriers"); k["score"] = (k.rating / 5 * 40 + k.on_time_pct * .4 - k.avg_cost_index * 12 - (k.risk_level == "High") * 8).round(1)
    s = Q("SELECT carrier name, COUNT(*) shipments, SUM(status LIKE '%Delay%' OR status='Customs Hold') problems, AVG(predicted_delay_risk) delay_risk FROM shipments GROUP BY carrier"); k = k.merge(s, on="name", how="left").fillna({"shipments": 0, "problems": 0})
    top = k.sort_values("score", ascending=False).head(12); rc = {"Low": TEAL, "Medium": AMBER, "High": RED}
    sc = {t: [{"x": a.on_time_pct, "y": a.avg_cost_index, "label": a.name, "size": 6 + a.shipments ** .5} for a in k[k.risk_level == t].itertuples()] for t in ["Low", "Medium", "High"] if (k.risk_level == t).any()}
    bl = [hero(c, "route_watch", "Carrier intelligence", "Score = rating × 40% + on-time % × 0.4 − cost-index penalty − 8 points for High risk. Shipments and delays come from the live shipments table."),
          B.kpis(("Carriers", len(k)), ("High-risk carriers", int((k.risk_level == "High").sum()), None, "Warning"), ("Avg on-time", f"{k.on_time_pct.mean():.1f}%"), ("Best score", k.sort_values("score").name.iloc[-1])),
          B.row(B.card("Top carriers by agent score", B.chart(B.bar(top.name, top.score, horizontal=True, colors=[TEAL], sort=True), h=360, key="ca_t")), B.card("On-time vs cost index (size = shipments)", B.chart(B.scatter(sc, "on-time %", "cost index", colors=rc, sized=True), h=360, key="ca_s"))),
          B.table(k.sort_values("score", ascending=False), ["name", B.num_col("score", "score", "bar", 100), "rating", B.num_col("on_time_pct", "on-time %", "num"), B.num_col("avg_cost_index", "cost idx", "num"), B.pill_col("risk_level", "risk"), B.num_col("shipments", "shipments", "int"), B.num_col("problems", "problems", "int")], title="Carrier league table", h=340, key="ca_tb", search=True)]
    return B.page("Carriers", "Agent 3 · ranking and risk", bl, live=15)

METRICS = {"wind": ("Wind speed", [("Calm / light  < 8 m/s", TEAL), ("Strong  8–15 m/s", AMBER), ("Storm-force  > 15 m/s", RED)]),
           "waves": ("Wave height", [("Slight  < 2.5 m", TEAL), ("Rough  2.5–4 m", AMBER), ("Very rough  > 4 m", RED)]),
           "rain": ("Rain now", [("Dry", "#8b8d98"), ("Light rain  < 2.5 mm/h", BLUE), ("Heavy rain  ≥ 2.5 mm/h", VIOLET)]),
           "temp": ("Temperature", [("Cold  < 10 °C", BLUE), ("Mild  10–30 °C", TEAL), ("Hot  30–35 °C", AMBER), ("Very hot  > 35 °C", RED)])}
def _wxcolor(metric, r):
    if metric == "wind": return RED if r.wind_ms > 15 else AMBER if r.wind_ms >= 8 else TEAL
    if metric == "waves": w = r.wave_m if r.wave_m == r.wave_m and r.wave_m is not None else 0; return RED if w > 4 else AMBER if w >= 2.5 else TEAL
    if metric == "rain": p = r.precip_mm or 0; return VIOLET if p >= 2.5 else BLUE if p > 0 else "#8b8d98"
    t = r.temp_c if r.temp_c is not None else 25; return RED if t > 35 else AMBER if t >= 30 else TEAL if t >= 10 else BLUE
def wx_layers(metric, hi):
    import weather as WX
    t = WX.table(); layers = []
    if len(t):
        pts = []
        for r in t.itertuples():
            w = r.wave_m if r.wave_m is not None and r.wave_m == r.wave_m else None
            pts.append({"id": r.port_name, "lat": r.lat, "lon": r.lon, "color": _wxcolor(metric, r), "r": 4 + min(9, r.wind_ms / 2.2), "z": 1, "open": r.port_name,
                        "tip": f"<b>{r.port_name}</b> · {WX.WMO.get(r.wcode, '')}<br>wind {r.wind_ms:.1f} m/s ({r.wind_ms * 3.6:.0f} km/h), gusts {r.gust_ms or 0:.0f} m/s<br>waves {'-' if w is None else f'{w:.1f} m'} · rain {r.precip_mm or 0:.1f} mm/h · {r.temp_c:.0f} °C<br><i>real reading {r.ts[11:16]} UTC</i>"})
        layers.append({"type": "points", "id": "wx_ports", "pts": pts})
    else:
        w = Q("SELECT w.port_name, w.current_severity sev, w.wind_speed, w.wave_height, w.temperature, p.lat, p.lon FROM weather_risks w JOIN ports p USING(port_name)")
        layers.append({"type": "points", "id": "wx_ports", "pts": [{"id": r.port_name, "lat": r.lat, "lon": r.lon, "color": RED if r.sev == "High" else AMBER if r.sev == "Medium" else TEAL, "r": 4 + min(9, r.wind_speed / 8), "z": 1, "open": r.port_name, "tip": f"<b>{r.port_name}</b><br>wind {r.wind_speed:.0f} km/h · waves {r.wave_height:.1f} m<br><i>simulated, not a real reading</i>"} for r in w.itertuples()]})
    v = Q("SELECT v.shipment_id, v.lat, v.lon, v.route_name, s.origin_port o, s.dest_port d FROM vessels v JOIN shipments s USING(shipment_id)"); hs = set(hi)
    layers.append({"type": "points", "id": "wx_v", "pts": [{"id": r.shipment_id, "lat": r.lat, "lon": r.lon, "color": "#1f2430" if r.shipment_id in hs else "#6b7080", "r": 4.5 if r.shipment_id in hs else 3, "z": 2, "open": r.shipment_id, "tip": f"<b>{r.shipment_id}</b> {r.o} → {r.d}" + ("<br><b>in storm-force wind</b>" if r.shipment_id in hs else "")} for r in v.itertuples()]})
    layers.append({"type": "circles", "items": [{"lat": s["lat"], "lon": s["lon"], "r_m": float(s.get("r", 700)) * 1852, "color": RED, "tip": f"Storm cell · wind {s.get('wind', '?')} m/s"} for s in dom.storms()]})
    return layers
def weather(c, tab=None):
    import weather as WX
    p = c.get("params") or {}; metric = p.get("metric") if p.get("metric") in METRICS else "wind"; st = WX.status()
    r = (latest("weather_watch") or {}).get("out", {}); hi = r.get("vessels_high", []); w = Q("SELECT port_name, current_severity sev, wind_speed, wave_height, temperature, forecast FROM weather_risks")
    src = (f"Real · Open-Meteo, {st['ok']}/{st['total']} ports, updated {st['ts'][11:16]} UTC ({st['age_min']:.0f} min ago)" if st["live"] else "Simulated · Open-Meteo not reachable" + (f" ({st['err']})" if st["err"] else "") + ". Press Refresh to retry.")
    lg = list(METRICS[metric][1]) + [("Big dot = port (size = wind)", "#8b8d98"), ("Black dot = vessel in storm-force wind", "#1f2430"), ("Grey dot = other vessel", "#6b7080"), ("Red circle = storm cell", "#e5484d")]
    pick = {"t": "form", "id": "wx_pick", "fields": [{"name": "metric", "label": "Colour ports by", "type": "select", "options": list(METRICS), "value": metric}], "submit": "Show", "url": "page:weather", "title": None, "tone": "ghost", "inline": True}
    hot = w.sort_values("wind_speed", ascending=False)
    bl = [B.callout(src, "success" if st["live"] else "warning", "Weather data source"), hero(c, "weather_watch", "Weather risk agent", "Real wind, wave, rain and temperature from Open-Meteo for every port (refreshed every 20 min) plus injected storm cells. Vessels in High risk (wind > 15 m/s) get a re-route ticket; the system re-plans the voyage once it is approved."),
          B.kpis(("Vessels in High risk", len(hi), None, "Critical" if hi else None), ("Active storms", len(dom.storms())), ("Ports with weather data", len(w)), ("Ports in High risk", int((w.sev == "High").sum()), None, "Warning"), ("Data", "Real" if st["live"] else "Simulated", None, "Low" if st["live"] else "Warning")),
          pick, B.card(f"Port weather · coloured by {METRICS[metric][0].lower()} · click a port or vessel", B.map_(wx_layers(metric, hi), h=470, view={"center": [20, 60], "zoom": 2}, key="wx_map", legend=lg)),
          B.row(B.card("Strongest port winds (km/h)", B.chart(B.bar(hot.head(12).port_name, hot.head(12).wind_speed.round(0), horizontal=True, colors=[AMBER], sort=True), h=330, open={"bar": "y"}, key="wx_w")), B.card("Port weather risk levels", B.chart(B.pie({str(k): int(v) for k, v in w.sev.value_counts().items()}, colors={"High": RED, "Medium": AMBER, "Low": TEAL}), h=330, key="wx_d")))]
    if hi: bl.append(B.table(Q("SELECT shipment_id, lat, lon, route_name FROM vessels WHERE shipment_id IN (%s)" % ",".join("?" * len(hi[:50])), hi[:50]), ["shipment_id", B.num_col("lat", "lat", "num"), B.num_col("lon", "lon", "num"), "route_name"], title="Vessels in High-risk weather now · click to inspect", h=240, open={"col": "shipment_id"}, key="wx_hv"))
    bl.append(B.table(w.sort_values("wind_speed", ascending=False).head(60).rename(columns={"wind_speed": "wind km/h", "wave_height": "waves m", "temperature": "temp °C"}), ["port_name", B.pill_col("sev"), "wind km/h", "waves m", "temp °C", "forecast"], title="Port weather (real where the forecast says Open-Meteo live)", h=300, open={"col": "port_name"}, key="wx_t"))
    if can(c, "run"): bl.append(B.button("wx_ref", "Refresh real weather now", "/api/weather/refresh", "ghost", payload={}))
    bl.append(B.table(pd.DataFrame(dom.feed_status(), columns=["feed", "status"]), title="Data sources", h=190, key="wx_f"))
    if can(c, "storm"):
        PRESET_STORMS = {"Red Sea": (18.0, 40.0), "Arabian Sea": (16.0, 66.0), "Bay of Bengal": (14.0, 88.0), "South China Sea": (14.0, 114.0), "Mediterranean": (35.0, 18.0)}; bl.append(B.form("storm", [{"name": "area", "label": "Area", "type": "select", "options": list(PRESET_STORMS), "value": "Red Sea"}, {"name": "wind", "label": "Wind m/s", "type": "range", "min": 15, "max": 35, "value": 24}], "Inject storm", "/api/freight/storm", title="Inject a storm", sub="Adds a storm cell for testing the re-route loop; it does not change the real readings."))
    bl.append(ticket_block(c, "weather_watch", title="Open tickets from this agent", key="tk_wx")); return B.page("Weather Risk", "Agent 4 · real wind, waves, rain, storms", bl, live=10)

def margin(c, tab=None):
    q = Q("SELECT quote_id, customer_id, base_cost, fuel_surcharge fuel, customs_fee, insurance, final_price price, margin_pct margin, status FROM freight_quotes WHERE base_cost>0 ORDER BY created_at DESC, quote_id DESC LIMIT 600")
    bl = [hero(c, "quote_watch", "Margin & approvals agent", "Margin = (price − cost) ÷ price with tiered targets (Platinum 18%, Gold 20%, Silver/Bronze 22–24%). Quotes > $50,000 or < 10% margin wait for an approver."),
          B.kpis(("Average margin", f"{q.margin.mean():.1f}%"), ("Below 10% margin", int((q.margin < 10).sum()), None, "Warning"), ("Over $50,000", int((q.price > 50000).sum())), ("Revenue in quotes", f"${q.price.sum():,.0f}"))]
    sc = {s: [{"x": a.base_cost, "y": a.price, "label": a.quote_id} for a in q[q.status == s].head(250).itertuples()] for s in q.status.unique()}; cm = q.groupby("customer_id").margin.mean().round(1).sort_values().head(10)
    bl.append(B.row(B.card("Price vs base cost (click a dot)", B.chart(B.scatter(sc, "base cost", "price", colors={"Approved": TEAL, "Pending Approval": AMBER, "On Hold": RED, "Rejected": "#8b8d98"}), h=330, open={"scatter": True}, key="mg_s")), B.card("Lowest-margin customers", B.chart(B.bar(cm.index, cm.values, horizontal=True, colors=[AMBER]), h=330, key="mg_c"))))
    if len(q):
        sel = (c.get("params") or {}).get("q") or q.quote_id.iloc[0]; r = q[q.quote_id == sel]; r = r.iloc[0] if len(r) else q.iloc[0]; cost = r.base_cost + r.fuel + r.customs_fee + r.insurance
        bl.append({"t": "form", "id": "mg_pick", "fields": [{"name": "q", "label": "Cost build-up for quote", "type": "select", "options": q.quote_id.tolist()[:200], "value": r.quote_id}], "submit": "Show", "url": "page:margin", "title": None, "tone": "ghost", "inline": True})
        bl.append(B.card(f"{r.quote_id}: how the price is built", B.chart(B.waterfall(["Base (ML)", "Fuel 12%", "Customs", "Insurance", "Margin"], [r.base_cost, r.fuel, r.customs_fee, r.insurance, r.price - cost]), h=300, key="mg_w")))
    bl.append(ticket_block(c, "quote_watch", ["quote_approval", "margin_review"], title="Margin actions", key="tk_mg")); return B.page("Margin", "Agent 5 · margin and pricing tiers", bl, live=10)

def customs(c, tab="customs"):
    tabs = [{"id": "customs", "label": "Customs & tariff"}, {"id": "docs", "label": "Documents (OCR)"}]
    if tab == "docs":
        ddir = os.path.join(dom.DATA_DIR, "docs"); files = sorted(os.listdir(ddir), reverse=True) if os.path.isdir(ddir) else []
        bl = [B.callout("PDFs are generated by the Document agent for every quote (Bill of Lading, Packing List). Upload a document to read its fields and attach it to the matching quote.", "info"), B.kpis(("Generated documents", len(files)))]
        bl += [B.button("dl_" + f, "Download " + f, f"/api/doc/{f}", "ghost", payload={"download": True}) for f in files[:10]]
        bl.append(B.form("readdoc", [{"name": "file", "label": "PDF or TXT", "type": "file"}], "Read document", "/api/freight/readdoc", title="Read an uploaded document (OCR / text extraction)", tone="primary")); return B.page("Customs", "Agent 6 · documents", bl, tabs, live=0)
    h = Q("SELECT shipment_id, hs_code, origin_port, dest_port, carrier FROM shipments WHERE status='Customs Hold' LIMIT 200"); rules = Q("SELECT * FROM customs_rules ORDER BY chapter"); rows = []
    for r in h.head(30).itertuples():
        ch, docs, rs, duty, goods = dom._required_docs(r.hs_code); miss = [d for d in docs if d not in dom._attached(r.shipment_id)]; rows.append({"shipment": r.shipment_id, "hs": r.hs_code, "goods": goods, "duty_pct": duty, "missing": ", ".join(miss), "route": f"{r.origin_port} → {r.dest_port}"})
    bl = [hero(c, "customs_watch", "Customs & tariff agent", "Requirements come from the customs_rules table by HS chapter. A hold lifts as soon as every required document is attached: the quote re-runs and the shipment clears."),
          B.kpis(("Shipments on hold", len(h), None, "Warning" if len(h) else None), ("Quotes on hold", int(Q("SELECT COUNT(*) n FROM freight_quotes WHERE status='On Hold'").n[0])), ("Rules in force", len(rules))),
          B.table(rows, ["shipment", "hs", "goods", B.num_col("duty_pct", "duty %", "num"), "missing", "route"], title="Held shipments and what each is missing · click a row", h=300, open={"col": "shipment"}, key="cu_h"), B.table(rules, list(rules.columns), title="Customs rules", h=230, key="cu_r")]
    if can(c, "resolve") or can(c, "quote"):
        held = Q("SELECT shipment_id ref FROM shipments WHERE status='Customs Hold' UNION SELECT quote_id FROM freight_quotes WHERE status='On Hold' LIMIT 200").ref.tolist(); alld = _docs_all()
        if held and alld: bl.append(B.form("attach", [{"name": "ref", "label": "Shipment or quote on hold", "type": "select", "options": held, "value": held[0]}, {"name": "doc", "label": "Document", "type": "select", "options": alld, "value": alld[0]}], "Attach document", "/api/freight/attach", title="Attach a document", sub="The Customs agent re-checks on its next cycle; quotes re-run immediately."))
        elif held and not alld: bl.append(B.callout("Document requirements are not available yet. Reload the page after initialization.", "warning"))
    if can(c, "view"): bl.append(ticket_block(c, "customs_watch", title="Open tickets from this agent", key="tk_cu"))
    return B.page("Customs", "Agent 6 · rules, holds, documents", bl, tabs, live=12)

PAGES = {"route": route, "quotes": quotes, "carriers": carriers, "weather": weather, "margin": margin, "customs": customs}
