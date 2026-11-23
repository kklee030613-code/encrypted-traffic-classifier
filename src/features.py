"""Turn labeled pcaps into a flow-feature CSV.

    python -m src.features --raw data/raw --out data/features.csv

Each subfolder of --raw is a label; every .pcap/.pcapng inside it is read.
"""
import argparse
from pathlib import Path

import pandas as pd
from scapy.utils import PcapReader

from src.flows import MIN_PKTS, FlowTable, flow_features


def pcap_to_rows(path: Path, label: str, window: float) -> list[dict]:
    table = FlowTable(window=window)
    flows = []
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            flows += table.add(float(pkt.time), pkt)
    flows += table.flush()

    rows = []
    for f in flows:
        if len(f) < MIN_PKTS:
            continue
        row = flow_features(f)
        row["label"] = label
        row["source"] = path.name  # used for group-wise train/test split
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default="data/raw")
    p.add_argument("--out", default="data/features.csv")
    p.add_argument("--window", type=float, default=30.0, help="max flow length in seconds")
    args = p.parse_args()

    rows = []
    for label_dir in sorted(d for d in Path(args.raw).iterdir() if d.is_dir()):
        for path in sorted(label_dir.glob("*.pcap*")):
            r = pcap_to_rows(path, label_dir.name, args.window)
            print(f"{label_dir.name:12s} {path.name:40s} {len(r):5d} flows")
            rows += r

    if not rows:
        raise SystemExit(f"No flows found under {args.raw}")
    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"\n{len(df)} flows -> {args.out}")
    print(df["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
