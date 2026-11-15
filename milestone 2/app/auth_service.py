"""Authentication, JWT sessions, lockout ladders and password policies for FreightQuote AI.
Ported directly from Milestone 1 with exact behavior, limits, and wording.
"""
import re
import json
import time
import hmac
import hashlib
import secrets
import datetime as dt
import unicodedata

try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False

try:
    import jwt
    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False

from db import get_conn
import config
import mailer

EMAIL_RE = re.compile(
    r"^[A-Za-z]{2,}[A-Za-z0-9._%+\-]*@[A-Za-z]{2,}[A-Za-z0-9\-]*(?:\.[A-Za-z]{2,}[A-Za-z0-9\-]*)+$"
)
QUESTIONS = [
    "What was the name of your first school?",
    "In which city were you born?",
    "What was the name of your first pet?",
    "What is the middle name of your oldest sibling?",
]
GENERIC_LOGIN_ERROR = "Invalid username/email or password."
LOCKED_MESSAGE = "Account locked. Contact the administrator to unlock it."
OTP_TTL = 300  # 5 minutes
MAX_OTP_REQUESTS = 5
MAX_OTP_FAILURES = 5

ALLOWED_SIGNUP_ROLES = ["Customer"]

def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def valid_email(value):
    return (
        isinstance(value, str)
        and len(value.strip()) <= 254
        and bool(EMAIL_RE.fullmatch(value.strip()))
    )

def password_errors(password):
    issues = []
    if len(password) < 8:
        issues.append("at least 8 characters")
    if len(password.encode("utf-8")) > 72:
        issues.append("no more than 72 UTF-8 bytes")
    if not re.search(r"[A-Z]", password):
        issues.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        issues.append("one lowercase letter")
    if not re.search(r"[0-9]", password):
        issues.append("one number")
    if not any(
        not ch.isalnum()
        and not ch.isspace()
        and not unicodedata.category(ch).startswith("C")
        for ch in password
    ):
        issues.append("one special symbol (spaces do not count)")
    if any(ch.isspace() or unicodedata.category(ch).startswith("C") for ch in password):
        issues.append("no whitespace or invisible characters")
    return issues

