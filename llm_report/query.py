import datetime
import os
from .llm_client import LLMClient
from .db import init_db, get_connection


def _build_usage_stats(cur, user_id: int) -> str:
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
        WHERE user_id=?
        GROUP BY date, app_name
        ORDER BY date DESC, total_sec DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return "(아직 DB에 적재된 앱 트래픽 기록이 없습니다.)"

    lines = []
    for r in rows:
        sec = r["total_sec"] or 0
        mb = (r["total_bytes"] or 0) / (1024 * 1024)
        lines.append(
            f"- 날짜 {r['date']} | 앱: {r['app_name']} | "
            f"사용시간: {sec}초 ({sec/60:.1f}분, {r['windows']}윈도우) | "
            f"데이터: {mb:.2f} MB ({r['total_bytes']} bytes, {r['total_pkts']} packets) | "
            f"시간대: {r['first_seen']}~{r['last_seen']}"
        )
    return "\n".join(lines)


def handle_query(query_text: str, user_id: int, model_version: str = "default") -> str:
    init_db()
    mock = os.environ.get("ENABLE_MOCK_LLM", "true").lower() in ("1", "true", "yes", "on")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    llm = LLMClient(model_version=model_version, mock=mock, provider=provider)

    conn = get_connection()
    cur = conn.cursor()

    usage_stats = _build_usage_stats(cur, user_id)

    cur.execute(
        "SELECT query_text, answer_text, timestamp FROM llm_queries WHERE user_id=? ORDER BY timestamp DESC LIMIT 3",
        (user_id,),
    )
    qrows = cur.fetchall()
    chat_history = "\n".join([f"Q: {r['query_text']} / A: {r['answer_text']}" for r in qrows]) or "(없음)"

    today = datetime.date.today().isoformat()
    prompt = (
        f"너는 암호화 트래픽 앱 분류기의 사용량 분석 챗봇이야. 오늘 날짜는 {today}이야.\n"
        f"아래 DB의 실제 앱별 트래픽 통계를 근거로 사용자의 질문에 한국어로 정확하고 친절하게 답해줘.\n"
        f"기록에 없는 내용은 지어내지 말고, 기록이 없으면 없다고 솔직히 말해줘.\n\n"
        f"[앱 사용 통계 (DB)]\n{usage_stats}\n\n"
        f"[최근 대화]\n{chat_history}\n\n"
        f"사용자 질문: {query_text}\n답변:"
    )
    answer = llm.generate(prompt, max_tokens=400)

    ts = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO llm_queries (user_id, query_text, answer_text, timestamp, model_version) VALUES (?, ?, ?, ?, ?)",
        (user_id, query_text, answer, ts, model_version),
    )
    conn.commit()
    conn.close()
    return answer