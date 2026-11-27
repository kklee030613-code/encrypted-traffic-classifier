# encrypted-traffic-classifier

**Computer Network Team 9 (PacketSniffers)** — Identifying Applications from Encrypted Network Traffic Using Machine Learning

Most traffic today is encrypted (TLS, QUIC), so we can't look at payloads. Instead we classify which app produced a flow
using only header-level information: packet sizes, directions, timing, and ports.

## Pipeline

```text
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
python -m src.live_predict --model models/window_model.joblib --iface "Wi-Fi"           # live (admin + Npcap)
python -m src.live_predict --model models/window_model.joblib --pcap some_capture.pcapng  # replay a file
```

Columns, results and the demo record: [docs/week10_demo_record.md](docs/week10_demo_record.md).

## LLM Extensions (Report Chatbot & Anomaly Alert)

Two LLM-powered application layers built on top of the 5-second classifier outputs:

1. **LLM 리포트·챗봇 (`llm_report`)**: Saves predicted app usage into SQLite (`traffic_logs`), answers natural-language questions (e.g., *"오늘 유튜브 얼마나 썼어?"*), and generates period usage summaries.
2. **LLM 이상 알림 (`llm_anomaly`)**: Uses rule-based heuristics to identify suspicious traffic candidates, then asks an LLM to assess them before raising alerts. The LLM's assessment may be incorrect and should not be treated as a definitive security judgment.

### Quick Start: Try Both Features in Mock Mode

This example creates a small test CSV and runs both LLM extensions without a
trained classifier, packet capture, or API key. Run the commands from the
repository root.

#### 1. Install dependencies and enable Mock mode

```bash
pip install -r requirements.txt
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force -Path llm_data | Out-Null
$Env:ENABLE_MOCK_LLM = "true"
$Env:LLM_REPORT_DB_PATH = Join-Path (Get-Location) "llm_data/llm_report.db"
$Env:LLM_ANOMALY_DB_PATH = Join-Path (Get-Location) "llm_data/llm_anomaly.db"
```

**macOS/Linux:**

```bash
mkdir -p llm_data
export ENABLE_MOCK_LLM="true"
export LLM_REPORT_DB_PATH="$PWD/llm_data/llm_report.db"
export LLM_ANOMALY_DB_PATH="$PWD/llm_data/llm_anomaly.db"
```

These environment variables apply to the current terminal session.

#### 2. Create a test prediction CSV

The following command creates `llm_data/example.csv` with one artificial
5-second prediction window:

```bash
python -c "from pathlib import Path; Path('llm_data').mkdir(exist_ok=True); Path('llm_data/example.csv').write_text('time,predicted,confidence,total_packet,total_bytes\n12:00:00,youtube,0.8,100,4000000\n', encoding='utf-8')"
```

The traffic volume is deliberately high so that the anomaly rules identify it
as a candidate. This is test data, not a real capture.

#### 3. Import the CSV and ask a question

```bash
python -m llm_report.cli ingest --csv llm_data/example.csv
python -m llm_report.cli query --query "오늘 유튜브 얼마나 썼어?" --user-id 1
```

The ingest command should print `Ingested 1 rows from llm_data/example.csv`.
The query result appears in the terminal. Mock responses are for testing the
workflow and may differ from real LLM responses.

By default, `ingest` assigns records to user ID `1` and uses today's date.
Alternatively, specify a user and date:

```bash
python -m llm_report.cli ingest --csv llm_data/example.csv --user-id 1 --date 2026-11-26
```

Running both ingest examples can store the same data under two different dates.

**Re-import behavior:** Before importing, existing records with the same user
ID, source filename and date are deleted. The filename comparison uses only the
base name, not the full path.

For a period summary:

```bash
python -m llm_report.cli summarize --user-id 1 --period-start 2026-11-26T00:00:00 --period-end 2026-11-28T23:59:59
```

Adjust the period to include the date used during ingestion. The example above
includes records imported with `--date 2026-11-26`. The result appears in the
terminal.

#### 4. Run the anomaly check

```bash
python -m llm_anomaly.cli --csv llm_data/example.csv --show-all
```

The test row should be identified as a rule-based candidate because its traffic
volume exceeds 3,000,000 bytes. Results appear in the terminal. The final
result depends on the Mock judgment; `--show-all` also displays results judged
as false positives.

By default, up to five rule-matched candidates are sent for LLM verification.
Change this with `--limit`.

Mock mode tests the workflow without calling an external LLM. It does not
evaluate the quality of a real LLM's responses.

#### 5. Use real data or a real LLM

- Replace `llm_data/example.csv` with a compatible project CSV. See **Supported
  CSV formats** below.
- To use OpenRouter, follow **Environment Variables** below and set
  `ENABLE_MOCK_LLM=false`. Real API calls require network access and may incur
  charges.
- To log live predictions or replay a capture, follow **Real-time Classifier +
  DB Logging & Anomaly Alert** below. A trained model is required.

### Supported CSV formats

Both `llm_report.cli ingest` and `llm_anomaly.cli` recognize the formats below.
If neither a prediction column nor `app_label` is present, the row is skipped.

#### Prediction CSV

Example header and row:

```csv
time,predicted,confidence,total_packet,total_bytes
12:00:00,youtube,0.8,100,4000000
```