def clean_answer(value):
    """Ignore case and surrounding whitespace; reject invisible-only answers."""
    value = unicodedata.normalize("NFKC", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    return value.strip().casefold()

def answer_error(value):
    cleaned = clean_answer(value)
    if not cleaned or not any(ch.isalnum() for ch in cleaned):
        return "Enter a security answer containing a letter or number."
    if len(cleaned.encode("utf-8")) > 72:
        return "Security answer is too long (maximum 72 UTF-8 bytes)."
    return None

def hashed(text):
    if _HAS_BCRYPT:
        try:
            return bcrypt.hashpw(text.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        except Exception:
            pass
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", text.encode("utf-8"), salt.encode("ascii"), 100000).hex()
    return f"pbkdf2:{salt}:{dk}"

def matches(text, saved):
    if not saved or not isinstance(saved, str):
        return False
    if saved.startswith("$2"):
        if _HAS_BCRYPT:
            try:
                return bcrypt.checkpw(text.encode("utf-8"), saved.encode("ascii"))
            except Exception:
                return False
        return False
    if saved.startswith("pbkdf2:"):
        try:
            parts = saved.split(":")
            if len(parts) == 3:
                salt = parts[1]
                expected_dk = parts[2]
                computed = hashlib.pbkdf2_hmac("sha256", text.encode("utf-8"), salt.encode("ascii"), 100000).hex()
                return hmac.compare_digest(computed, expected_dk)
        except Exception:
            return False
    return False

def otp_digest(code, salt, secret=None, purpose="reset"):
    sec = secret or config.JWT_SECRET
    msg = f"{purpose}:{salt}:{code}".encode("utf-8")
    return hmac.new(sec.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    import base64
    rem = len(s) % 4
    if rem:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s)

def issue_token(user, expires_in=7200):
    now = int(time.time())
    payload = {
        "sub": user["username"],
        "email": user["email"],
        "role": user["role"],
        "customer_id": user.get("customer_id"),
        "iat": now,
        "exp": now + expires_in,
        "jti": secrets.token_hex(16),
        "uid": user["id"],
        "sv": session_version(user["id"]),
    }
    if _HAS_JWT:
        try:
            return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
        except Exception:
            pass
    h_bytes = json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    p_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signing_input = f"{_b64url_encode(h_bytes)}.{_b64url_encode(p_bytes)}"
    sig = hmac.new(config.JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"

def decode_token(token):
    if not token or not isinstance(token, str):
        return None
    if _HAS_JWT:
        try:
            return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        except Exception:
            pass
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}"
        sig = _b64url_decode(parts[2])
        expected_sig = hmac.new(config.JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        if payload.get("exp") and time.time() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None

# ------------------------------------------------------------------ User Repository
def get_user_by_id(uid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, email, password_hash, role, locked, created_at, last_login, security_question, security_answer_hash, customer_id FROM users WHERE id=?", (uid,))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "username": row[1], "email": row[2], "password_hash": row[3],
            "role": row[4], "locked": row[5], "created_at": row[6], "last_login": row[7],
            "security_question": row[8], "security_answer_hash": row[9], "customer_id": row[10],
        }

def get_user(identity):
    if not identity:
        return None
    ident = identity.strip()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """SELECT id, username, email, password_hash, role, locked, created_at, last_login, security_question, security_answer_hash, customer_id
               FROM users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE LIMIT 1""",
            (ident, ident),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "username": row[1], "email": row[2], "password_hash": row[3],
            "role": row[4], "locked": row[5], "created_at": row[6], "last_login": row[7],
            "security_question": row[8], "security_answer_hash": row[9], "customer_id": row[10],
        }

def audit(actor, event):
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO audit(actor, event, occurred_at) VALUES(?,?,?)", (str(actor)[:100], event, utcnow()))
            conn.commit()
    except Exception:
        pass

# ------------------------------------------------------------------ Progressive Lockout Ladder
# Login ladder: 3 wrong -> 120s, 4 wrong -> 300s, 5 wrong -> Admin-only unlock.
def check_login_lockout(user_or_identity):
    """Password failures are counted directly; only the administrator can unlock accounts.

    Resend cooldowns are managed separately by the OTP subsystem. Previous
    login cooldown entries must not prevent the fifth password attempt.
    """
    if isinstance(user_or_identity, dict):
        user = user_or_identity
    else:
        user = get_user(str(user_or_identity or "").strip().casefold())
    if user and user.get("locked"):
        return True, None, LOCKED_MESSAGE
    return False, 0, None


def record_login_failure(identity):
    ident = str(identity or "unknown").strip().casefold()
    user = get_user(ident) if ident != "unknown" else None
    if user and user.get("locked"):
        return True, None, LOCKED_MESSAGE

    now = int(time.time())
    subject = f"login:user:{user['id']}" if user else f"login:anon:{ident}"
    with get_conn() as conn:
        row = conn.execute("SELECT attempts FROM limits WHERE subject=?", (subject,)).fetchone()
        attempts = (int(row[0]) if row else 0) + 1
        # Retain the existing table for backward compatibility, but no cooldown
        # blocks password attempts 3 and 4. The fifth failure locks the account.
        conn.execute(
            "INSERT OR REPLACE INTO limits(subject,attempts,window_start,locked_until,ladder_step) VALUES(?,?,?,?,?)",
            (subject, attempts, now, 0, 0),
        )
        if attempts >= 5 and user:
            conn.execute("UPDATE users SET locked=1 WHERE id=?", (user["id"],))
        conn.commit()

    if attempts >= 5 and user:
        audit(user.get("username") or user.get("email") or "unknown", "account_locked_login_attempts")
        return True, None, LOCKED_MESSAGE
    # Keep identical error wording for unknown accounts and bad passwords.
    return False, 0, GENERIC_LOGIN_ERROR


def clear_login_failure(user):
    subject = f"login:user:{user['id']}"
    with get_conn() as conn:
        conn.execute("DELETE FROM limits WHERE subject=?", (subject,))
        conn.commit()

# ------------------------------------------------------------------ OTP Flow & Limits from File 1
def check_otp_lockout(email):
    now = int(time.time())
    u = get_user(email)
    if u and u.get("locked"):
        return True, None, LOCKED_MESSAGE

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT requests, next_request_at, failures, locked_until, ladder_step FROM otp_policy WHERE email=? AND purpose='reset'",
                  (email.strip().casefold(),))
        row = c.fetchone()
        if not row:
            return False, 0, None
        requests, next_request_at, failures, locked_until, ladder_step = row
        if locked_until > now:
            retry_after = locked_until - now
            return True, retry_after, f"Request another code in {retry_after} seconds."
        return False, 0, None

def record_otp_failure(email):
    now = int(time.time())
    em = email.strip().casefold()
    u = get_user(em)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT requests, next_request_at, failures, locked_until, ladder_step FROM otp_policy WHERE email=? AND purpose='reset'", (em,))
        row = c.fetchone()
        if not row:
            requests, next_request_at, failures, locked_until, ladder_step = 0, 0, 1, 0, 0
        else:
            requests, next_request_at, failures, locked_until, ladder_step = row[0], row[1], row[2] + 1, row[3], row[4]

        # File 1 rule: failures >= MAX_OTP_FAILURES (5) -> account locked
        if failures >= MAX_OTP_FAILURES:
            locked_until = now + 315360000
            if u:
                c.execute("UPDATE users SET locked=1 WHERE id=?", (u["id"],))
                audit(u["username"], "account_locked_otp_failures")
        else:
            locked_until = 0

        c.execute("INSERT OR REPLACE INTO otp_policy(email, purpose, requests, next_request_at, failures, locked_until, ladder_step) VALUES(?,?,?,?,?,?,?)",
                  (em, "reset", requests, next_request_at, failures, locked_until, ladder_step))
        conn.commit()

    if failures >= MAX_OTP_FAILURES:
        return True, None, LOCKED_MESSAGE
    return False, 0, "Invalid or expired code."

# ------------------------------------------------------------------ Signup & Login Actions
def signup_user(username, email, password, confirm_password, question, answer, role="Customer"):
    username = (username or "").strip()
    email = (email or "").strip().lower()
    role = "Customer"  # Only administrators assign staff roles.

    if role not in ALLOWED_SIGNUP_ROLES:
        return False, "Invalid role. Allowed roles: Customer, Freight Broker, Operations Manager, Auditor."

    if not re.fullmatch(r"[\w.\-]{3,50}", username, re.UNICODE):
        return False, "Username must be 3–50 letters, digits, dots, dashes, or underscores."

    if valid_email(username):
        return False, "Username cannot be formatted as an email address."

    if not valid_email(email):
        return False, "Enter a valid email address."

    if password != confirm_password:
        return False, "Password and confirmation do not match."

    errs = password_errors(password)
    if errs:
        return False, "Password does not meet requirements: " + ", ".join(errs)

    if question not in QUESTIONS:
        return False, "Choose a security question from the provided list."

    a_err = answer_error(answer)
    if a_err:
        return False, a_err

    if not mailer.configured():
        return False, "Email verification is unavailable. Ask your administrator to configure EMAIL_ADDRESS and EMAIL_PASSWORD in Colab Secrets."

    # Check case-insensitive uniqueness
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE", (username,))
        if c.fetchone():
            return False, "That username is already taken. Please choose another."
        c.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,))
        if c.fetchone():
            return False, "An account with that email already exists."

        pw_hash = hashed(password)
        ans_hash = hashed(clean_answer(answer))
        now = utcnow()
        c.execute(
            """INSERT INTO users(username, email, password_hash, role, locked, created_at, last_login, security_question, security_answer_hash, customer_id, email_verified)
               VALUES(?,?,?,?,0,?,NULL,?,?,NULL,0)""",
            (username, email, pw_hash, role, now, question, ans_hash),
        )
        uid = c.lastrowid
        c.execute("INSERT INTO password_history(user_id, password_hash, created_at) VALUES(?,?,?)", (uid, pw_hash, now))
        conn.commit()

    audit(username, "signup_success")
    return True, "Account created. Verify your email before signing in."

