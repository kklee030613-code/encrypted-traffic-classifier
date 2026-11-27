import argparse
from .rules import load_flows_from_csv, detect_candidates
from .judge import judge_candidates
from .alerts import send_alerts
from .db import init_db


def main():
    ap = argparse.ArgumentParser(prog="llm_anomaly", description="LLM Anomaly Detection CLI")
    ap.add_argument("--csv", default="demo/live_youtube.csv", help="분석할 트래픽 CSV 경로")
    ap.add_argument("--limit", type=int, default=5, help="LLM에 판정 요청할 최대 후보 수 (API 비용 절약)")
    ap.add_argument("--show-all", action="store_true", help="오탐으로 걸러진 결과도 알림으로 표시")
    ap.add_argument("--channels", nargs="+", default=["console"], help="알림 채널")
    ns = ap.parse_args()

    init_db()
    flows = load_flows_from_csv(ns.csv)
    candidates = detect_candidates(flows)

    if not candidates:
        print(f"[{ns.csv}] 규칙에 걸린 이상 트래픽 후보가 없습니다. (총 {len(flows)}개 윈도우 검사)")
        return

    print(f"[{ns.csv}] 총 {len(flows)}개 중 규칙 후보 {len(candidates)}건 탐지 -> 상위 {min(len(candidates), ns.limit)}건 LLM 판정 시작")
    results = judge_candidates(candidates[: ns.limit])
    send_alerts(results, channels=ns.channels, include_false_positive=ns.show_all)


if __name__ == "__main__":
    main()