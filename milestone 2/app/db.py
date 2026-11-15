import sqlite3, os, threading
from config import DB_PATH

# A single, long-lived connection reused across the whole app process
# instead of opening (and never explicitly closing) a brand-new SQLite
# connection + re-running PRAGMA setup on every single call. That old
# pattern was leaking file handles under load and was the single
# biggest source of slowness/lock contention across the app.
_conn = None
_conn_lock = threading.Lock()
_transaction_lock = threading.RLock()
class SerializedConnection(sqlite3.Connection):
    def __enter__(self):
        _transaction_lock.acquire()
        try:
            self.execute("BEGIN IMMEDIATE")
            return self
        except Exception:
            _transaction_lock.release()
            raise
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            _transaction_lock.release()


def get_conn():
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                _conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False, factory=SerializedConnection)
                _conn.execute("PRAGMA journal_mode=WAL;")
                _conn.execute("PRAGMA synchronous=NORMAL;")
                _conn.execute("PRAGMA cache_size=-64000;")   # ~64MB page cache
                _conn.execute("PRAGMA temp_store=MEMORY;")
    return _conn

def save_chat_message(username, role, message):
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO chat_history (username, role, message) VALUES (?, ?, ?);", (username, role, message))
            conn.commit()
    except Exception: pass

def load_chat_history(username=None, limit=100):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            if username:
                rows = cur.execute("SELECT role, message FROM chat_history WHERE username=? ORDER BY id ASC LIMIT ?;", (username, limit)).fetchall()
            else:
                rows = cur.execute("SELECT role, message FROM chat_history ORDER BY id ASC LIMIT ?;", (limit,)).fetchall()

            res = []
            for r in rows:
                content_val = str(r[1] or "")
                res.append({
                    "role": str(r[0] or "assistant"),
                    "content": content_val,
                    "message": content_val
                })
            return res
    except Exception: return []