def authenticate_user(identity, password, expected_role=None):
    ident = (identity or "").strip()
    pw = password or ""
    if not ident or not pw:
        return None, 0, GENERIC_LOGIN_ERROR

    user = get_user(ident)
    is_locked, retry_after, lock_msg = check_login_lockout(user or ident)
    if is_locked:
        return None, retry_after or 0, lock_msg

    if not user:
        is_l, ret_s, msg = record_login_failure(ident)
        audit(ident[:100], "login_failed_unknown_user")
        return None, ret_s, msg

    if user.get("locked"):
        return None, 0, LOCKED_MESSAGE

    if not matches(pw, user["password_hash"]):
        u_name = user.get("username") or user.get("email") or ident
        is_l, ret_s, msg = record_login_failure(u_name)
        audit(u_name, "login_failed_wrong_password")
        return None, ret_s, msg

    # Role selection is a sign-in confirmation, not a role assignment.
    # Verify only after the correct password to avoid leaking role metadata.
    if expected_role is not None:
        from rbac import ROLE_CAPS
        if expected_role not in ROLE_CAPS:
            return None, 0, "Select your assigned role to sign in."
        if expected_role != user["role"]:
            audit(user.get("username") or ident, "login_failed_role_mismatch")
            return None, 0, "Selected role does not match your account. Choose your assigned role."

    # Incorrect passwords are counted before disclosing verification status.
    with get_conn() as conn:
        verified = conn.execute("SELECT email_verified FROM users WHERE id=?", (user["id"],)).fetchone()
    if verified and not verified[0]:
        return None, 0, "Email verification required. Check your inbox or request a new code."

    clear_login_failure(user)
    now = utcnow()
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now, user["id"]))
        conn.commit()

    audit(user.get("username") or user.get("email") or ident, "login_success")
    token = issue_token(user)
    return {"token": token, "user": user}, 0, "Login successful."

# ------------------------------------------------------------------ Email verification (Milestone 1)
def email_is_verified(identity):
    user = get_user(identity)
    if not user:
        return False
    with get_conn() as conn:
        row = conn.execute("SELECT email_verified FROM users WHERE id=?", (user["id"],)).fetchone()
    return bool(row and row[0])

