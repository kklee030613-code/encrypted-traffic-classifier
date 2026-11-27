import datetime
import os
from .llm_client import LLMClient
from .db import get_connection


def judge_candidates(candidates, context=None, model_version="default"):
    mock = os.environ.get("ENABLE_MOCK_LLM", "true").lower() in ("1", "true", "yes", "on")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    llm = LLMClient(model_version=model_version, mock=mock, provider=provider)

    conn = get_connection()
    cur = conn.cursor()
    results = []

    for c in (candidates or []):
        ts = datetime.datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO anomaly_candidates (flow_id, timestamp, reason, confidence) VALUES (?, ?, ?, ?)",
            (c.get("flow_id"), ts, c.get("reason"), c.get("confidence", 0.0)),
        )
        cand_id = cur.lastrowid

        prompt = (
            f"너는 네트워크 보안/트래픽 분석 AI야. 규칙 필터가 아래 트래픽을 '이상 후보'로 올렸어.\n"
            f"실제 보안 이상/비정상 트래픽인지, 아니면 정상 앱 사용 중 흔히 생기는 오탐(False Positive, 예: 유튜브 버퍼링 4MB)인지 판단해줘.\n"
            f"반드시 첫 줄을 '[실제 이상]' 또는 '[정상/오탐]' 중 하나로 시작하고, 그 다음 줄에 간단한 근거를 한국어로 적어줘.\n\n"
            f"후보 정보: {c}\n"
            f"추가 컨텍스트: {context or '5초 윈도우 단위 암호화 트래픽 분류 결과'}\n"
            f"판정:"
        )
        verdict = llm.generate(prompt, max_tokens=220)

        cur.execute(
            "INSERT INTO anomaly_results (candidate_id, verdict, explanation, llm_timestamp) VALUES (?, ?, ?, ?)",
            (cand_id, verdict, c.get("reason"), datetime.datetime.utcnow().isoformat()),
        )
        res_id = cur.lastrowid
        results.append({
            "result_id": res_id,
            "candidate": c,
            "verdict": verdict,
        })

    conn.commit()
    conn.close()
    return results