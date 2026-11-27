import os
import sqlite3
import threading

DB_PATH = os.environ.get(
    "LLM_REPORT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "llm_report.db"),
)

_lock = threading.Lock()


def get_connection():
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS traffic_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            source_file TEXT,
            date TEXT,
            time_str TEXT,
            app_name TEXT,
            confidence REAL,
            total_packet INTEGER,
            total_bytes INTEGER,
            send_bytes INTEGER DEFAULT 0,
            recv_bytes INTEGER DEFAULT 0,
            window_sec INTEGER DEFAULT 5
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query_text TEXT,
            answer_text TEXT,
            timestamp TEXT,
            model_version TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            period_start TEXT,
            period_end TEXT,
            summary_text TEXT,
            generated_at TEXT
        )
        """)
        conn.commit()
        conn.close()