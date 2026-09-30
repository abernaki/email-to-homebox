## What this does

Monitors an IMAP mailbox for receipt emails, uses a local LLM (via Ollama) to extract structured purchase data, and creates items in a [Homebox](https://homebox.software) inventory instance.

## Running the app

```bash
source venv/bin/activate

# One-shot live processing: reads/moves mailbox messages and writes to Homebox
python run_once.py --live

# Daemon live processing: poll every CHECK_INTERVAL seconds
python src/app.py --live
```

### Docker (primary deployment)

```bash
# Requires Ollama running natively on the host Mac
docker compose up --build -d
docker compose logs -f
```

Compose explicitly opts into live processing. The Dockerfile default is intentionally safe and omits `--live`, so `docker run IMAGE` exits without reading IMAP or writing Homebox. For an explicitly approved standalone live run, override it with `docker run --env-file .env IMAGE python src/app.py --live`. The container reaches the host's Ollama via `host.docker.internal:11434`. The `data/` directory is bind-mounted for log/receipt persistence; `config/` is mounted read-only.

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

Homebox v0.26.2 removed the separate item and location routes in favor of entities:

- `POST /api/v1/entities` creates an item with `parentId`, description, quantity, `tagIds`, and supported identifiers. Omitting `entityTypeId` selects the group's default Item type.
- `PUT /api/v1/entities/{id}` applies purchase details using the complete entity update contract.
- `GET /api/v1/entities?isLocation=true` looks up locations; attachments use `/api/v1/entities/{id}/attachments`.
- Legacy client payload fields `locationId`, `labelIds`, and `purchaseTime` translate to `parentId`, `tagIds`, and `purchaseDate`.

See the [official entity-merge migration guide](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/docs/src/content/docs/en/advanced/entity-merge-upgrade.mdx).

### Confidence scoring

The LLM returns a self-assessed `confidence` field. `app.py` also cross-checks the sum of item prices against the receipt total and penalises confidence when the gap exceeds 20% (to allow for tax/shipping). Items below `MIN_CONFIDENCE` (default 0.7) are moved to the Manual Review folder rather than added to Homebox.

### IMAP folder separators

Most providers (Gmail, Fastmail, Outlook, iCloud) use `/` as the subfolder separator: `"Receipts/Homebox"`. Some use `.`. See `IMAP_PROVIDERS.md` for provider-specific notes. The code always re-SELECTs the source folder before COPY/DELETE because IMAP requires SELECTED state.

## Configuration

All secrets go in `.env` (see `env.sample`). Behaviour is tuned in `config/config.yml` — prompts, category maps, OCR thresholds, image-search limits, consumable/non-physical filtering rules, and Homebox location defaults. The config path can be overridden with `CONFIG_FILE` env var.

Processed receipts are saved as YAML in `data/processed/`; failures land in `data/failed/` for manual review. Main log: `data/logs/processor.log`.
