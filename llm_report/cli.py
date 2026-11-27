import argparse
from .query import handle_query
from .summaries import generate_summary
from .ingest import ingest_csv


def main():
    ap = argparse.ArgumentParser(prog="llm_report", description="LLM Report & Chatbot CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="분류기 CSV 결과를 DB에 적재")
    ing.add_argument("--csv", required=True, help="CSV 파일 경로 (예: demo/live_youtube.csv)")
    ing.add_argument("--user-id", type=int, default=1)
    ing.add_argument("--date", default=None, help="YYYY-MM-DD (생략 시 오늘)")

    q = sub.add_parser("query", help="자연어 질문")
    q.add_argument("--query", required=True)
    q.add_argument("--user-id", type=int, default=1)
    q.add_argument("--model-version", default="default")

    s = sub.add_parser("summarize", help="기간 사용 요약 리포트 생성")
    s.add_argument("--user-id", type=int, default=1)
    s.add_argument("--period-start", required=True)
    s.add_argument("--period-end", required=True)

    ns = ap.parse_args()
    if ns.cmd == "ingest":
        cnt = ingest_csv(ns.csv, user_id=ns.user_id, date_str=ns.date)
        print(f"Ingested {cnt} rows from {ns.csv}")
    elif ns.cmd == "query":
        print(handle_query(ns.query, ns.user_id, ns.model_version))
    elif ns.cmd == "summarize":
        print(generate_summary(ns.user_id, ns.period_start, ns.period_end))


if __name__ == "__main__":
    main()