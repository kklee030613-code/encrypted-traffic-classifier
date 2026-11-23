"""Flow assembly and per-flow feature extraction.

A flow is the bidirectional 5-tuple (protocol, ip/port pairs). The side that
sends the first packet is treated as the client, so "up" = client -> server
and "down" = server -> client. Only header-level information (sizes, timing,
ports) is used, so this works for encrypted traffic (TLS, QUIC, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scapy.layers.inet import IP, TCP, UDP
from scapy.layers.inet6 import IPv6

N_FIRST = 10  # signed sizes of the first N packets are used as features
MIN_PKTS = 5  # flows shorter than this are dropped


def parse_packet(pkt):
    """Return (key, src, sport, size) for TCP/UDP over IPv4/IPv6, else None."""
    if IP in pkt:
        ip = pkt[IP]
        size = int(ip.len) if ip.len else len(ip)
    elif IPv6 in pkt:
        ip = pkt[IPv6]
        size = int(ip.plen) + 40 if ip.plen else len(ip)
    else:
        return None

    if TCP in pkt:
        l4, proto = pkt[TCP], 6
    elif UDP in pkt:
        l4, proto = pkt[UDP], 17
    else:
        return None

    a = (ip.src, int(l4.sport))
    b = (ip.dst, int(l4.dport))
    key = (proto,) + (a + b if a <= b else b + a)
    return key, a, size


@dataclass
class Flow:
    proto: int
    client: tuple  # (ip, port) of the side that sent the first packet
    server: tuple
    start: float
    last: float
    times: list = field(default_factory=list)
    sizes: list = field(default_factory=list)  # + up, - down

    def add(self, ts: float, src: tuple, size: int) -> None:
        self.times.append(ts)
        self.sizes.append(size if src == self.client else -size)
        self.last = ts

    def __len__(self) -> int:
        return len(self.sizes)


class FlowTable:
    """Groups packets into flows.

    A flow is closed when it has been idle for `idle_timeout` seconds or has
    lasted `window` seconds. Cutting long flows into windows gives more
    samples from long sessions (e.g. one YouTube video) and lets the live
    demo classify a flow while it is still running.
    """

    def __init__(self, window: float = 30.0, idle_timeout: float = 15.0):
        self.window = window
        self.idle_timeout = idle_timeout
        self.active: dict[tuple, Flow] = {}

    def add(self, ts: float, pkt) -> list[Flow]:
        parsed = parse_packet(pkt)
        if parsed is None:
            return []
        key, src, size = parsed
        closed = []

        flow = self.active.get(key)
        if flow and (ts - flow.last > self.idle_timeout or ts - flow.start > self.window):
            closed.append(self.active.pop(key))
            flow = None
        if flow is None:
            dst = (key[3], key[4]) if src == (key[1], key[2]) else (key[1], key[2])
            flow = Flow(proto=key[0], client=src, server=dst, start=ts, last=ts)
            self.active[key] = flow
        flow.add(ts, src, size)
        return closed

    def expire(self, now: float) -> list[Flow]:
        """Close flows idle for longer than idle_timeout."""
        done = [k for k, f in self.active.items() if now - f.last > self.idle_timeout]
        return [self.active.pop(k) for k in done]

    def flush(self) -> list[Flow]:
        flows = list(self.active.values())
        self.active.clear()
        return flows


def _stats(prefix: str, values) -> dict:
    if len(values) == 0:
        return {f"{prefix}_mean": 0.0, f"{prefix}_std": 0.0, f"{prefix}_min": 0.0, f"{prefix}_max": 0.0}
    v = np.asarray(values, dtype=float)
    return {f"{prefix}_mean": v.mean(), f"{prefix}_std": v.std(), f"{prefix}_min": v.min(), f"{prefix}_max": v.max()}


def flow_features(flow: Flow) -> dict:
    sizes = np.asarray(flow.sizes, dtype=float)
    times = np.asarray(flow.times, dtype=float)
    up, down = sizes[sizes > 0], -sizes[sizes < 0]
    duration = max(times[-1] - times[0], 1e-6)
    iat = np.diff(times)

    feats = {
        "proto": flow.proto,
        "server_port": flow.server[1],
        "n_pkts": len(sizes),
        "n_up": len(up),
        "n_down": len(down),
        "bytes_up": up.sum(),
        "bytes_down": down.sum(),
        "duration": duration,
        "pkts_per_sec": len(sizes) / duration,
        "bytes_per_sec": np.abs(sizes).sum() / duration,
        "down_up_byte_ratio": down.sum() / (up.sum() + 1.0),
    }
    feats.update(_stats("size", np.abs(sizes)))
    feats.update(_stats("up_size", up))
    feats.update(_stats("down_size", down))
    feats.update(_stats("iat", iat))

    first = list(sizes[:N_FIRST]) + [0.0] * max(0, N_FIRST - len(sizes))
    for i, s in enumerate(first):
        feats[f"first_{i}"] = s
    return feats