def clear_chat_history(username=None):
    try:
        with get_conn() as conn:
            if username:
                conn.execute("DELETE FROM chat_history WHERE username=?;", (username,))
            else:
                conn.execute("DELETE FROM chat_history;")
            conn.commit()
    except Exception: pass

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            role TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT,
            security_question TEXT,
            security_answer_hash TEXT,
            role TEXT,
            failed_attempts INTEGER DEFAULT 0,
            lock_until TIMESTAMP DEFAULT NULL,
            account_status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Authentication columns and tables — safe migrations for existing databases.
        for _col, _ddl in [
            ("username", "ALTER TABLE users ADD COLUMN username TEXT"),
            ("security_question", "ALTER TABLE users ADD COLUMN security_question TEXT"),
            ("security_answer_hash", "ALTER TABLE users ADD COLUMN security_answer_hash TEXT"),
            ("failed_attempts", "ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0"),
            ("lock_until", "ALTER TABLE users ADD COLUMN lock_until TIMESTAMP DEFAULT NULL"),
            ("account_status", "ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'active'"),
            ("profile_picture", "ALTER TABLE users ADD COLUMN profile_picture TEXT DEFAULT NULL"),
            ("locked", "ALTER TABLE users ADD COLUMN locked INTEGER NOT NULL DEFAULT 0"),
            ("last_login", "ALTER TABLE users ADD COLUMN last_login TEXT DEFAULT NULL"),
            ("customer_id", "ALTER TABLE users ADD COLUMN customer_id TEXT DEFAULT NULL"),
            ("session_version", "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"),
            ("email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1"),
        ]:
            try:
                conn.execute(_ddl)
            except Exception:
                pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS limits (
            subject TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            window_start INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER NOT NULL DEFAULT 0,
            ladder_step INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS resets (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            code_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            sent_at INTEGER NOT NULL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_policy (
            email TEXT NOT NULL COLLATE NOCASE,
            purpose TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0,
            next_request_at INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER NOT NULL DEFAULT 0,
            ladder_step INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(email, purpose)
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS email_verification_codes (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            code_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS reset_grants (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            token_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            event TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL
        );
        """)

        # Preserve older Stage 5/Milestone 1 admin-activity tables during upgrades.
        # CREATE TABLE IF NOT EXISTS does not migrate an existing table.
        _activity_columns = {r[1] for r in conn.execute("PRAGMA table_info(admin_activity_log)")}
        for _name, _ddl in (
            ("actor", "ALTER TABLE admin_activity_log ADD COLUMN actor TEXT NOT NULL DEFAULT 'system'"),
            ("action", "ALTER TABLE admin_activity_log ADD COLUMN action TEXT NOT NULL DEFAULT ''"),
            ("details", "ALTER TABLE admin_activity_log ADD COLUMN details TEXT"),
            ("timestamp", "ALTER TABLE admin_activity_log ADD COLUMN timestamp TEXT NOT NULL DEFAULT ''"),
        ):
            if _name not in _activity_columns:
                conn.execute(_ddl)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id TEXT,
            outlet_id TEXT,
            severity TEXT,
            category TEXT,
            message TEXT,
            date TEXT,
            resolved INT DEFAULT 0
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            shipment_id TEXT PRIMARY KEY,
            origin_port TEXT,
            dest_port TEXT,
            carrier TEXT,
            status TEXT,
            eta TEXT,
            weight_kg REAL,
            hs_code TEXT,
            predicted_delay_risk REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS freight_quotes (
            quote_id TEXT PRIMARY KEY,
            shipment_id TEXT,
            customer_id TEXT,
            carrier TEXT,
            base_cost REAL,
            insurance REAL,
            customs_fee REAL,
            fuel_surcharge REAL,
            final_price REAL,
            margin_pct REAL,
            status TEXT,
            created_at TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ports (
            port_id TEXT PRIMARY KEY,
            port_name TEXT,
            country TEXT,
            congestion_index REAL,
            avg_dwell_days REAL,
            lat REAL,
            lon REAL,
            region TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS carriers (
            carrier_id TEXT PRIMARY KEY,
            name TEXT,
            rating REAL,
            on_time_pct REAL,
            avg_cost_index REAL,
            risk_level TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            priority_tier TEXT,
            credit_risk REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ml_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT,
            model_name TEXT,
            metric_name TEXT,
            metric_value REAL,
            trained_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS outlets (
            outlet_id TEXT PRIMARY KEY,
            outlet_name TEXT,
            location TEXT,
            tier TEXT,
            revenue REAL,
            operating_costs REAL,
            customer_satisfaction REAL,
            staff_headcount INT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            staff_id TEXT PRIMARY KEY,
            outlet_id TEXT,
            name TEXT,
            role TEXT,
            salary REAL,
            overtime_hrs REAL,
            job_satisfaction INT,
            age INT,
            tenure_years INT,
            work_life_balance INT,
            predicted_attrition_prob REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            record_id TEXT PRIMARY KEY,
            outlet_id TEXT,
            sku_name TEXT,
            category TEXT,
            current_stock INT,
            reorder_threshold INT,
            weekly_demand REAL,
            lead_time_days INT,
            stockout_risk_prob REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS marketing (
            campaign_id TEXT PRIMARY KEY,
            outlet_id TEXT,
            campaign_name TEXT,
            channel TEXT,
            budget REAL,
            actual_roi REAL,
            reach INT,
            conversions INT,
            start_date TEXT,
            end_date TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            outlet_id TEXT,
            rating INT,
            comment TEXT,
            date TEXT,
            sentiment_score REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            audit_id TEXT PRIMARY KEY,
            outlet_id TEXT,
            audit_date TEXT,
            score REAL,
            violations INT,
            category TEXT,
            status TEXT,
            notes TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_risks (
            port_name TEXT PRIMARY KEY,
            current_severity INT,
            forecast TEXT,
            wind_speed REAL,
            wave_height REAL,
            temperature REAL
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customs_rules (
            chapter TEXT PRIMARY KEY,
            goods TEXT,
            duty_pct REAL,
            docs TEXT,
            restricted INT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS vessels (
            shipment_id TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            progress REAL,
            chain TEXT,
            route_name TEXT,
            speed_kn REAL,
            updated TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            score REAL,
            risk TEXT,
            narrative TEXT
        );
        """)
        conn.commit()