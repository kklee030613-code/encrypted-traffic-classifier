"""Capture labeled traffic into data/raw/<label>/.

Run this while using ONLY the target app (close other tabs/apps), e.g.:

    python -m src.capture --label youtube --duration 180 --iface "Wi-Fi"

Needs admin rights. On Windows install Npcap (https://npcap.com) first.
"""
import argparse
from datetime import datetime
from pathlib import Path

from scapy.all import sniff, wrpcap, conf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True, help="app name, e.g. youtube, kakaotalk, game, web")
    p.add_argument("--duration", type=int, default=120, help="seconds to capture")
    p.add_argument("--iface", default=None, help="network interface (default: scapy default)")
    p.add_argument("--filter", default="tcp or udp", help="BPF filter")
    p.add_argument("--out", default="data/raw")
    args = p.parse_args()

    out_dir = Path(args.out) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}_{datetime.now():%Y%m%d_%H%M%S}.pcap"

    print(f"Capturing '{args.label}' on {args.iface or conf.iface} for {args.duration}s ...")
    pkts = sniff(iface=args.iface, filter=args.filter, timeout=args.duration)
    wrpcap(str(path), pkts)
    print(f"Saved {len(pkts)} packets -> {path}")


if __name__ == "__main__":
    main()