def request_email_verification(email):
    email = (email or "").strip().lower()
    if not valid_email(email):
        return False, 0, "Enter a valid email address."
    user = get_user(email)
    if not user:
        return True, 0, "If the account is pending verification, a code will be sent."
    if user.get("locked"):
        return False, 0, LOCKED_MESSAGE
    if email_is_verified(email):
        return True, 0, "Email already verified. You may sign in."
    if not mailer.configured():
        return False, 0, "Email delivery is unavailable. Configure EMAIL_ADDRESS and EMAIL_PASSWORD in Colab Secrets."
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT requests, next_request_at FROM otp_policy WHERE email=? AND purpose='verify'", (email,)).fetchone()
        requests, next_at = row if row else (0, 0)
        if next_at > now:
            return False, next_at-now, f"Request another code in {next_at-now} seconds."
        if requests >= MAX_OTP_REQUESTS:
            # The fifth code remains usable until expiry; additional requests are blocked.
            return False, 0, "Maximum verification code requests reached. Contact your administrator."
        number = requests + 1
        delay = 60 if number <= 3 else 300
        code = f"{secrets.randbelow(1000000):06d}"
        salt = secrets.token_hex(16)
        digest = otp_digest(code, salt, config.JWT_SECRET, "verify")
        conn.execute("INSERT OR REPLACE INTO email_verification_codes(email,code_hash,salt,expires_at) VALUES(?,?,?,?)", (email,digest,salt,now+OTP_TTL))
        conn.execute("INSERT OR REPLACE INTO otp_policy(email,purpose,requests,next_request_at,failures,locked_until,ladder_step) VALUES(?,?,?,?,COALESCE((SELECT failures FROM otp_policy WHERE email=? AND purpose='verify'),0),0,0)", (email,'verify',number,now+delay,email))
        conn.commit()
    success, message = mailer.send(email, "FreightQuote AI — Verify your email", f"Your FreightQuote AI verification code is {code}. It expires in five minutes. Do not share this code.")
    if not success:
        # Failed SMTP delivery must not consume an OTP attempt or a resend slot.
        with get_conn() as conn:
            conn.execute("DELETE FROM email_verification_codes WHERE email=?", (email,))
            conn.execute("UPDATE otp_policy SET requests=?,next_request_at=? WHERE email=? AND purpose='verify'", (requests,next_at,email))
            conn.commit()
        return False, 0, message
    audit(user["username"], "email_verification_requested")
    return True, delay, "A six-digit verification code has been sent to your email."

def verify_email_code(email, code):
    email = (email or "").strip().lower()
    code = (code or "").strip()
    user = get_user(email)
    if not user or not valid_email(email):
        return False, "Invalid or expired code."
    if user.get("locked"):
        return False, LOCKED_MESSAGE
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT code_hash,salt,expires_at FROM email_verification_codes WHERE email=?", (email,)).fetchone()
        valid = bool(row and row[2] > now and re.fullmatch(r"[0-9]{6}",code) and hmac.compare_digest(otp_digest(code,row[1],config.JWT_SECRET,'verify'),row[0]))
        if valid:
            conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user['id'],))
            conn.execute("DELETE FROM email_verification_codes WHERE email=?", (email,))
            conn.execute("DELETE FROM otp_policy WHERE email=? AND purpose='verify'", (email,))
            conn.commit()
            audit(user['username'], "email_verified")
            return True, "Email verified. You may now sign in."
        previous = conn.execute("SELECT failures FROM otp_policy WHERE email=? AND purpose='verify'", (email,)).fetchone()
        failures = (previous[0] if previous else 0) + 1
        conn.execute("INSERT OR IGNORE INTO otp_policy(email,purpose) VALUES(?,'verify')", (email,))
        conn.execute("UPDATE otp_policy SET failures=? WHERE email=? AND purpose='verify'", (failures,email))
        if failures >= MAX_OTP_FAILURES:
            conn.execute("UPDATE users SET locked=1 WHERE id=?", (user['id'],))
            conn.execute("DELETE FROM email_verification_codes WHERE email=?", (email,))
        conn.commit()
    if failures >= MAX_OTP_FAILURES:
        audit(user['username'], "account_locked_email_verification")
        return False, LOCKED_MESSAGE
    return False, "Invalid or expired code."

