"""Generate small synthetic pcaps to test the pipeline before real captures exist.

    python scripts/make_synthetic.py --out data/synthetic

The traffic profiles are rough imitations (video = big downstream bursts,
chat = small sporadic packets, game = steady small UDP, web = short bursty
TCP). Results on this data say nothing about real-world accuracy.
"""
import argparse
import random
from pathlib import Path

from scapy.all import IP, TCP, UDP, Raw, wrpcap

CLIENT = "192.168.0.10"


def make_flow(profile, t0, server, sport, rng):
    pkts, t = [], t0
    n = rng.randint(*profile["n"])
    for _ in range(n):
        up = rng.random() < profile["up_ratio"]
        size = max(1, int(rng.gauss(*(profile["up_size"] if up else profile["down_size"]))))
        src, dst = (CLIENT, server) if up else (server, CLIENT)
        sp, dp = (sport, profile["port"]) if up else (profile["port"], sport)
        l4 = UDP(sport=sp, dport=dp) if profile["udp"] else TCP(sport=sp, dport=dp, flags="PA")
        pkt = IP(src=src, dst=dst) / l4 / Raw(b"\x00" * min(size, 1400))
        pkt.time = t
        pkts.append(pkt)
        t += rng.expovariate(1 / profile["iat"])
    return pkts


PROFILES = {
    "youtube": dict(n=(80, 200), up_ratio=0.15, up_size=(60, 10), down_size=(1300, 150), iat=0.01, port=443, udp=True),
    "kakaotalk": dict(n=(6, 30), up_ratio=0.5, up_size=(150, 60), down_size=(200, 80), iat=0.8, port=443, udp=False),
    "game": dict(n=(100, 300), up_ratio=0.5, up_size=(90, 20), down_size=(120, 30), iat=0.03, port=7777, udp=True),
    "web": dict(n=(10, 60), up_ratio=0.3, up_size=(400, 200), down_size=(900, 400), iat=0.05, port=443, udp=False),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/synthetic")
    p.add_argument("--files", type=int, default=3, help="pcaps per app")
    p.add_argument("--flows", type=int, default=40, help="flows per pcap")
    args = p.parse_args()

    rng = random.Random(0)
    for label, prof in PROFILES.items():
        d = Path(args.out) / label
        d.mkdir(parents=True, exist_ok=True)
        for k in range(args.files):
            pkts = []
            for i in range(args.flows):
                server = f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
                pkts += make_flow(prof, 1_700_000_000 + i * 2.0, server, 40000 + i, rng)
            pkts.sort(key=lambda x: x.time)
            wrpcap(str(d / f"{label}_{k}.pcap"), pkts)
        print(f"{label}: {args.files} files")


if __name__ == "__main__":
    main()