| Column | Meaning | If missing or empty |
|---|---|---|
| `predicted` | Predicted application | `unknown` if `smoothed` is also empty |
| `smoothed` | Smoothed application prediction; preferred over `predicted` | Falls back to `predicted` |
| `time` | Time of the window, e.g. `12:00:00` | Empty for report ingestion; `00:00:00` for anomaly detection |
| `confidence` | Prediction confidence | `0.0` |
| `total_packet` | Number of packets | `0` |
| `total_bytes` | Traffic volume in bytes | `0` |

At least one of the `predicted` or `smoothed` **columns** must be present to
select this format.

For anomaly detection, use a time such as `12:00:00`. If `time` is missing,
it defaults to `00:00:00`, which can affect late-night rules. Missing
`confidence` defaults to `0.0`, which can affect low-confidence rules.

For this format, both modules set `send_bytes` to `0` and `recv_bytes` to
`total_bytes`, even if separate send/receive columns exist. Therefore,
upload-specific anomaly rules cannot detect actual uploads from this format.

#### Feature CSV

Example header and row:

```csv
window_start_time,app_label,total_packet,total_bytes,send_bytes,recv_bytes
1795694400,youtube,100,4000000,1500000,2500000
```

| Column | Meaning | If missing or empty |
|---|---|---|
| `app_label` | Application label; selects this format when no prediction column is present | Empty value becomes `unknown` |
| `window_start_time` | Unix timestamp in seconds, converted to local time | Current time for report ingestion; `00:00:00` for anomaly detection |
| `total_packet` | Number of packets | `0` |
| `total_bytes` | Total traffic volume in bytes | `0` |
| `send_bytes` | Sent bytes | `0` |
| `recv_bytes` | Received bytes | `0` |

For this format, confidence is set to `1.0`. During report ingestion, the
record's **date** comes from `--date` or defaults to today; it is not taken from
`window_start_time`.

Numeric values must be parseable as numbers. Report ingestion treats each row as
a 5-second window by default.

### Environment Variables

By default (`ENABLE_MOCK_LLM=true`), both modules run in **Mock mode** without calling an external API. To enable real LLM responses via OpenRouter:

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force -Path llm_data | Out-Null
$Env:LLM_PROVIDER        = "openrouter"
$Env:OPENROUTER_API_KEY  = "sk-or-v1-..."
$Env:OPENROUTER_MODEL    = "openai/gpt-4o-mini"
$Env:ENABLE_MOCK_LLM     = "false"
$Env:LLM_REPORT_DB_PATH  = Join-Path (Get-Location) "llm_data/llm_report.db"
$Env:LLM_ANOMALY_DB_PATH = Join-Path (Get-Location) "llm_data/llm_anomaly.db"
```

**macOS/Linux (bash/zsh):**

```bash
mkdir -p llm_data
export LLM_PROVIDER="openrouter"
export OPENROUTER_API_KEY="sk-or-v1-..."
export OPENROUTER_MODEL="openai/gpt-4o-mini"
export ENABLE_MOCK_LLM="false"
export LLM_REPORT_DB_PATH="$PWD/llm_data/llm_report.db"
export LLM_ANOMALY_DB_PATH="$PWD/llm_data/llm_anomaly.db"
```

Replace the example API key and model with your own values. Real API calls
require network access and may incur charges. Before using private traffic
data, check what information is sent to the provider.

### 1) Real-time Classifier + DB Logging & Anomaly Alert

Add `--save-db` and/or `--anomaly-alert` to `src.live_predict` (existing behavior without flags is unchanged):

```bash
python -m src.live_predict --model models/window_model.joblib --iface "Wi-Fi" --save-db --anomaly-alert
python -m src.live_predict --model models/window_model.joblib --pcap some_capture.pcapng --save-db --anomaly-alert
```

Replace `"Wi-Fi"` with your capture interface, or replace `some_capture.pcapng`
with the path to your capture. See **Week 10: 5-second window model** above for
model training.

### 2) LLM Report & Chatbot (`llm_report`)

Ingest existing prediction CSV logs (optional if `--save-db` was already used), then ask questions or generate a summary:

```bash
python -m llm_report.cli ingest --csv demo/live_youtube.csv
python -m llm_report.cli ingest --csv demo/live_web.csv

python -m llm_report.cli query --query "오늘 유튜브 얼마나 썼어?" --user-id 1
python -m llm_report.cli summarize --user-id 1 --period-start 2026-11-26T00:00:00 --period-end 2026-11-28T23:59:59
```

Replace the CSV paths with compatible files available on your machine. Adjust
the summary period to match the dates of your stored records.

### 3) LLM Anomaly Alert (`llm_anomaly`)

Run rule-based filtering and LLM assessment on a prediction or feature CSV:

```bash
python -m llm_anomaly.cli --csv demo/live_youtube.csv
python -m llm_anomaly.cli --csv demo/replay_yt_web_01.csv --show-all
```

Replace the CSV paths with compatible files available on your machine.

## Notes

- Background traffic (OS updates, cloud sync, DNS) gets the capture's label too. Keep captures clean, or add an
  `other` class captured while idle.
- Raw pcaps are git-ignored: they can be large and include private data. Share them via the team drive.
- The synthetic data is trivially separable; its 100% accuracy says nothing about real traffic.
- Never commit API keys (`set_env.ps1`, `.env`) or local SQLite DB files (`*.db`) to git.

## Team

| Role | Member |
|---|---|
| P1 (Leader) | 조대현 |
| P2 | 윤한음 |
| P3 | ZHANG ZHAOJU |
| P4 | 이상규 |

Team doc: https://docs.google.com/document/d/12SZTmh0J75AUXhv_bg8-aJhIH3VihcRrUMHkwFEd0nI/edit