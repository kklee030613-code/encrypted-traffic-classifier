import csv
import datetime


def load_flows_from_csv(csv_path: str) -> list:
    flows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            if "smoothed" in row or "predicted" in row:
                time_str = (row.get("time") or "00:00:00").strip()
                app = (row.get("smoothed") or row.get("predicted") or "unknown").strip()
                conf = float(row.get("confidence") or 0.0)
                pkts = int(float(row.get("total_packet") or 0))
                byt = int(float(row.get("total_bytes") or 0))
                send_b, recv_b = 0, byt
            elif "app_label" in row:
                ts_val = float(row.get("window_start_time") or 0)
                time_str = datetime.datetime.fromtimestamp(ts_val).strftime("%H:%M:%S") if ts_val else "00:00:00"
                app = (row.get("app_label") or "unknown").strip()
                conf = 1.0
                pkts = int(float(row.get("total_packet") or 0))
                byt = int(float(row.get("total_bytes") or 0))
                send_b = int(float(row.get("send_bytes") or 0))
                recv_b = int(float(row.get("recv_bytes") or 0))
            else:
                continue

            flows.append({
                "flow_id": f"{idx}_{time_str}_{app}",
                "time": time_str,
                "app": app,
                "confidence": conf,
                "packets": pkts,
                "bytes": byt,
                "send_bytes": send_b,
                "recv_bytes": recv_b,
            })
    return flows


def detect_candidates(flows, context=None):
    candidates = []
    for f in flows or []:
        reasons = []
        time_str = f.get("time", "00:00:00")
        hour = int(time_str.split(":")[0]) if ":" in time_str else 12
        byt = f.get("bytes", 0)
        send_b = f.get("send_bytes", 0)
        conf = f.get("confidence", 1.0)

        # 규칙 1: 새벽 시간대(00~05시) 대량 트래픽 또는 대량 업로드
        if 0 <= hour <= 5 and (byt > 500_000 or send_b > 200_000):
            reasons.append("새벽 시간대 대량 트래픽/업로드")

        # 규칙 2: 5초 윈도우 내 3MB 초과 스파이크
        if byt > 3_000_000:
            reasons.append(f"단시간 트래픽 급증 ({byt/1024/1024:.2f} MB / 5s)")

        # 규칙 3: 업로드 비율 비정상(송신 > 수신*2 이면서 200KB 초과)
        if send_b > 200_000 and send_b > f.get("recv_bytes", 0) * 2:
            reasons.append(f"비정상 대량 업로드 (send={send_b} bytes)")

        # 규칙 4: 낮은 분류 신뢰도(<0.55) + 1MB 이상 전송 (처음 보는 서버/패턴 의심)
        if conf < 0.55 and byt > 1_000_000:
            reasons.append(f"미확인 패턴 의심 (confidence={conf:.2f}, {byt/1024/1024:.2f} MB)")

        if reasons:
            candidates.append({
                "flow_id": f.get("flow_id"),
                "reason": ", ".join(reasons),
                "confidence": conf,
                "flow": f,
            })
    return candidates