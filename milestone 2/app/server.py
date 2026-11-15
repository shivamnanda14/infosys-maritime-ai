"""Web server: FastAPI JSON API + server-sent events + the single-page front end. Models live on the GPU in this process; the simulator and agent cycles run in worker.py."""
import sqlite3, os, sys, io, re, csv, json, time, asyncio, subprocess, threading, importlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from config import KIND, DB_PATH
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import numpy as np
import gpu, qa as QA, analyst as AN, live_engine as LE, entities as EN, blocks as B
import views_core as VC
import auth_service
import rbac
import mailer
import copilot_engine
dom = importlib.import_module("domain_franchise" if KIND == "Franchise" else "domain_freight")
V = importlib.import_module("views_franchise" if KIND == "Franchise" else "views_freight")
HERE = os.path.dirname(os.path.abspath(__file__)); STATIC = os.path.join(HERE, "static"); STATIC_DIR = STATIC
app = FastAPI(title=f"{V.NAME} Platform", docs_url=None, redoc_url=None, openapi_url=None) if os.environ.get("PUBLIC_DOCS") != "1" else FastAPI(title=f"{V.NAME} Platform"); _worker = None; _ready = {"db": False}
import hardening; hardening.install(app, KIND)

@app.middleware("http")
async def sec(request, call_next):
    r = await call_next(request); r.headers["X-Content-Type-Options"] = "nosniff"; r.headers["Referrer-Policy"] = "same-origin"; r.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else r.headers.get("Cache-Control", "public, max-age=300"); return r

def _boot():
    # The ocean router requires the bundled world coastline, separately from ECharts.
    # Restore either missing asset before any Route page calculation can start.
    vendor_dir = os.path.join(STATIC_DIR, "vendor")
    required_vendor = [os.path.join(vendor_dir, x) for x in ("echarts.min.js", "world.topo.json")]
    if any(not os.path.isfile(x) or os.path.getsize(x) == 0 for x in required_vendor):
        import _vendor_bundle
    missing_vendor = [x for x in required_vendor if not os.path.isfile(x) or os.path.getsize(x) == 0]
    if missing_vendor:
        raise RuntimeError("Missing required bundled assets: " + ", ".join(missing_vendor))
    from db import init_db; from seed_data import seed_all
    init_db(); auth_service.init_sessions(); seed_all(); LE.init_live_tables()
    auth_service.seed_admin_account()
    dom.ensure_schema()
    _ready["db"] = True
@app.on_event("startup")
def startup():
    global _worker
    _boot()
    if os.environ.get("NO_WORKER") != "1":
        env = {**os.environ, "APP_KIND": KIND}; _worker = subprocess.Popen([sys.executable, os.path.join(HERE, "worker.py")], env=env, cwd=HERE)
@app.on_event("shutdown")
def shutdown():
    if _worker:
        try: _worker.terminate()
        except Exception: pass

# ------------------------------------------------------------------ auth + context
def user_of(request: Request):
    auth_header = request.headers.get("Authorization") or ""
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid token. Please sign in again.")
    username = payload.get("sub")
    user = auth_service.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User account not found.")
    if user.get("locked"):
        raise HTTPException(status_code=401, detail="Account locked. Contact administrator.")
    if payload.get("uid") != user["id"] or payload.get("sv") != auth_service.session_version(user["id"]):
        raise HTTPException(401, "Session expired. Sign in again.")
    return user

def ctx(u, params=None):
    return {
        "dom": dom,
        "kind": KIND,
        "role": u["role"],
        "email": u["email"],
        "user": u,
        "customer_id": u.get("customer_id"),
        "scope": None,
        "params": params or {},
    }

def need(c, cap):
    role = c.get("role")
    if not rbac.check_permission(role, cap):
        raise HTTPException(status_code=403, detail=f"Permission denied: role '{role}' lacks '{cap}' privilege.")
    return None

def menu_for(role):
    return rbac.menu_for_role(role)

def ok(msg="Done", **kw): return {"ok": True, "msg": msg, **kw}
def bad(msg, **kw): return JSONResponse({"ok": False, "msg": msg, **kw}, status_code=400)

