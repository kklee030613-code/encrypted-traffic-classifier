import datetime
import os
from .llm_client import LLMClient
from .db import init_db, get_connection


def generate_summary(user_id: int, period_start: str, period_end: str) -> str:
    init_db()
    conn = get_connection()
    cur = conn.cursor()

    start_date = period_start[:10]
    end_date = period_end[:10]

    cur.execute(
        """
        SELECT date, app_name,
               COUNT(*) AS windows,
               SUM(window_sec) AS total_sec,
               SUM(total_packet) AS total_pkts,
               SUM(total_bytes) AS total_bytes,
               MIN(time_str) AS first_seen,
               MAX(time_str) AS last_seen
        FROM traffic_logs
        WHERE user_id=? AND date BETWEEN ? AND ?
        GROUP BY date, app_name
        ORDER BY total_sec DESC
        """,
        (user_id, start_date, end_date),
    )
    usage_rows = cur.fetchall()
    usage_text = "\n".join(
        [
            f"- {r['date']} | {r['app_name']}: {r['total_sec']}초 ({r['total_sec']/60:.1f}분), "
            f"{(r['total_bytes'] or 0)/(1024*1024):.2f} MB, 시간대 {r['first_seen']}~{r['last_seen']}"
            for r in usage_rows
        ]
    ) or "(해당 기간 트래픽 기록 없음)"

    cur.execute(
        "SELECT query_text, timestamp FROM llm_queries WHERE user_id=? AND timestamp BETWEEN ? AND ?",
        (user_id, period_start, period_end),
    )
    qrows = cur.fetchall()

    mock = os.environ.get("ENABLE_MOCK_LLM", "true").lower() in ("1", "true", "yes", "on")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    llm = LLMClient(model_version="summary", mock=mock, provider=provider)

    prompt = (
        f"아래 기간의 네트워크 앱 사용량 요약 리포트를 한국어로 깔끔하게 작성해줘.\n"
        f"기간: {period_start} ~ {period_end}\n"
        f"총 챗봇 질의 수: {len(qrows)}\n\n"
        f"[앱별 사용 기록]\n{usage_text}\n\n"
        f"앱별 사용 시간, 데이터 사용량 비중, 주요 특징을 포함해서 요약해줘:"
    )
    summary_text = llm.generate(prompt, max_tokens=500)

    ts = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO summaries (user_id, period_start, period_end, summary_text, generated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, period_start, period_end, summary_text, ts),
    )
    conn.commit()
    conn.close()
    return summary_text