"""Live capture -> 5 s features -> model -> app name, in one command.

    # live (admin terminal, Npcap installed on Windows)
    python -m src.live_predict --model models/window_model.joblib --iface "Wi-Fi" --truth youtube --log demo/live_youtube.csv

    # replay a capture file with LLM DB logging + anomaly alert
    python -m src.live_predict --model models/window_model.joblib --pcap yt_web_01.pcapng --save-db --anomaly-alert
"""
import argparse
import csv
import threading
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from src.window_features import WINDOW_SEC, Window, guess_local_ip, pcap_windows

LOG_HEADER = ["time", "truth", "predicted", "confidence", "smoothed", "total_packet", "total_bytes"]


def _check_anomaly_async(stamp: str, app: str, conf: float, feats: dict):
    try:
        from llm_anomaly.db import init_db
        from llm_anomaly.rules import detect_candidates
        from llm_anomaly.judge import judge_candidates
        from llm_anomaly.alerts import send_alerts

        init_db()
        flow = {
            "flow_id": f"live_{stamp}_{app}",
            "time": stamp,
            "app": app,
            "confidence": float(conf),
            "packets": int(feats.get("total_packet", 0)),
            "bytes": int(feats.get("total_bytes", 0)),
            "send_bytes": int(feats.get("send_bytes", 0)),
            "recv_bytes": int(feats.get("recv_bytes", 0)),
        }
        candidates = detect_candidates([flow])
        if candidates:
            results = judge_candidates(candidates, context="실시간 5초 윈도우 분류기")
            send_alerts(results, channels=["console"])
    except Exception as e:
        print(f"[anomaly hook error] {e}")


class Predictor:
    def __init__(self, model_path, min_pkts, smooth, truth, log_path,
                 save_db=False, anomaly_alert=False, source_name="live"):
        bundle = joblib.load(model_path)
        self.model, self.columns = bundle["model"], bundle["columns"]
        self.min_pkts, self.truth = min_pkts, truth or ""
        self.recent = deque(maxlen=smooth)
        self.results = []
        self.save_db = save_db
        self.anomaly_alert = anomaly_alert
        self.source_name = source_name
        self.log = None
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            self.log = open(log_path, "w", newline="", encoding="utf-8")
            self.writer = csv.writer(self.log)
            self.writer.writerow(LOG_HEADER)
        print(f"model apps: {bundle['labels']}  window={WINDOW_SEC}s\n")

    def __call__(self, ts, feats):
        stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        if feats["total_packet"] < self.min_pkts:
            print(f"[{stamp}] idle ({feats['total_packet']} pkts)")
            return
        x = pd.DataFrame([feats])[self.columns]
        proba = self.model.predict_proba(x)[0]
        best = proba.argmax()
        app, conf = self.model.classes_[best], proba[best]
        self.recent.append(proba)
        smoothed = self.model.classes_[sum(self.recent).argmax()]
        mark = "" if not self.truth else ("  O" if smoothed == self.truth else "  X")
        print(f"[{stamp}] {app:10s} {conf:4.0%} | last {len(self.recent)}: {smoothed:10s}"
              f"| {feats['total_packet']:5d} pkts {feats['total_bytes'] / 1024:8.1f} KB{mark}")
        row = [stamp, self.truth, app, round(conf, 3), smoothed, feats["total_packet"], feats["total_bytes"]]
        self.results.append(row)
        if self.log:
            self.writer.writerow(row)
            self.log.flush()

        if self.save_db:
            from llm_report.ingest import log_window
            log_window(ts, smoothed, conf, feats, source_file=self.source_name, window_sec=WINDOW_SEC)

        if self.anomaly_alert:
            threading.Thread(
                target=_check_anomaly_async,
                args=(stamp, smoothed, conf, dict(feats)),
                daemon=True,
            ).start()

    def summary(self):
        if self.log:
            self.log.close()
        if not (self.truth and self.results):
            return
        n = len(self.results)
        raw = sum(r[2] == self.truth for r in self.results)
        smooth = sum(r[4] == self.truth for r in self.results)
        print(f"\ntruth={self.truth}: per-window {raw}/{n} ({raw / n:.0%}), smoothed {smooth}/{n} ({smooth / n:.0%})")
        print("predicted:", dict(Counter(r[2] for r in self.results)))


def run_pcap(args, predict):
    for ts, feats in pcap_windows(args.pcap, args.local_ip or guess_local_ip(args.pcap)):
        predict(ts, feats)


def run_live(args, predict):
    from scapy.all import conf, get_if_addr, sniff

    iface = args.iface or conf.iface
    local_ip = args.local_ip or get_if_addr(iface)
    print(f"capturing on {iface} (this PC = {local_ip}), Ctrl+C to stop")
    win, lock = Window([local_ip]), threading.Lock()

    def on_packet(pkt):
        with lock:
            win.add(pkt)

    stop = threading.Event()
    threading.Thread(target=lambda: sniff(iface=iface, filter=args.filter, prn=on_packet, store=False,
                                          stop_filter=lambda _: stop.is_set()), daemon=True).start()
    end = time.time() + args.duration if args.duration else None
    try:
        while not end or time.time() < end:
            start = time.time()
            time.sleep(WINDOW_SEC)
            with lock:
                feats = win.features()
                win.reset()
            predict(start, feats)
    except KeyboardInterrupt:
        pass
    stop.set()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="models/window_model.joblib")
    p.add_argument("--iface", help='e.g. "Wi-Fi" (default: scapy default interface)')
    p.add_argument("--pcap", help="replay a capture file instead of live capture")
    p.add_argument("--local-ip", help="this PC's IP (auto-detected if omitted)")
    p.add_argument("--filter", default="ip", help="BPF filter for live capture")
    p.add_argument("--duration", type=int, default=0, help="stop after N seconds (0 = until Ctrl+C)")
    p.add_argument("--min-pkts", type=int, default=5, help="fewer packets than this = idle, no prediction")
    p.add_argument("--smooth", type=int, default=3, help="average probabilities over the last N windows")
    p.add_argument("--truth", help="real app, for the demo log only; not given to the model")
    p.add_argument("--log", help="write every prediction to this CSV")
    p.add_argument("--save-db", action="store_true", help="save 5s predictions to llm_report DB")
    p.add_argument("--anomaly-alert", action="store_true", help="run LLM anomaly check on each window")
    args = p.parse_args()

    source_name = Path(args.pcap).name if args.pcap else "live"
    predict = Predictor(
        args.model, args.min_pkts, args.smooth, args.truth, args.log,
        save_db=args.save_db, anomaly_alert=args.anomaly_alert, source_name=source_name,
    )
    (run_pcap if args.pcap else run_live)(args, predict)
    predict.summary()


if __name__ == "__main__":
    main()