# ------------------------------------------------------------------ auth routes
@app.post("/api/auth/signup")
def auth_signup(d: dict):
    success, msg = auth_service.signup_user(
        d.get("username"),
        d.get("email"),
        d.get("password"),
        d.get("confirm_password"),
        d.get("question"),
        d.get("answer"),
        d.get("role", "Customer"),
    )
    if not success:
        return bad(msg)
    sent, cooldown, notice = auth_service.request_email_verification(d.get("email"))
    return ok(notice if sent else msg + " " + notice, email_verification_pending=True,
              verification_sent=bool(sent), retry_after_seconds=cooldown)

@app.post("/api/auth/verify-email/request")
def auth_verify_email_request(d: dict):
    success, wait_sec, msg = auth_service.request_email_verification(d.get("email"))
    if not success:
        return JSONResponse({"ok": False, "msg": msg, "retry_after_seconds": wait_sec}, status_code=429 if wait_sec else 400)
    return ok(msg, retry_after_seconds=wait_sec)

@app.post("/api/auth/verify-email/confirm")
def auth_verify_email_confirm(d: dict):
    success, msg = auth_service.verify_email_code(d.get("email"), d.get("code"))
    if not success:
        return bad(msg)
    return ok(msg)

@app.post("/api/auth/login")
def auth_login(d: dict):
    result, retry_after, msg = auth_service.authenticate_user(d.get("identity"), d.get("password"), d.get("role"))
    if not result:
        status = 423 if msg == auth_service.LOCKED_MESSAGE else (429 if retry_after else 401)
        return JSONResponse({"ok": False, "msg": msg, "retry_after_seconds": retry_after}, status_code=status)
    u = result["user"]
    return ok(
        msg,
        token=result["token"],
        user={
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "role": u["role"],
            "customer_id": u.get("customer_id"),
        },
    )

@app.post("/api/auth/forgot")
@app.post("/api/auth/forgot/request_otp")
def auth_forgot_otp(d: dict):
    success, wait_sec, msg = auth_service.request_password_reset_otp(d.get("email"))
    if not success:
        return JSONResponse({"ok": False, "msg": msg, "retry_after_seconds": wait_sec}, status_code=400 if wait_sec == 0 else 429)
    return ok(msg, retry_after_seconds=wait_sec)

@app.post("/api/auth/forgot/verify_otp")
def auth_forgot_verify_otp(d: dict):
    success, grant, msg = auth_service.verify_password_reset_otp(d.get("email"), d.get("code"))
    if not success:
        return bad(msg)
    return ok(msg, grant=grant)

@app.post("/api/auth/forgot/question")
def auth_forgot_question(d: dict):
    q, err = auth_service.get_user_security_question(d.get("identity"))
    if not q:
        return bad(err or "Security question unavailable for this account.")
    return ok(err or "Question found", question=q, locked=bool(err))

@app.post("/api/auth/forgot/verify_answer")
def auth_forgot_verify_answer(d: dict):
    success, grant, msg = auth_service.verify_user_security_answer(d.get("identity"), d.get("answer"))
    if not success:
        return bad(msg)
    return ok(msg, grant=grant)

@app.post("/api/auth/reset")
def auth_reset(d: dict):
    success, msg = auth_service.reset_user_password(
        d.get("identity"),
        d.get("grant"),
        d.get("new_password"),
        d.get("confirm_password"),
    )
    if not success:
        return bad(msg)
    return ok(msg)

@app.post("/api/auth/unblock")
def auth_unblock(d: dict, request: Request):
    u = user_of(request)
    if u.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Administrator authentication required")
    success, msg = auth_service.unblock_user_account(u, d.get("identity"))
    if not success:
        return bad(msg)
    return ok(msg)


