# Week 10 — Live prediction integration and demo record (P4 이상규)

## One command

```bash
pip install -r requirements.txt
# 1) 5 s features from all real captures (data/synthetic is not used)
python -m src.window_features --raw data/raw --out data/full_features.csv
# 2) train (holds out one capture file per app for the score, then refits on all)
python -m src.train_window --data data/full_features.csv --model models/window_model.joblib
# 3a) LIVE: capture -> 5 s features -> prediction -> app name (admin terminal + Npcap)
python -m src.live_predict --model models/window_model.joblib --iface "Wi-Fi" --truth youtube --log demo/live_youtube.csv
# 3b) REPLAY a capture the model never saw (no admin needed)
python -m src.live_predict --model models/window_model.joblib --pcap data/yt_web_01.pcapng --truth youtube
```

`--truth` is never given to the model. It is only written to the log so the real app can be compared with the prediction.

## Model input contract (models/window_model.json)

| # | column | meaning (one 5 s window, direction relative to this PC) |
|---|---|---|
| 1 | send_packet_count | packets sent |
| 2 | send_bytes | bytes sent |
| 3 | recv_packet_count | packets received |
| 4 | recv_bytes | bytes received |
| 5 | total_packet | 1 + 3 |
| 6 | total_bytes | 2 + 4 |
| 7 | avg_packet_len | total_bytes / total_packet |

Output: one of `kakaotalk`, `web`, `youtube` (the model returns the name directly). `app_label` and `pcap_filename` are kept in the CSV but never used as inputs.
Windows with fewer than 5 packets are shown as `idle` and not predicted.

## Data check (Week 10 data/raw, 9 files)

All 9 files were read. No file had 0 windows. 312 windows in total.

| app | file | windows |
|---|---|---|
| kakaotalk | kakaotalk_20261117_161327.pcap | 32 |
| kakaotalk | kakaotalk_20261117_161745.pcap | 34 |
| kakaotalk | kakaotalk_20261117_162201.pcap | 34 |
| web | web_20261117_162752.pcap | 36 |
| web | web_20261117_163203.pcap | 36 |
| web | web_20261117_163529.pcap | 36 |
| youtube | youtube_20261117_155826.pcap | 36 |
| youtube | youtube_20261117_160423.pcap | 35 |
| youtube | youtube_20261117_160828.pcap | 33 |

`yt_web_01.pcapng` (YouTube in a browser, label = youtube) is read fine by scapy. pcapng needs no conversion. It gives 9 windows (about 45 s).

## Results

**Held-out capture files** (one per app, not used in training): accuracy 0.825, macro-F1 0.826.

| true \ predicted | kakaotalk | web | youtube |
|---|---|---|---|
| kakaotalk | 23 | 0 | 9 |
| web | 1 | 30 | 5 |
| youtube | 3 | 0 | 32 |

**New session yt_web_01.pcapng** (never used in training, truth = youtube):
per window 4/8 correct (50%), smoothed over the last 3 windows 5/8 (62%). Log: `demo/replay_yt_web_01.csv`.

## What this shows / next steps

- Big buffering bursts (3,000+ packets in 5 s) are recognised as YouTube. Quiet windows between bursts look like web or KakaoTalk, so they are often wrong.
- yt_web_01 is only ~45 s long. Longer test sessions (2–3 min) will give a fairer score.
- Most errors are kakaotalk ↔ youtube. More captures per app (from other members / networks) should help most.

## Live test (2026-11-22, P4 PC, wired Ethernet 192.168.0.82, Npcap 1.90)

The program got no app name; `--truth` was only written to the logs. Neither session was used in training.
Npcap with default options captured fine without an admin terminal.

| session | what ran | windows | per window | smoothed (last 3) | log |
|---|---|---|---|---|---|
| YouTube, 3 min | nature video in a browser, 480p | 36 | 19/36 (53%) | 20/36 (56%) | demo/live_youtube.csv |
| — first 22 windows (before the burst) | | 22 | 17/22 (77%) | 20/22 (91%) | |
| Web, 3 min | 14 sites (Wikipedia, GitHub, BBC, MDN, ...) | 35 | 34/35 (97%) | 35/35 (100%) | demo/live_web.csv |

**Background burst:** from 19:49:46 (YouTube test) and 19:52:51 (web test) the PC sent/received
15,000–25,000 packets per 5 s (~3 MB/s). Neither a 480p video nor page browsing makes that much traffic,
so another program was downloading (Steam, Meta/Oculus and several updaters were running).
The model labels that burst `web`. That is why the YouTube score drops after 2 minutes, and why the
last ~16 windows of the web test count as correct for the wrong reason.

**Takeaways**
- In clean conditions the pipeline works live: YouTube 91% and web 100% (smoothed).
- Because the features count all traffic of the PC, any background download changes the answer.
  For the final demo: close Steam/launchers/cloud sync first, or move to per-flow features (src/flows.py) so each connection is classified separately.
- KakaoTalk was not tested live yet.