# ------------------------------------------------------------------ Forgot Password Flow from File 1
def request_password_reset_otp(email):
    email = (email or "").strip().lower()
    if not valid_email(email):
        return False, 0, "Enter a valid email address."

    now = int(time.time())
    user = get_user(email)

    is_locked, retry_after, lock_msg = check_otp_lockout(email)
    if is_locked:
        return False, retry_after or 0, lock_msg

    if not user:
        return False, 0, "If this address is eligible, a code will be sent."
    if user.get("locked"):
        return False, 0, LOCKED_MESSAGE

    # Cooldown & request budget from File 1:
    # 60s for requests 1-3, then 300s. Cap = MAX_OTP_REQUESTS (5) -> locks account
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT requests, next_request_at, failures, locked_until, ladder_step FROM otp_policy WHERE email=? AND purpose='reset'", (email,))
        row = c.fetchone()
        if row:
            requests, next_request_at, failures, locked_until, ladder_step = row
            if next_request_at > now:
                wait_sec = next_request_at - now
                return False, wait_sec, f"Request another code in {wait_sec} seconds."
            if requests >= MAX_OTP_REQUESTS:
                c.execute("UPDATE users SET locked=1 WHERE id=?", (user["id"],))
                audit(user["username"], "account_locked_otp_budget")
                conn.commit()
                return False, 0, LOCKED_MESSAGE
        else:
            requests, next_request_at, failures, locked_until, ladder_step = 0, 0, 0, 0, 0

        number = requests + 1
        delay = 60 if number <= 3 else 300

        code_int = secrets.randbelow(1000000)
        code_str = f"{code_int:06d}"
        salt = secrets.token_hex(16)
        chash = otp_digest(code_str, salt, config.JWT_SECRET, "reset")
        expires_at = now + OTP_TTL
        sent_at = now

        c.execute("INSERT OR REPLACE INTO resets(email, code_hash, salt, expires_at, attempts, sent_at) VALUES(?,?,?,?,0,?)",
                  (email, chash, salt, expires_at, sent_at))
        c.execute("INSERT OR REPLACE INTO otp_policy(email, purpose, requests, next_request_at, failures, locked_until, ladder_step) VALUES(?,?,?,?,?,?,?)",
                  (email, "reset", number, now + delay, failures, locked_until, ladder_step))
        c.execute("DELETE FROM reset_grants WHERE email=?", (email,))
        conn.commit()

    subject = "FreightQuote AI — Your password reset code"
    body = f"Hello {user['username']},\n\nYour password reset verification code is: {code_str}\n\nThis code expires in 5 minutes. If you did not request this, please contact your administrator."
    sent, msg = mailer.send(email, subject, body, html=mailer.otp_html(user["username"], code_str))
    if not sent:
        with get_conn() as conn:
            conn.execute("DELETE FROM resets WHERE email=?", (email,))
            conn.execute("UPDATE otp_policy SET requests=?, next_request_at=? WHERE email=? AND purpose='reset'", (requests, next_request_at if row else 0, email))
            conn.commit()
        return False, 0, msg

    audit(user["username"], "otp_requested:reset")
    return True, delay, "A 6-digit verification code has been sent to your registered email."

def verify_password_reset_otp(email, code):
    email = (email or "").strip().lower()
    code = (code or "").strip()
    if not email or not code:
        return False, None, "Enter the six-digit code."

    now = int(time.time())
    user = get_user(email)
    if not user or user.get("locked"):
        return False, None, "Invalid or expired code."

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT code_hash, salt, expires_at, attempts FROM resets WHERE email=?", (email,))
        row = c.fetchone()
        if not row:
            is_l, ret_s, msg = record_otp_failure(email)
            return False, None, msg

        code_hash, salt, expires_at, attempts = row
        if expires_at <= now:
            c.execute("DELETE FROM resets WHERE email=?", (email,))
            conn.commit()
            return False, None, "Invalid or expired code."

        ok = bool(re.fullmatch(r"[0-9]{6}", code)) and hmac.compare_digest(
            otp_digest(code, salt, config.JWT_SECRET, "reset"), code_hash
        )
        if not ok:
            is_l, ret_s, msg = record_otp_failure(email)
            return False, None, msg

        # Single-use code
        c.execute("DELETE FROM resets WHERE email=?", (email,))
        c.execute("UPDATE otp_policy SET failures=0 WHERE email=? AND purpose='reset'", (email,))
        grant_token = secrets.token_urlsafe(32)
        grant_hash = hashlib.sha256(grant_token.encode("utf-8")).hexdigest()
        c.execute("INSERT OR REPLACE INTO reset_grants(email, token_hash, expires_at, version) VALUES(?,?,?,0)",
                  (email, grant_hash, now + 300))
        conn.commit()

    audit(user["username"], "otp_verified:reset")
    return True, grant_token, "Code verified successfully."

def get_user_security_question(identity):
    ident = (identity or "").strip()
    if not ident:
        return None, "Enter your registered username."
    user = get_user(ident)
    if not user:
        return None, "Unable to verify that username."
    # The question may be displayed to a locked user, but answering it cannot
    # grant a password reset or unlock the account (checked below).
    if user.get("locked"):
        return user["security_question"], LOCKED_MESSAGE

    return user["security_question"], None

def verify_user_security_answer(identity, answer):
    ident = (identity or "").strip()
    answer = answer or ""
    if not ident:
        return False, None, "Enter your registered username."

    user = get_user(ident)
    if not user:
        return False, None, "Unable to verify that username."
    if user.get("locked"):
        return False, None, LOCKED_MESSAGE

    is_l, ret_s, msg = check_otp_lockout(user["email"])
    if is_l:
        return False, None, msg or LOCKED_MESSAGE

    err = answer_error(answer)
    if err:
        return False, None, err

    cleaned = clean_answer(answer)
    if not matches(cleaned, user["security_answer_hash"]):
        record_otp_failure(user["email"])
        audit(user["username"], "security_answer_failed")
        return False, None, "Incorrect answer or too many attempts."

    now = int(time.time())
    grant_token = secrets.token_urlsafe(32)
    grant_hash = hashlib.sha256(grant_token.encode("utf-8")).hexdigest()
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO reset_grants(email, token_hash, expires_at, version) VALUES(?,?,?,0)",
                     (user["email"], grant_hash, now + 300))
        conn.commit()

    audit(user["username"], "security_answer_verified")
    return True, grant_token, "Answer verified successfully."

