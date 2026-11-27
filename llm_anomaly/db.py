import os
import sqlite3
import threading

DB_PATH = os.environ.get("LLM_ANOMALY_DB_PATH", os.path.join(os.path.dirname(__file__), "llm_anomaly.db"))

_lock = threading.Lock()

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_id TEXT,
            timestamp TEXT,
            reason TEXT,
            confidence REAL
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            verdict TEXT,
            explanation TEXT,
            llm_timestamp TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anomaly_result_id INTEGER,
            channel TEXT,
            status TEXT,
            sent_at TEXT
        )
        """)
        conn.commit()
        conn.close()
