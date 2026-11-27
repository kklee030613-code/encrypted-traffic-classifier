import csv
import datetime
import os
from .db import init_db, get_connection


def ingest_csv(csv_path: str, user_id: int = 1, date_str: str = None, window_sec: int = 5) -> int:
    init_db()
    if date_str is None:
        date_str = datetime.date.today().isoformat()

    source_name = os.path.basename(csv_path)
    conn = get_connection()
    cur = conn.cursor()

    # 같은 파일을 중복 적재하지 않도록 기존 기록 정리
    cur.execute("DELETE FROM traffic_logs WHERE user_id=? AND source_file=? AND date=?", (user_id, source_name, date_str))

    inserted = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 1) demo/live_*.csv 형식: time,truth,predicted,confidence,smoothed,total_packet,total_bytes
            if "smoothed" in row or "predicted" in row:
                app_name = (row.get("smoothed") or row.get("predicted") or "unknown").strip()
                time_str = (row.get("time") or "").strip()
                conf = float(row.get("confidence") or 0.0)
                pkts = int(float(row.get("total_packet") or 0))
                byt = int(float(row.get("total_bytes") or 0))
                send_b, recv_b = 0, byt
            # 2) data/full_features.csv 형식: window_start_time,app_label,...,send_bytes,recv_bytes,...
            elif "app_label" in row:
                app_name = (row.get("app_label") or "unknown").strip()
                ts_val = float(row.get("window_start_time") or 0)
                dt = datetime.datetime.fromtimestamp(ts_val) if ts_val else datetime.datetime.now()
                time_str = dt.strftime("%H:%M:%S")
                conf = 1.0
                pkts = int(float(row.get("total_packet") or 0))
                byt = int(float(row.get("total_bytes") or 0))
                send_b = int(float(row.get("send_bytes") or 0))
                recv_b = int(float(row.get("recv_bytes") or 0))
            else:
                continue

            cur.execute(
                """
                INSERT INTO traffic_logs
                (user_id, source_file, date, time_str, app_name, confidence, total_packet, total_bytes, send_bytes, recv_bytes, window_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, source_name, date_str, time_str, app_name, conf, pkts, byt, send_b, recv_b, window_sec),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted
def log_window(
    ts: float,
    app_name: str,
    confidence: float,
    feats: dict,
    user_id: int = 1,
    source_file: str = "live",
    window_sec: int = 5,
) -> None:
    init_db()
    dt = datetime.datetime.fromtimestamp(ts)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO traffic_logs
        (user_id, source_file, date, time_str, app_name, confidence, total_packet, total_bytes, send_bytes, recv_bytes, window_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            source_file,
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%H:%M:%S"),
            app_name,
            float(confidence),
            int(feats.get("total_packet", 0)),
            int(feats.get("total_bytes", 0)),
            int(feats.get("send_bytes", 0)),
            int(feats.get("recv_bytes", 0)),
            window_sec,
        ),
    )
    conn.commit()
    conn.close()