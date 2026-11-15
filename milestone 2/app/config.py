"""Shared configuration for FreightQuote AI.
Reads required secrets from Colab Secrets (or environment variables).
Fail closed if admin or JWT secrets are missing; never use published credentials.
"""
import os
import secrets as _s

KIND = os.environ.get("APP_KIND", "Freight")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
_in_colab = os.path.isdir("/content") and os.name != "nt"
_default = "/content/app_data" if _in_colab else os.path.join(APP_DIR, "runtime_data")
DATA_DIR = os.environ.get("PERSIST_DIR") or os.environ.get("APP_DATA_DIR") or os.environ.get("FREIGHTQUOTE_DATA_DIR") or _default
os.makedirs(DATA_DIR, exist_ok=True)
_mpl_dir = os.path.join(DATA_DIR, "mpl")
os.makedirs(_mpl_dir, exist_ok=True)
os.environ["MPLCONFIGDIR"] = _mpl_dir
DB_PATH = os.path.join(DATA_DIR, "freight_database.db")

def _secret(*keys, default=""):
    for k in keys:
        try:
            from google.colab import userdata
            v = userdata.get(k)
            if v:
                return str(v).strip()
        except Exception:
            pass
        val = os.environ.get(k)
        if val:
            return str(val).strip()
    return default

JWT_SECRET = _secret("JWT_SECRET", "JWT_SECRET_KEY")
if len(JWT_SECRET) < 32:
    raise RuntimeError("Set JWT_SECRET to at least 32 characters in Colab Secrets or the environment.")
ADMIN_EMAIL = _secret("ADMIN_EMAIL", "ADMIN_EMAIL_ID", default="admin@infosys.com")
ADMIN_PASSWORD = _secret("ADMIN_PASSWORD", default="")
if not 12 <= len(ADMIN_PASSWORD.encode("utf-8")) <= 72:
    raise RuntimeError("Set a unique ADMIN_PASSWORD (12–72 UTF-8 bytes) in Colab Secrets or the environment.")

EMAIL_ADDRESS = _secret("EMAIL_ADDRESS", "EMAIL_ID", "SENDER_EMAIL", default="")
EMAIL_PASSWORD = _secret("EMAIL_PASSWORD", "EMAIL_APP_PASSWORD", default="").replace(" ", "")
NGROK_AUTHTOKEN = _secret("NGROK_AUTHTOKEN", default="")
HF_TOKEN = _secret("HF_TOKEN", "HUGGINGFACE_TOKEN", default="")