def reset_user_password(email_or_username, grant_token, new_password, confirm_password):
    ident = (email_or_username or "").strip()
    user = get_user(ident)
    if not user:
        return False, "Account not found."
    if user.get("locked"):
        return False, LOCKED_MESSAGE

    if new_password != confirm_password:
        return False, "Password and confirmation do not match."

    errs = password_errors(new_password)
    if errs:
        return False, "Password does not meet requirements: " + ", ".join(errs)

    now = int(time.time())
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash, expires_at FROM reset_grants WHERE email=?", (user["email"],))
        row = c.fetchone()
        if not row or row[1] < now:
            return False, "Verification expired. Please verify again."
        expected_hash = hashlib.sha256((grant_token or "").encode("utf-8")).hexdigest()
        if not hmac.compare_digest(row[0], expected_hash):
            return False, "Invalid verification token. Please verify again."

        if matches(new_password, user["password_hash"]):
            return False, "Choose a password different from your current password."

        c.execute("SELECT password_hash FROM password_history WHERE user_id=? ORDER BY id DESC LIMIT 5", (user["id"],))
        for h_row in c.fetchall():
            if matches(new_password, h_row[0]):
                return False, "Choose a password different from your recent passwords."

        new_hash = hashed(new_password)
        now_iso = utcnow()
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        c.execute("INSERT INTO password_history(user_id, password_hash, created_at) VALUES(?,?,?)", (user["id"], new_hash, now_iso))
        c.execute("DELETE FROM reset_grants WHERE email=?", (user["email"],))
        c.execute("DELETE FROM resets WHERE email=?", (user["email"],))
        conn.execute("DELETE FROM limits WHERE subject=?", (f"login:user:{user['id']}",))
        conn.execute("DELETE FROM otp_policy WHERE email=?", (user["email"],))
        conn.commit()

    audit(user["username"], "password_changed")
    return True, "Password updated successfully. You may now sign in."

# ------------------------------------------------------------------ Admin Unblock
def unblock_user_account(admin_user, target_identity):
    if admin_user.get("role") != "Admin":
        return False, "Administrator authentication required."
    target = get_user(target_identity)
    if not target:
        return False, "Account not found."

    with get_conn() as conn:
        conn.execute("UPDATE users SET locked=0 WHERE id=?", (target["id"],))
        conn.execute("DELETE FROM limits WHERE subject=?", (f"login:user:{target['id']}",))
        conn.execute("DELETE FROM otp_policy WHERE email=?", (target["email"],))
        conn.execute("DELETE FROM resets WHERE email=?", (target["email"],))
        conn.execute("DELETE FROM reset_grants WHERE email=?", (target["email"],))
        conn.execute("INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
                     (admin_user["username"], "unblock_account", f"Unblocked user {target['username']} ({target['email']})", utcnow()))
        conn.commit()

    audit(admin_user["username"], f"unblocked_user_{target['username']}")
    return True, f"Account {target['username']} has been unlocked."

# ------------------------------------------------------------------ Admin & Default Accounts Seeding
def seed_admin_account():
    # Provision once. Restarts must never change credentials or unlock accounts.
    if password_errors(config.ADMIN_PASSWORD):
        raise ValueError("ADMIN_PASSWORD requires upper/lowercase, a number and a symbol.")
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE role='Admin'").fetchone():
            return
        if conn.execute("SELECT 1 FROM users WHERE username='admin' OR email=?", (config.ADMIN_EMAIL,)).fetchone():
            raise ValueError("Initial administrator identity already belongs to another account.")
        pw_hash = hashed(config.ADMIN_PASSWORD)
        now = utcnow()
        cur = conn.execute("INSERT INTO users(username,email,password_hash,role,locked,created_at,security_question,security_answer_hash) VALUES(?,?,?,'Admin',0,?,?,?)", ("admin",config.ADMIN_EMAIL,pw_hash,now,QUESTIONS[0],hashed(secrets.token_urlsafe(32))))
        conn.execute("INSERT INTO password_history(user_id,password_hash,created_at) VALUES(?,?,?)",(cur.lastrowid,pw_hash,now))
        conn.commit()

# ------------------------------------------------------------------ Profile Management (Stage 3)
def change_username(user_id, new_username, current_password):
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found.", None
    if not current_password or not matches(current_password, user["password_hash"]):
        return False, "Current password is incorrect.", None
    
    clean_u = (new_username or "").strip()
    if not clean_u:
        return False, "New username cannot be empty.", None
    if clean_u == user["username"]:
        return False, "New username must be different from your current username.", None
    if not re.match(r"^[a-zA-Z0-9_.]{3,30}$", clean_u):
        return False, "Username must be 3-30 characters and contain only letters, numbers, underscores, or periods.", None
    
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE username=? AND id != ?", (clean_u, user_id))
        if c.fetchone():
            return False, "Username is already taken. Please choose another.", None
        c.execute("UPDATE users SET username=? WHERE id=?", (clean_u, user_id))
        conn.commit()

    audit(user["username"], f"username_changed_to_{clean_u}")
    updated = get_user_by_id(user_id)
    new_token = issue_token(updated)
    sanitized = {
        "id": updated["id"],
        "username": updated["username"],
        "email": updated["email"],
        "role": updated["role"],
        "customer_id": updated["customer_id"],
        "created_at": updated["created_at"],
        "last_login": updated["last_login"],
    }
    return True, "Username updated successfully.", {"token": new_token, "user": sanitized}

