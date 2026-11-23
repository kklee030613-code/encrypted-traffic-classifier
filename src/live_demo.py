"""Classify live traffic with a trained model.

    python -m src.live_demo --model models/model.joblib --iface "Wi-Fi"

Needs admin rights (and Npcap on Windows). Every --interval seconds it prints
the active flows with the predicted app and confidence.
"""
import argparse
import threading
import time

import joblib
import pandas as pd
from scapy.all import sniff

from src.flows import MIN_PKTS, FlowTable, flow_features


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="models/model.joblib")
    p.add_argument("--iface", default=None)
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--window", type=float, default=30.0)
    p.add_argument("--top", type=int, default=15, help="show the N busiest flows")
    args = p.parse_args()

    bundle = joblib.load(args.model)
    model, enc, columns = bundle["model"], bundle["encoder"], bundle["columns"]

    table = FlowTable(window=args.window)
    lock = threading.Lock()

    def on_packet(pkt):
        with lock:
            table.add(float(pkt.time), pkt)

    threading.Thread(
        target=sniff, kwargs={"iface": args.iface, "filter": "tcp or udp", "prn": on_packet, "store": False}, daemon=True
    ).start()
    print("Sniffing... Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(args.interval)
            with lock:
                table.expire(time.time())
                flows = [f for f in table.active.values() if len(f) >= MIN_PKTS]
                flows = sorted(flows, key=len, reverse=True)[: args.top]
                feats = [flow_features(f) for f in flows]
            if not flows:
                print("(no active flows)")
                continue

            X = pd.DataFrame(feats).reindex(columns=columns, fill_value=0)
            proba = model.predict_proba(X)
            print(time.strftime("%H:%M:%S"), "-" * 60)
            for f, pr in zip(flows, proba):
                i = pr.argmax()
                proto = "TCP" if f.proto == 6 else "UDP"
                print(f"  {proto} {f.server[0]:>39}:{f.server[1]:<5} {len(f):6d} pkts  ->  "
                      f"{enc.classes_[i]:12s} {pr[i]:.0%}")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