# ------------------------------------------------------------------ Admin Dashboard Routes (Stage 4)
@app.get("/api/admin/users")
def api_admin_users(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    return {"ok": True, "users": auth_service.admin_list_users()}

@app.get("/api/admin/metrics")
def api_admin_metrics(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    return {"ok": True, **auth_service.admin_get_metrics()}

@app.get("/api/admin/activity")
def api_admin_activity(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    return {"ok": True, "activity": auth_service.admin_get_activity_log(50)}

@app.post("/api/admin/users/create")
async def api_admin_create_user(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    d = await request.json()
    ok_res, msg = auth_service.admin_create_user(
        u["username"], d.get("username"), d.get("email"), d.get("password"), d.get("role"), d.get("customer_id")
    )
    if not ok_res:
        return bad(msg)
    return ok(msg)

@app.post("/api/admin/users/role")
async def api_admin_change_role(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    d = await request.json()
    ok_res, msg = auth_service.admin_change_role(u["username"], d.get("target_id"), d.get("role"))
    if not ok_res:
        return bad(msg)
    return ok(msg)

@app.post("/api/admin/users/lock")
async def api_admin_lock_user(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    d = await request.json()
    ok_res, msg = auth_service.admin_set_lock(u["username"], d.get("target_id"), True)
    if not ok_res:
        return bad(msg)
    return ok(msg)

@app.post("/api/admin/users/unlock")
async def api_admin_unlock_user(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    d = await request.json()
    ok_res, msg = auth_service.admin_set_lock(u["username"], d.get("target_id"), False)
    if not ok_res:
        return bad(msg)
    return ok(msg)

@app.post("/api/admin/users/delete")
async def api_admin_delete_user(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")
    d = await request.json()
    ok_res, msg = auth_service.admin_delete_user(u["username"], d.get("target_id"))
    if not ok_res:
        return bad(msg)
    return ok(msg)

@app.post("/api/admin/link_customer")
async def api_admin_link_customer(request: Request):
    u = user_of(request); c = ctx(u); need(c, "users")  # Enforces admin RBAC
    d = await request.json()

    # Accepts a plain id or the "ID - Name" dropdown format
    try:
        uid = int(str(d.get("user_id", "0")).split(" - ")[0])
    except ValueError:
        return bad("Invalid user selected.")
    cid = str(d.get("customer_id", "")).split(" - ")[0]

    success, msg = auth_service.admin_link_customer(u["username"], uid, cid)
    if not success:
        return bad(msg)
    return ok(msg, refresh=True)

# ------------------------------------------------------------------ Profile routes (Stage 3)
@app.post("/api/profile/username")
async def profile_change_username(request: Request):
    u = user_of(request)
    d = await request.json()
    ok_res, msg, data = auth_service.change_username(u["id"], d.get("new_username"), d.get("current_password"))
    if not ok_res:
        return bad(msg)
    return ok(msg, token=data["token"], user=data["user"])

@app.post("/api/profile/password")
async def profile_change_password(request: Request):
    u = user_of(request)
    d = await request.json()
    ok_res, msg = auth_service.change_password(u["id"], d.get("current_password"), d.get("new_password"), d.get("confirm_password"))
    if not ok_res:
        return bad(msg)
    return ok(msg)


@app.get("/api/public")
def public():
    s = LE.get_state("boot", {}) if _ready["db"] else {}
    return {
        "kind": KIND,
        "name": V.NAME,
        "stage": (s or {}).get("stage", "starting"),
        "gpu": {"cuda": False, "name": None},
        "questions": QUESTIONS if "QUESTIONS" in globals() else auth_service.QUESTIONS,
        "email_enabled": mailer.configured(),
        "roles": auth_service.ALLOWED_SIGNUP_ROLES,
        "demo": [],
    }

@app.get("/api/me")
def me(request: Request):
    u = user_of(request)
    menu_items = menu_for(u["role"])
    caps = list(rbac.ROLE_CAPS.get(u["role"], set()))
    return {
        "ok": True,
        "user": {
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "role": u["role"],
            "customer_id": u.get("customer_id"),
            "created_at": u.get("created_at"),
            "last_login": u.get("last_login"),
        },
        "kind": KIND,
        "name": V.NAME,
        "menu": menu_items,
        "caps": caps,
        "scope": None,
        "langs": ["English"],
        "questions": [],
    }
# ------------------------------------------------------------------ live pulse
def pulse():
    rt = LE.get_state("runtime", {}) or {}; boot = LE.get_state("boot", {}) or {}; d = VC.decision()
    oa = B.Q("SELECT status, severity, COUNT(*) n FROM agent_actions WHERE status IN ('open','proposed') GROUP BY status, severity")
    n = lambda st, sv=None: int(oa[(oa.status == st) & ((oa.severity == sv) if sv else True)].n.sum()) if len(oa) else 0
    return {"stage": boot.get("stage", "starting"), "ticks": rt.get("ticks", 0), "cycles": rt.get("cycles", 0), "last_cycle": rt.get("last_cycle"), "health": d["score"] if d else None, "risk": d["risk"] if d else None, "dec": d["id"] if d else 0,
            "open": n("open"), "critical": n("open", "Critical"), "proposed": 0, "gpu": {"cuda": True, "name": "", "used": 0, "total": 0, "llm": "off", "llm_name": "", "llm_done": 0, "llm_total": 0}, "worker_alive": bool(rt.get("last_cycle"))}
@app.get("/api/pulse")
def pulse_http(request: Request): user_of(request); return pulse()
@app.get("/api/stream")
async def stream(request: Request):
    user_of(request)
    async def gen():
        last = None; t0 = time.time()
        while True:
            if await request.is_disconnected(): break
            try: p = await asyncio.to_thread(pulse)
            except Exception as e: p = {"error": str(e)}
            k = json.dumps(p, sort_keys=True, default=str)
            if k != last or time.time() - t0 > 10: last = k; t0 = time.time(); yield f"data: {k}\n\n"
            await asyncio.sleep(1.5)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ------------------------------------------------------------------ pages
_TABS = {}
def _tabs_of(c, f):
    if f not in _TABS: _TABS[f] = f(c, None).get("tabs")
    return _TABS[f]
def _page(c, pid, tab):
    if pid == "copilot":
        examples = copilot_engine.get_role_suggestions(c.get("role", "Customer"))
        return B.page("AI Copilot", "Ask about your data in plain English. Answers are exact database queries.", [{"t": "chat", "examples": examples, "langs": ["English"]}], [], live=0)
    if pid == "profile":
        u = c.get("user") or {}
        return {
            "title": "My Profile",
            "sub": "Manage account credentials and security settings",
            "tabs": None,
            "actions": [],
            "blocks": [
                {"t": "profile_page", "user": {
                    "username": u.get("username"),
                    "email": u.get("email"),
                    "role": u.get("role"),
                    "created_at": u.get("created_at"),
                    "last_login": u.get("last_login") or "First login session",
                    "customer_id": u.get("customer_id") or "None"
                }}
            ],
            "live": 0
        }
    if pid == "admin":
        if c.get("role") != "Admin":
            raise HTTPException(403, "Access denied: Admin role required.")
        return {
            "title": "Admin Dashboard",
            "sub": "Platform user governance, access control, and audit logs",
            "tabs": None,
            "actions": [],
            "blocks": [
                {
                    "t": "admin_page",
                    "metrics": auth_service.admin_get_metrics(),
                    "users": auth_service.admin_list_users(),
                    "activity": auth_service.admin_get_activity_log(50),
                    "customers": B.Q("SELECT customer_id, name FROM customers ORDER BY customer_id").to_dict("records"),
                    "current_admin": c.get("user", {}).get("username")
                }
            ],
            "live": 0
        }
    f = V.PAGES.get(pid)
    if not f: raise HTTPException(404, "unknown page")
    o = f(c, tab); _TABS[f] = o.get("tabs"); return o
@app.get("/api/page/{pid}")
def page(pid: str, request: Request, tab: str = "", p: str = ""):
    u = user_of(request)
    if pid not in rbac.ROLE_MENU.get(u["role"], set()):
        raise HTTPException(403, f"Access denied: '{pid}' page is not accessible for role '{u['role']}'")
    c = ctx(u, json.loads(p) if p else {})
    t = time.time(); out = _page(c, pid, tab or None); out["id"] = pid; out["ms"] = round((time.time() - t) * 1000); return JSONResponse(B.clean(out))
@app.get("/api/detail/{eid:path}")
def detail(eid: str, request: Request):
    u = user_of(request)
    if not rbac.can_access_entity(u["role"], eid, u.get("customer_id")):
        raise HTTPException(403, f"Access denied: role '{u['role']}' is not authorized to view entity '{eid}'.")
    c = ctx(u)
    return JSONResponse(B.clean(V.detail(c, eid)))

# ------------------------------------------------------------------ tickets, cycles, policy
@app.post("/api/run_cycle")
def run_cycle(request: Request):
    u = user_of(request); c = ctx(u); need(c, "run"); need(c, "users"); t = time.time(); LE.run_cycle(dom, "manual", ""); LE.audit(u["email"], "manual_cycle", "all"); return ok(f"Agents finished in {time.time() - t:.1f}s")
@app.post("/api/run_agent")
async def run_agent(request: Request):
    u = user_of(request); c = ctx(u); need(c, "run"); a = (await request.json()).get("agent")
    if u["role"] == "Operations Manager" and a not in {"route_watch", "weather_watch", "customs_watch"}:
        raise HTTPException(403, "This agent is outside your role permissions.")
    if a not in dom.AGENTS: raise HTTPException(404, "unknown agent")
    await asyncio.to_thread(_run_one, a); LE.audit(u["email"], "manual_agent", a); return ok(f"{a} re-ran")
def _run_one(agent):
    cid = time.strftime("%m%d-%H%M%S") + "-page"; t = time.time(); s = {"cycle_id": cid, "trigger": "page", "request": "", "queue": [], "results": {}}
    if agent == "digest":
        for a in ("outlet", "inventory", "staff", "marketing", "audit"): s["results"][a] = dom.AGENTS[a](s)
    res = dom.AGENTS[agent](s); LE._log_run(cid, "page", res, int((time.time() - t) * 1000)); s["results"][agent] = res; LE.act(dom, {"actions": res.actions}, cid, {agent: res})

# ------------------------------------------------------------------ admin users

# ------------------------------------------------------------------ digital twin

# ------------------------------------------------------------------ data feeds

# ------------------------------------------------------------------ Franchise actions
@app.post("/api/franchise/review")
async def fr_review(request: Request):
    import uuid; u = user_of(request); c = ctx(u); d = await request.json(); tx = str(d.get("comment", "")).strip()
    if not tx: return bad("Write a comment first")
    src = "eng_Latn"; en = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d -]{8,}\d", "[removed]", tx)
    try: from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer; sc = SentimentIntensityAnalyzer().polarity_scores(en)["compound"]
    except Exception: sc = (int(d["rating"]) - 3) / 2
    rt = int(d["rating"])
    with LE._DB_LOCK, LE.conn() as cn: cn.execute("INSERT INTO feedback(feedback_id,outlet_id,rating,comment,date,sentiment_score) VALUES(?,?,?,?,?,?)", ("FB-U" + uuid.uuid4().hex[:10], d["outlet"], rt, en, datetime.date.today().isoformat(), .6 * (rt - 3) / 2 + .4 * sc))
    LE.emit("review", d["outlet"], {"rating": rt}); return ok(f"Stored for {d['outlet']} (sentiment {sc:+.2f}{', translated from ' + src if src != 'eng_Latn' else ''}). The Sentiment agent includes it in its next cycle.", refresh=True)
@app.post("/api/franchise/audit")
async def fr_audit(request: Request):
    import uuid; u = user_of(request); c = ctx(u); need(c, "resolve"); d = await request.json(); sc = int(d["score"])
    with LE._DB_LOCK, LE.conn() as cn: cn.execute("INSERT INTO audits(audit_id,outlet_id,audit_date,score,violations,category,status,notes) VALUES(?,?,?,?,?,?,?,?)", ("AUD-U" + uuid.uuid4().hex[:10], d["outlet"], datetime.date.today().isoformat(), sc, int((100 - sc) / 6), d["category"], "Pass" if sc >= 80 else "Warning" if sc >= 60 else "Fail", d.get("notes", "")))
    LE.emit("audit", d["outlet"], {"score": sc}); LE.audit(u["email"], "audit_logged", d["outlet"], str(sc)); await asyncio.to_thread(_run_one, "audit"); return ok("Saved and evaluated by the Audit agent.", refresh=True)

# ------------------------------------------------------------------ Freight actions
@app.post("/api/freight/quote")
async def fq_quote(request: Request):
    u = user_of(request); c = ctx(u); need(c, "quote"); d = await request.json()
    if d["o"] == d["d"]: return bad("Origin and destination must differ.")
    rid = dom.submit_request(d["o"], d["d"], d["cargo"], float(d["weight"]), d["hs"], d["customer"], "English", d.get("docs") or []); await asyncio.to_thread(dom.run_quote, rid); LE.audit(u["email"], "quote_created", str(rid), f"{d['o']}->{d['d']}")
    return ok("Quote generated", blocks=B.clean(V.quote_result(rid)))
@app.post("/api/freight/storm")
async def fq_storm(request: Request):
    PRESET_STORMS = {"Red Sea": (18.0, 40.0), "Arabian Sea": (16.0, 66.0), "Bay of Bengal": (14.0, 88.0), "South China Sea": (14.0, 114.0), "Mediterranean": (35.0, 18.0)}; u = user_of(request); c = ctx(u); need(c, "storm"); d = await request.json() if request.headers.get("content-length", "0") not in ("0", "2") else {}
    la, lo = PRESET_STORMS.get(d.get("area") or "Red Sea"); dom.inject_storm(la, lo, wind=float(d.get("wind", 24))); LE.audit(u["email"], "inject_storm", d.get("area", "Red Sea")); return ok("Storm injected. The weather agent will propose re-routes on its next cycle.", refresh=True)
@app.post("/api/freight/reroute")
async def fq_reroute(request: Request):
    u = user_of(request); c = ctx(u); need(c, "reroute"); j = await request.json(); sid = j["shipment"]; opt = j.get("opt")
    idx = int(str(opt).split(".")[0]) - 1 if opt else None; act = {"type": "reroute", "target": sid}
    if idx is not None: act["opt_label"] = str(opt).split(" · ", 1)[-1]; act["opt_idx"] = idx
    with LE._DB_LOCK, LE.conn() as cn: note = dom.apply(act, cn)
    LE.audit(u["email"], "manual_reroute", sid, note); return ok(note or "no change", refresh=True)
@app.post("/api/freight/attach")
async def fq_attach(request: Request):
    u = user_of(request); c = ctx(u); need(c, "customs_edit")
    d = await request.json(); dom.attach_doc(d["ref"], d["doc"], u["email"]); LE.audit(u["email"], "doc_attached", d["ref"], d["doc"]); return ok("Attached. Quotes re-run immediately; shipments clear on the next customs cycle.", refresh=True)
@app.post("/api/freight/readdoc")
async def fq_readdoc(request: Request, file: UploadFile = File(...)):
    u = user_of(request); c = ctx(u); need(c, "customs_edit"); data = await file.read(); txt = ""
    try:
        if file.filename.lower().endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf: txt = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        else: txt = data.decode("utf-8", errors="ignore")
    except Exception as e: return bad(f"Could not read the file: {e}")
    hs = re.findall(r"HS[- ]?\d{2,8}", txt); q = re.findall(r"QTE-L\d+", txt); wt = re.findall(r"(\d+(?:\.\d+)?)\s*(?:t|tons|kg)\b", txt)
    return ok("Read", blocks=[B.table([{"field": "HS code", "value": ", ".join(dict.fromkeys(hs)) or "-"}, {"field": "Quote reference", "value": ", ".join(dict.fromkeys(q)) or "-"}, {"field": "Weights", "value": ", ".join(wt[:3]) or "-"}], ["field", "value"], title="Fields found", h=170, key="ocr"), B.md("```\n" + txt[:2500] + "\n```")])

# ------------------------------------------------------------------ language, knowledge base

# ------------------------------------------------------------------ Copilot (agents first, then the GPU LLM; NLLB for every language) + executive brief
def _sse(ev, **kw): return f"data: {json.dumps({'ev': ev, **kw}, default=str)}\n\n"
SYSTEM = "You are the operations copilot of an agentic platform. Answer ONLY from the EVIDENCE. Quote numbers exactly as given, never invent any. Be concise: a one-line answer, then up to 5 short bullets with the entity ids. If the evidence does not answer, say so. When you use a numbered source, cite it as [1], [2]."
_BRIEF = {}
def _chat_db():
    c = sqlite3.connect(DB_PATH, timeout=30); c.execute("PRAGMA journal_mode=WAL;"); c.execute("CREATE TABLE IF NOT EXISTS copilot_chats(id TEXT PRIMARY KEY, email TEXT, title TEXT, ts TEXT, data TEXT)"); c.execute("CREATE INDEX IF NOT EXISTS ix_chat_email ON copilot_chats(email, ts)"); return c
@app.get("/api/chats")
async def chats_list(request: Request):
    u = user_of(request)
    with _chat_db() as c: rows = c.execute("SELECT id, title, ts FROM copilot_chats WHERE email=? ORDER BY ts DESC LIMIT 60", (u["email"],)).fetchall()
    return {"ok": True, "chats": [{"id": r[0], "title": r[1], "ts": r[2]} for r in rows]}
@app.get("/api/chats/{cid}")
async def chats_get(cid: str, request: Request):
    u = user_of(request)
    with _chat_db() as c: r = c.execute("SELECT title, data FROM copilot_chats WHERE id=? AND email=?", (cid, u["email"])).fetchone()
    if not r: raise HTTPException(404, "chat not found")
    return {"ok": True, "title": r[0], "msgs": json.loads(r[1])}
@app.post("/api/chats/save")
async def chats_save(request: Request):
    u = user_of(request); d = await request.json(); cid = re.sub(r"[^a-zA-Z0-9_-]", "", str(d.get("id") or ""))[:40] or ("c" + str(int(time.time() * 1000))); msgs = d.get("msgs") or []
    if not isinstance(msgs, list) or not msgs: return bad("nothing to save")
    msgs = [{"role": m.get("role"), "text": str(m.get("text", ""))[:20000], "en": (str(m["en"])[:20000] if m.get("en") else None), "lang": m.get("lang"), "sql": str(m.get("sql") or "")[:1500]} for m in msgs[-80:]]
    title = next((m["text"] for m in msgs if m["role"] == "user"), "Chat")[:70]; now = datetime.datetime.now().isoformat(timespec="seconds")
    with _chat_db() as c:
        o = c.execute("SELECT email FROM copilot_chats WHERE id=?", (cid,)).fetchone()
        if o and o[0] != u["email"]: raise HTTPException(403, "not your chat")
        c.execute("INSERT OR REPLACE INTO copilot_chats VALUES(?,?,?,?,?)", (cid, u["email"], title, now, json.dumps(msgs)))
    return {"ok": True, "id": cid}
@app.delete("/api/chats/{cid}")
async def chats_del(cid: str, request: Request):
    u = user_of(request)
    with _chat_db() as c: c.execute("DELETE FROM copilot_chats WHERE id=? AND email=?", (cid, u["email"]))
    return {"ok": True}
@app.post("/api/weather/refresh")
async def wx_refresh(request: Request):
    u = user_of(request); c = ctx(u); need(c, "run")
    if KIND != "Freight": raise HTTPException(404)
    import weather as WX; n, msg = await asyncio.to_thread(WX.refresh); LE.audit(u["email"], "weather_refresh", "ports", msg)
    return ok(("Real weather updated: " if n else "Could not reach Open-Meteo, simulated values stay: ") + msg, refresh=True)

# ------------------------------------------------------------------ reports, exports, profile, invitations


@app.get("/api/health")
def health(): return {"ok": True, "gpu": gpu.status()}
@app.get("/")
def index(): return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-store"})
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ------------------------------------------------------------------ AI Copilot (SQL only: greetings + exact database answers)
@app.post("/api/copilot")
async def copilot(request: Request):
    u = user_of(request); c = ctx(u); need(c, "copilot")
    d = await request.json(); q = str(d.get("q", "")).strip()[:800]
    def gen():
        t0 = time.time()
        # Stage 5 Copilot Engine with strict RBAC, Customer data scoping, and parameterized queries
        res = copilot_engine.ask_copilot(q, u.get("role", "Customer"), u.get("customer_id"))
        if res.get("status") != "out_of_scope":
            if res.get("sql"):
                yield _sse("exact", sql=res["sql"], rows=res.get("row_count", 0))
            yield _sse("final", text=res.get("text", ""), sql=res.get("sql", ""), rows=res.get("row_count", 0), ms=res.get("ms", round((time.time() - t0) * 1000)))
            yield _sse("done")
            return

        yield _sse("final", text=res.get("text", ""), sql="", rows=0, ms=round((time.time()-t0)*1000))
        yield _sse("done")
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})