def change_password(user_id, current_password, new_password, confirm_password):
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found."
    if not current_password or not matches(current_password, user["password_hash"]):
        return False, "Current password is incorrect."
    
    if new_password != confirm_password:
        return False, "Password and confirmation do not match."

    errs = password_errors(new_password)
    if errs:
        return False, "Password does not meet requirements: " + ", ".join(errs)

    if matches(new_password, user["password_hash"]):
        return False, "Choose a password different from your current password."

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash FROM password_history WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
        for h_row in c.fetchall():
            if matches(new_password, h_row[0]):
                return False, "Choose a password different from your recent passwords."

        new_hash = hashed(new_password)
        now = utcnow()
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
        c.execute("INSERT INTO password_history(user_id, password_hash, created_at) VALUES(?,?,?)", (user_id, new_hash, now))
        conn.commit()

    audit(user["username"], "password_changed")
    return True, "Password updated successfully."

# ------------------------------------------------------------------ Admin Dashboard Management (Stage 4)
ADMIN_ALLOWED_ROLES = ["Admin", "Operations Manager", "Freight Broker", "Auditor", "Customer"]

def admin_list_users():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, username, email, role, customer_id, locked, created_at, last_login
            FROM users
            ORDER BY id ASC
        """)
        rows = c.fetchall()
        return [
            {
                "id": r[0],
                "username": r[1] or "",
                "email": r[2] or "",
                "role": r[3] or "Customer",
                "customer_id": r[4],
                "locked": bool(r[5]),
                "created_at": r[6] or "—",
                "last_login": r[7] or "Never"
            }
            for r in rows
        ]

def admin_get_metrics():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE locked=1")
        locked = c.fetchone()[0]
        c.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        per_role = {r[0]: r[1] for r in c.fetchall()}
        return {
            "total_users": total,
            "locked_users": locked,
            "roles": per_role
        }

def admin_create_user(admin_username, username, email, password, role, customer_id=None):
    clean_u = (username or "").strip()
    clean_e = (email or "").strip().lower()
    pw = password or ""
    r = (role or "").strip()

    if not clean_u or not clean_e or not pw:
        return False, "Username, email, and temporary password are required."
    
    if r not in ADMIN_ALLOWED_ROLES:
        return False, f"Invalid role. Allowed roles: {', '.join(ADMIN_ALLOWED_ROLES)}."

    if not re.match(r"^[a-zA-Z0-9_.]{3,30}$", clean_u):
        return False, "Username must be 3-30 characters and contain only letters, numbers, underscores, or periods."

    if not valid_email(clean_e):
        return False, "Invalid email address format."

    errs = password_errors(pw)
    if errs:
        return False, "Password does not meet requirements: " + ", ".join(errs)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE", (clean_u,))
        if c.fetchone():
            return False, "Username is already taken."
        c.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (clean_e,))
        if c.fetchone():
            return False, "Email address is already registered."

        pw_hash = hashed(pw)
        now = utcnow()
        ans_hash = hashed(secrets.token_urlsafe(32))
        c.execute(
            """INSERT INTO users(username, email, password_hash, role, locked, created_at, last_login, security_question, security_answer_hash, customer_id)
               VALUES(?, ?, ?, ?, 0, ?, NULL, ?, ?, ?)""",
            (clean_u, clean_e, pw_hash, r, now, QUESTIONS[0], ans_hash, (customer_id or None)),
        )
        uid = c.lastrowid
        c.execute("INSERT INTO password_history(user_id, password_hash, created_at) VALUES(?,?,?)", (uid, pw_hash, now))
        c.execute(
            "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
            (admin_username, "create_user", f"Created user {clean_u} ({clean_e}) with role {r}", now)
        )
        conn.commit()

    audit(admin_username, f"admin_created_user_{clean_u}")
    return True, f"User {clean_u} created successfully."

def admin_change_role(admin_username, target_id, new_role):
    r = (new_role or "").strip()
    if r not in ADMIN_ALLOWED_ROLES:
        return False, f"Invalid role. Allowed roles: {', '.join(ADMIN_ALLOWED_ROLES)}."

    target = get_user_by_id(target_id)
    if not target:
        return False, "User not found."

    if target["role"] == r:
        return True, f"User already has role {r}."

    with get_conn() as conn:
        c = conn.cursor()
        if target["role"] == "Admin" and r != "Admin":
            c.execute("SELECT COUNT(*) FROM users WHERE role='Admin' AND locked=0 AND id != ?", (target_id,))
            remaining = c.fetchone()[0]
            if remaining == 0:
                return False, "Cannot demote the last remaining active Administrator."

        c.execute("UPDATE users SET role=? WHERE id=?", (r, target_id))
        now = utcnow()
        c.execute(
            "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
            (admin_username, "change_role", f"Changed role of {target['username']} from {target['role']} to {r}", now)
        )
        conn.commit()

    audit(admin_username, f"admin_changed_role_{target['username']}_to_{r}")
    return True, f"Role for {target['username']} updated to {r}."

def admin_set_lock(admin_username, target_id, lock_bool):
    target = get_user_by_id(target_id)
    if not target:
        return False, "User not found."

    if target["username"] == admin_username and lock_bool:
        return False, "You cannot lock your own account."

    with get_conn() as conn:
        c = conn.cursor()
        now = utcnow()
        if lock_bool:
            if target["role"] == "Admin":
                c.execute("SELECT COUNT(*) FROM users WHERE role='Admin' AND locked=0 AND id != ?", (target_id,))
                remaining = c.fetchone()[0]
                if remaining == 0:
                    return False, "Cannot lock the last remaining active Administrator."

            c.execute("UPDATE users SET locked=1, account_status='Locked' WHERE id=?", (target_id,))
            c.execute(
                "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
                (admin_username, "lock_user", f"Locked account {target['username']}", now)
            )
            msg = f"Account {target['username']} has been locked."
        else:
            c.execute("UPDATE users SET locked=0, account_status='Active', failed_attempts=0, lock_until=NULL WHERE id=?", (target_id,))
            c.execute("DELETE FROM resets WHERE email=?", (target["email"],))
            c.execute("DELETE FROM reset_grants WHERE email=?", (target["email"],))
            c.execute("DELETE FROM otp_policy WHERE email=?", (target["email"],))
            c.execute("DELETE FROM limits WHERE subject=?", (f"login:user:{target['id']}",))
            c.execute(
                "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
                (admin_username, "unlock_user", f"Unlocked account {target['username']}", now)
            )
            msg = f"Account {target['username']} has been unlocked."
        conn.commit()

    audit(admin_username, f"admin_{'locked' if lock_bool else 'unlocked'}_{target['username']}")
    return True, msg

def admin_delete_user(admin_username, target_id):
    target = get_user_by_id(target_id)
    if not target:
        return False, "User not found."

    if target["username"] == admin_username:
        return False, "You cannot delete your own account."

    with get_conn() as conn:
        c = conn.cursor()
        if target["role"] == "Admin":
            c.execute("SELECT COUNT(*) FROM users WHERE role='Admin' AND locked=0 AND id != ?", (target_id,))
            remaining = c.fetchone()[0]
            if remaining == 0:
                return False, "Cannot remove the last remaining active Administrator."

        c.execute("DELETE FROM users WHERE id=?", (target_id,))
        c.execute("DELETE FROM password_history WHERE user_id=?", (target_id,))
        c.execute("DELETE FROM resets WHERE email=?", (target["email"],))
        c.execute("DELETE FROM reset_grants WHERE email=?", (target["email"],))
        now = utcnow()
        c.execute(
            "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
            (admin_username, "delete_user", f"Deleted user {target['username']} ({target['email']})", now)
        )
        conn.commit()

    audit(admin_username, f"admin_deleted_user_{target['username']}")
    return True, f"User {target['username']} has been deleted."

def admin_link_customer(admin_username, target_id, customer_id):
    target = get_user_by_id(target_id)
    if not target:
        return False, "User not found."

    clean_cid = (customer_id or "").strip() or None

    with get_conn() as conn:
        conn.execute("UPDATE users SET customer_id=? WHERE id=?", (clean_cid, target_id))
        now = utcnow()
        conn.execute(
            "INSERT INTO admin_activity_log(actor, action, details, timestamp) VALUES(?,?,?,?)",
            (admin_username, "link_customer", f"Linked {target['username']} to {clean_cid}", now)
        )
        conn.commit()

    audit(admin_username, f"admin_linked_{target['username']}_to_{clean_cid}")
    return True, f"User {target['username']} is now linked to {clean_cid or 'None'}."

def admin_get_activity_log(limit=50):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, actor, action, details, timestamp FROM admin_activity_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = c.fetchall()
        return [
            {
                "id": r[0],
                "actor": r[1] or "system",
                "action": r[2] or "",
                "details": r[3] or "",
                "timestamp": r[4] or ""
            }
            for r in rows
        ]


def session_version(uid):
    with get_conn() as c:
        try:
            row = c.execute("SELECT session_version FROM users WHERE id=?", (uid,)).fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception:
            return 0

def init_sessions():
    with get_conn() as c:
        if "session_version" not in [x[1] for x in c.execute("PRAGMA table_info(users)")]:
            c.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
        c.execute("""CREATE TRIGGER IF NOT EXISTS revoke_user_sessions AFTER UPDATE OF password_hash,role,locked,username ON users BEGIN UPDATE users SET session_version=session_version+1 WHERE id=NEW.id; END""")