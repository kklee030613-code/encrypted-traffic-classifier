"""5-second window features, shared by training and the live predictor.

Same columns as ZHANG's batch_run.py, plus avg_packet_len. Using one function
for both the training CSV and live capture keeps the model input identical.

    # all captures under data/raw/<app>/ -> one CSV (data/synthetic is not touched)
    python -m src.window_features --raw data/raw --out data/full_features.csv

    # one file, label given by hand
    python -m src.window_features --pcap yt_web_01.pcapng --label youtube --out test.csv
"""
import argparse
import csv
import ipaddress
from collections import Counter
from pathlib import Path

from scapy.all import IP, PcapReader

WINDOW_SEC = 5
# Model input columns, in this order. app_label is the answer only, never an input.
COLUMNS = [
    "send_packet_count", "send_bytes",
    "recv_packet_count", "recv_bytes",
    "total_packet", "total_bytes", "avg_packet_len",
]
HEADER = ["window_start_time", "app_label", "pcap_filename"] + COLUMNS
PCAP_EXT = {".pcap", ".pcapng", ".cap"}


class Window:
    """Counts one window of traffic, split by direction relative to this PC."""

    def __init__(self, local_ips):
        self.local_ips = set(local_ips)
        self.reset()

    def reset(self):
        self.send_p = self.send_b = self.recv_p = self.recv_b = 0

    def add(self, pkt):
        if not pkt.haslayer(IP):
            return
        size = len(pkt)
        if pkt[IP].src in self.local_ips:
            self.send_p += 1
            self.send_b += size
        elif pkt[IP].dst in self.local_ips:
            self.recv_p += 1
            self.recv_b += size

    def features(self):
        total_p = self.send_p + self.recv_p
        total_b = self.send_b + self.recv_b
        return {
            "send_packet_count": self.send_p, "send_bytes": self.send_b,
            "recv_packet_count": self.recv_p, "recv_bytes": self.recv_b,
            "total_packet": total_p, "total_bytes": total_b,
            "avg_packet_len": round(total_b / total_p, 2) if total_p else 0.0,
        }


def guess_local_ip(path, sample=5000):
    """The private IP seen most often in the first packets = this PC."""
    cnt = Counter()
    with PcapReader(str(path)) as reader:
        for i, pkt in enumerate(reader):
            if i >= sample:
                break
            if pkt.haslayer(IP):
                for ip in (pkt[IP].src, pkt[IP].dst):
                    if ipaddress.ip_address(ip).is_private:
                        cnt[ip] += 1
    return cnt.most_common(1)[0][0] if cnt else None


def pcap_windows(path, local_ip=None, window=WINDOW_SEC):
    """Yield (window_start, features) for fixed 5 s windows from a capture file.

    Windows are fixed slots [t0, t0+5), [t0+5, t0+10), ... like the live timer.
    Empty slots in between are skipped; the last partial window is kept.
    """
    local_ip = local_ip or guess_local_ip(path)
    w = Window([local_ip])
    t0 = slot = None
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            t = float(pkt.time)
            if t0 is None:
                t0, slot = t, 0
            s = int((t - t0) // window)
            if s != slot:
                if w.send_p + w.recv_p:
                    yield t0 + slot * window, w.features()
                w.reset()
                slot = s
            w.add(pkt)
    if t0 is not None and w.send_p + w.recv_p:
        yield t0 + slot * window, w.features()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", help="folder with <app>/<capture>.pcap(ng) subfolders")
    p.add_argument("--pcap", help="single capture file (use with --label)")
    p.add_argument("--label", help="app label for --pcap")
    p.add_argument("--out", default="data/full_features.csv")
    args = p.parse_args()

    jobs = []
    if args.pcap:
        jobs.append((args.label or "unknown", Path(args.pcap)))
    if args.raw:
        for app_dir in sorted(Path(args.raw).iterdir()):
            if app_dir.is_dir():
                jobs += [(app_dir.name, f) for f in sorted(app_dir.iterdir()) if f.suffix.lower() in PCAP_EXT]
    if not jobs:
        p.error("give --raw or --pcap")

    rows, problems = [], []
    for label, path in jobs:
        try:
            ip = guess_local_ip(path)
            got = [[round(ts, 6), label, path.name] + [f[c] for c in COLUMNS] for ts, f in pcap_windows(path, ip)]
        except Exception as e:  # unreadable file
            problems.append(f"{path.name}: read failed ({e})")
            continue
        print(f"{label:10s} {path.name:40s} local_ip={ip}  windows={len(got)}")
        if not got:
            problems.append(f"{path.name}: 0 windows")
        rows += got

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([HEADER] + rows)
    print(f"\n{len(rows)} rows -> {args.out}")
    for msg in problems:
        print("PROBLEM:", msg)


if __name__ == "__main__":
    main()
