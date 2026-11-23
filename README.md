# encrypted-traffic-classifier

**Computer Network Team 9 (PacketSniffers)** — Identifying Applications from Encrypted Network Traffic Using Machine Learning

Most traffic today is encrypted (TLS, QUIC), so we can't look at payloads. Instead we classify which app produced a flow
using only header-level information: packet sizes, directions, timing, and ports.

## Pipeline

```
capture.py      →  data/raw/<app>/*.pcap        (labeled captures)
features.py     →  data/features.csv             (one row per flow)
train.py        →  models/model.joblib           (best model + report)
live_demo.py    →  real-time classification of live traffic
```

A **flow** = bidirectional 5-tuple (protocol, IPs, ports), cut into windows of at most 30 s.
Per flow we extract ~40 features: packet/byte counts per direction, size and inter-arrival-time statistics,
rates, and the signed sizes of the first 10 packets (+ = upload, − = download).

## Setup

```bash
pip install -r requirements.txt
```

Capturing needs admin rights. **Windows:** install [Npcap](https://npcap.com) and run the terminal as administrator.
**macOS/Linux:** run with `sudo`.

## Usage

### 0. Test the pipeline with synthetic data (no capture needed)

```bash
python scripts/make_synthetic.py --out data/synthetic
python -m src.features --raw data/synthetic --out data/synthetic_features.csv
python -m src.train --data data/synthetic_features.csv --model models/synthetic.joblib
```

### 1. Capture labeled traffic

Use **only one app** during each capture (close other tabs, pause updates/cloud sync).

```bash
python -m src.capture --label youtube   --duration 180 --iface "Wi-Fi"
python -m src.capture --label kakaotalk --duration 180 --iface "Wi-Fi"
python -m src.capture --label game      --duration 180 --iface "Wi-Fi"
python -m src.capture --label web       --duration 180 --iface "Wi-Fi"
```

Aim for **3+ captures per app**, ideally by different members / networks, so the test set can use unseen captures.
Wireshark captures saved as `.pcap`/`.pcapng` into `data/raw/<app>/` work too.

### 2. Extract features

```bash
python -m src.features --raw data/raw --out data/features.csv
```

### 3. Train and evaluate

```bash
python -m src.train --data data/features.csv --model models/model.joblib
python -m src.train --data data/features.csv --model models/model_noport.joblib --no-port
```

- Test set = held-out capture files per app (falls back to a random split if an app has only one capture).
- Prints accuracy, macro-F1, per-class report, confusion matrix, top features.
- `--no-port` removes `server_port` — compare both to see how much the model relies on ports vs. traffic shape.
- `pip install xgboost` to also compare an XGBoost model.

### 4. Live demo

```bash
python -m src.live_demo --model models/model.joblib --iface "Wi-Fi"
```

## Week 10: 5-second window model (team plan)

Simpler pipeline used for the demo: every 5 s, count packets/bytes sent and received by this PC and predict the app.

```bash
python -m src.window_features --raw data/raw --out data/full_features.csv
python -m src.train_window --data data/full_features.csv --model models/window_model.joblib
python -m src.live_predict --model models/window_model.joblib --iface "Wi-Fi"          # live (admin + Npcap)
python -m src.live_predict --model models/window_model.joblib --pcap some_capture.pcapng # replay a file
```

Columns, results and the demo record: [docs/week10_demo_record.md](docs/week10_demo_record.md).

## Notes

- Background traffic (OS updates, cloud sync, DNS) gets the capture's label too. Keep captures clean, or add an
  `other` class captured while idle.
- Raw pcaps are git-ignored: they can be large and include private data. Share them via the team drive.
- The synthetic data is trivially separable; its 100% accuracy says nothing about real traffic.

## Team

| Role | Member |
|---|---|
| P1 (Leader) | 조대현 |
| P2 | 윤한음 |
| P3 | ZHANG ZHAOJU |
| P4 | 이상규 |

Team doc: https://docs.google.com/document/d/12SZTmh0J75AUXhv_bg8-aJhIH3VihcRrUMHkwFEd0nI/edit
