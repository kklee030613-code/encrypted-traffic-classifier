import datetime
from .db import get_connection


def send_alerts(results, channels=None, include_false_positive: bool = False):
    if channels is None:
        channels = ["console"]

    conn = get_connection()
    cur = conn.cursor()

    for r in (results or []):
        verdict = r["verdict"]
        is_fp = "[정상/오탐]" in verdict and not include_false_positive

        if is_fp:
            print(f"[오탐 제외됨] {r['candidate'].get('flow_id')} ({r['candidate'].get('reason')})")
            status = "suppressed_fp"
        else:
            print("=" * 60)
            print(f"🚨 [평소와 다른 트래픽 알림] {r['candidate'].get('flow_id')}")
            print(f"탐지 규칙 사유: {r['candidate'].get('reason')}")
            print(f"LLM 판정:\n{verdict}")
            print("=" * 60)
            status = "sent"

        for ch in channels:
            cur.execute(
                "INSERT INTO alerts (anomaly_result_id, channel, status, sent_at) VALUES (?, ?, ?, ?)",
                (r.get("result_id"), ch, status, datetime.datetime.utcnow().isoformat()),
            )

    conn.commit()
    conn.close()