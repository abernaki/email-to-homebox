## What this does

Monitors an IMAP mailbox for receipt emails, uses a local LLM (via Ollama) to extract structured purchase data, and creates items in a [Homebox](https://homebox.software) inventory instance.

## Running the app

```bash
source venv/bin/activate

# One-shot: process all emails in the Receipts folder once
python run_once.py

# Daemon: poll every CHECK_INTERVAL seconds (used in Docker)
python src/app.py
```

### Docker (primary deployment)

```bash
# Requires Ollama running natively on the host Mac
docker compose up --build -d
docker compose logs -f
```

The container reaches the host's Ollama via `host.docker.internal:11434`. The `data/` directory is bind-mounted for log/receipt persistence; `config/` is mounted read-only.

## Tests

```bash
# All tests
./run_tests.sh

# Fast unit tests only (no model loading)
./run_tests.sh --fast          # or: pytest -m unit

# Single test by keyword
pytest tests/test_receipts.py -k "best_buy" -v

# With coverage
./run_tests.sh --coverage
```

Test markers: `unit` (fast), `slow` (loads model), `integration` (needs email server), `edge_case`.

## Architecture

### Data flow

```
IMAP → EmailFetcher → ReceiptExtractor (Ollama) → app.py logic → HomeboxClient
                ↓                                       ↓
         extract images                         map + create items (2-step)
         run OCR if body < 200 chars            upload images / PDF
         (EasyOCR, lazy-loaded)                 move email to subfolder
```

### Key source files

| File                           | Role                                                                                                                                               |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/app.py`                   | Orchestrates the full pipeline; contains `process_receipt()`, item mapping, image/PDF upload, email folder routing                                 |
| `src/email_fetcher.py`         | IMAP client; extracts body text, images (attachments + `<img>` tags), OCR from photos                                                              |
| `src/receipt_extractor_mlx.py` | **Now Ollama-based** despite the filename. Calls `POST /api/chat` on the configured Ollama host, parses JSON response, validates price consistency |
| `src/homebox_client.py`        | Homebox API client; handles token auth + refresh                                                                                                   |
| `src/image_handler.py`         | DuckDuckGo image search fallback; image filtering/matching                                                                                         |
| `run_once.py`                  | Thin wrapper around the same pipeline for one-off batch runs                                                                                       |

### Homebox API — two-step item creation

Homebox's create endpoint only accepts a small set of fields. Purchase details require a separate PUT:

1. `POST /api/v1/items` — name, locationId, description, quantity
2. `PUT /api/v1/items/{id}` — purchasePrice, purchaseFrom, purchaseTime, manufacturer, modelNumber, serialNumber

The PUT must include `name` and `locationId` even when not changing them or they get cleared.

### Confidence scoring

The LLM returns a self-assessed `confidence` field. `app.py` also cross-checks the sum of item prices against the receipt total and penalises confidence when the gap exceeds 20% (to allow for tax/shipping). Items below `MIN_CONFIDENCE` (default 0.7) are moved to the Manual Review folder rather than added to Homebox.

### IMAP folder separators

Most providers (Gmail, Fastmail, Outlook, iCloud) use `/` as the subfolder separator: `"Receipts/Homebox"`. Some use `.`. See `IMAP_PROVIDERS.md` for provider-specific notes. The code always re-SELECTs the source folder before COPY/DELETE because IMAP requires SELECTED state.

## Configuration

All secrets go in `.env` (see `env.sample`). Behaviour is tuned in `config/config.yml` — prompts, category maps, OCR thresholds, image-search limits, consumable/non-physical filtering rules, and Homebox location defaults. The config path can be overridden with `CONFIG_FILE` env var.

Processed receipts are saved as YAML in `data/processed/`; failures land in `data/failed/` for manual review. Main log: `data/logs/processor.log`.
