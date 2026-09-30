# Email to Homebox - Automated Receipt Processor

Extract purchase data from email receipts with Ollama and add items to Homebox. The checked-in extractor calls Ollama's HTTP API; `receipt_extractor_mlx.py` is a legacy filename, not an MLX implementation.

## Features

- 🤖 **Ollama extraction** using the configured Ollama host and model
- 📧 **Email integration** via IMAP - works with Gmail, Outlook, iCloud, Fastmail, and any IMAP provider
- 🏠 **Homebox API integration** - automatically creates inventory items with purchase info
- 📸 **OCR for physical receipts** - extract text from receipt photos using EasyOCR
  - Take a photo of a physical receipt with your phone
  - Email it to yourself as an attachment
  - System automatically extracts text using OCR
  - Uses an available backend supported by EasyOCR
- 🖼️ **Product image extraction** - finds and uploads product photos from emails
  - Extracts images from email attachments
  - Downloads linked images from HTML emails
  - DuckDuckGo search fallback when no email images
  - Smart filtering (size, URL patterns, dimensions)
- 🔒 **Privacy-focused** - use a local Ollama server to keep receipt text on your network
- 📊 **Smart validation** - cross-checks item prices vs receipt total, adjusts confidence
- 🎯 **Confidence scoring** - only processes high-confidence extractions (≥0.7)
- 🍎 **Consumable filtering** - automatically skip receipts for food/supplies, organize separately
- 📝 **Comprehensive logging** - failed receipts saved for manual review

## What It Extracts

From receipt emails, the system extracts:
- **Items**: name, price, quantity, category, description
- **Product details**: manufacturer, model number, serial number (when available)
- **Purchase info**: store, date, order ID, total amount
- **Product images**: from attachments, HTML links, or DuckDuckGo search
- **Metadata**: confidence score, validation results

## Requirements

- Python 3.10 or later
- An Ollama server with the configured model available
- Email account with IMAP access (Gmail, Outlook, iCloud, Fastmail, etc.)
- Homebox instance (tested with sysadminsmedia/homebox)

## Quick Start

### 1. Clone & Setup

```bash
git clone <your-repo-url>
cd email-to-homebox

# Run setup script
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate
```

### 2. Configure

Copy and edit environment file:

```bash
cp env.sample .env
nano .env
```

Fill in your settings:

```bash
# Email settings (example shown for Gmail)
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993

# Homebox settings
HOMEBOX_URL=https://your-homebox-url/
HOMEBOX_API_KEY=your-dedicated-service-account-key
# Legacy username/password login is used only when HOMEBOX_API_KEY is unset.
# HOMEBOX_USERNAME=your-homebox-username
# HOMEBOX_PASSWORD=your-homebox-password

# Ollama (defaults shown; set OLLAMA_HOST for your Ollama server)
OLLAMA_HOST=http://localhost:11434
AI_MODEL=qwen2.5:7b
AI_MAX_TOKENS=2048
```

**Email Setup:**
1. Find your IMAP settings (see [IMAP_PROVIDERS.md](IMAP_PROVIDERS.md) for Gmail, Outlook, iCloud, etc.)
2. Create an app password if required by your provider
3. Update `.env` with your provider's IMAP host, port, and credentials

**Common providers:**
- **Gmail:** `imap.gmail.com:993` (app password required)
- **Outlook:** `outlook.office365.com:993`
- **iCloud:** `imap.mail.me.com:993` (app password required)
- **Fastmail:** `imap.fastmail.com:993`

See [IMAP_PROVIDERS.md](IMAP_PROVIDERS.md) for detailed setup instructions for each provider.

**Homebox Setup:**
1. Create a location called "Unassigned" in Homebox

**Email Folder Setup:**
1. Create a folder/label called "Receipts" in your email
2. Create subfolders: "Receipts/Receipts (in Homebox)", "Receipts/Receipts (process manually)", and "Receipts/Consumables"
3. Move some receipt emails to the "Receipts" folder

### 3. Safe synthetic test

Run the isolated pipeline test first; it uses a synthetic receipt, a fake extractor, and a fake Homebox client. It makes no network calls:

```bash
python -m unittest tests.test_safe_pipeline tests.test_model_evaluation -v
```

To evaluate an installed Ollama model on the synthetic example, run the dry-run preview. It contacts only the explicitly supplied Ollama URL for model discovery and inference; it never reads IMAP credentials or calls Homebox:

```bash
python run_dry_run.py \
  --input tests/fixtures/synthetic_receipt.json \
  --ollama-url http://localhost:11434 \
  --model qwen2.5:14b
```

Compare selected installed Ollama model tags serially against the same synthetic receipt, including field-level correctness and inference timings:

```bash
python run_model_evaluation.py \
  --ollama-url http://localhost:11434 \
  --models qwen2.5:14b qwen3:14b phi4:14b gemma4:12b

# Explicit CPU-only requests; omit --num-gpu to use Ollama's normal placement.
python run_model_evaluation.py \
  --ollama-url http://localhost:11434 \
  --num-gpu 0 \
  --models qwen2.5:14b qwen3:14b
```

The evaluator uses no mailbox or Homebox, makes requests serially, and does not override Ollama's normal model keep-alive behavior. It does not run automatically. A default-placement request may use the host GPU, but does not guarantee that the shared Tesla P100 is selected. Ollama's current API/source supports `options.num_gpu: 0` for CPU-only execution; confirm the installed Ollama version supports it before running. Review the reported extraction correctness, `client_wall_seconds`, and Ollama load/prompt/generation metrics (server durations are nanoseconds; client wall time is seconds). See [TESTING.md](TESTING.md) for metric details and safety notes.

The preview prints extracted receipt data and mapped Homebox payloads to stdout. The default location ID is a placeholder and is not checked against Homebox. Use only synthetic or sanitized input.

### Deployment contract

The Compose service explicitly runs the live daemon. Before starting it, configure `.env` with `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `HOMEBOX_URL`, `HOMEBOX_API_KEY`, and a container-reachable `OLLAMA_HOST`; `AI_MODEL` must name an already-installed Ollama model. Homebox API keys inherit the owning user's full access and have no per-key endpoint scope, so use a dedicated service account. Never mint keys from the app or place credentials in the image/source/plaintext manifests.

For a future cluster deployment, inject `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, and `HOMEBOX_API_KEY` from an ESO-managed Secret; keep `HOMEBOX_URL`, `OLLAMA_HOST`, `AI_MODEL`, and processing settings as non-secret configuration. Leave any scheduled one-shot job suspended until an image has been published, endpoint egress reviewed, and a human approves a test; its command is `python run_once.py --live`. `OLLAMA_HOST` must be routable and allowed from within the pod; `localhost` is not the host Ollama service. Container image publication, registry/fork setup, and infrastructure deployment are not performed by this repository task.

### 4. Live integrations (not part of the safe test)

The commands below access external services and may read or modify real mailbox/Homebox state. Do not use them for the synthetic first-stage evaluation.

Test email fetching and extraction:

```bash
python test_email.py
```

This will:
- Connect to the configured Ollama server and request extraction from its configured model
- Fetch a receipt from your "Receipts" folder
- Extract and display the JSON data
- Show confidence analysis

Test image extraction:

```bash
python test_images.py
```

This will:
- Fetch a receipt from your "Receipts" folder
- Extract images (attachments + HTML links)
- Show image dimensions and sources
- Save first image to `data/test_images/` for verification

Test Homebox connection:

```bash
python test_homebox.py
```

### 5. Run

Process all receipts in your "Receipts" folder (live IMAP reads, mailbox moves, and Homebox writes):

```bash
python run_once.py --live
```

This will:
- Fetch all emails from "Receipts" folder
- Extract item data using local AI
- Validate confidence scores (price cross-checking)
- Add high-confidence items (≥0.7) to Homebox
- Show summary of results

### 6. Backfill Images (Optional)

Add images to existing items in Homebox:

```bash
python backfill_images.py --max-items 5
```

This is useful for:
- **Testing image search** - Process just 1-2 items to test DuckDuckGo
- **Adding images to existing items** - Don't need to process receipts
- **Avoiding rate limits** - Control exactly how many items to process

**Quick examples:**
```bash
# Test with 1 item
python backfill_images.py --max-items 1

# Preview what would be done (dry run)
python backfill_images.py --max-items 10 --dry-run

# Process items in specific location
python backfill_images.py --location "Unassigned"
```

See [BACKFILL_GUIDE.md](BACKFILL_GUIDE.md) for detailed usage.

## Project Structure

```
email-to-homebox/
├── run_once.py           # One-time batch processor (recommended)
├── backfill_images.py    # Add images to existing Homebox items
├── test_email.py         # Test email + extraction
├── test_images.py        # Test image extraction
├── test_homebox.py       # Test Homebox API
├── setup.sh              # Setup script
├── requirements.txt      # Python dependencies
├── .env                  # Your configuration (not in git)
├── env.sample            # Example environment file
├── BACKFILL_GUIDE.md     # Backfill usage guide
├── config/
│   └── config.yml       # App configuration & prompts
├── src/
│   ├── app.py           # Main application logic
│   ├── email_fetcher.py # Email IMAP handling + image extraction
│   ├── receipt_extractor_mlx.py  # Ollama HTTP extraction (legacy filename)
│   ├── homebox_client.py         # Homebox API client + attachment upload
│   └── image_handler.py          # DuckDuckGo image search
└── data/
    ├── logs/            # Application logs
    ├── failed/          # Failed receipts for review
    ├── processed/       # Successfully processed receipts
    └── test_images/     # Test images (created by test_images.py)
```

## Configuration

### Email Settings (`config/config.yml`)

Configure email folders (currently set to "Receipts" folder only):

```yaml
email:
  folders:
    - Receipts  # Email folder/label to monitor

  # Email moving (optional, currently disabled in run_once.py)
  move_to_folder_on_success: "Receipts/Receipts (in Homebox)"
  move_to_folder_on_low_confidence: "Receipts/Receipts (process manually)"
  move_to_folder_on_consumable: "Receipts/Consumables"
```

**Note:** Subject patterns and sender domains are in the config but currently ALL emails in the configured folder are processed (no filtering).

**Folder naming:** Most providers use "/" for nested folders. See [IMAP_PROVIDERS.md](IMAP_PROVIDERS.md) if you have issues.

### Homebox Settings (`config/config.yml`)

```yaml
homebox:
  default_location: "Unassigned"  # Must exist in Homebox

  # Category mapping (AI category → Homebox label)
  category_map:
    electronics: "Electronics"
    clothing: "Clothing"
    # ... etc
```

### AI Model (`.env`)

Current checked-in implementation uses the Ollama API:

```bash
OLLAMA_HOST=http://localhost:11434
AI_MODEL=qwen2.5:7b
AI_MAX_TOKENS=2048
```

The project uses Ollama because that is the existing configured inference path. This is not a claim that MLX is unavailable on x86/Linux: current MLX documentation includes Linux CPU and CUDA backends. Compatibility and performance of MLX on a Tesla P100 have not been evaluated here.

### Processing Settings

In `config/config.yml`:

```yaml
processing:
  min_confidence: 0.7          # Only auto-add items with 70%+ confidence
  enable_image_search: true    # Use DuckDuckGo fallback when no email images
  save_processed: true         # Save processed receipts to data/processed/
  save_failed: true            # Save failed receipts to data/failed/

  # Consumable filtering - skip receipts that only contain food/supplies
  skip_consumables: true       # Enable consumable filtering
  consumable_categories:       # Categories to consider consumable
    - food                     # Food, groceries, snacks
    # - health                 # Uncomment to also skip medicine, toiletries, vitamins
  # Note: Receipts are skipped only if ALL items are consumable
  # Mixed receipts (e.g., TV + snacks) will still be processed
```

In `.env`:

```bash
CHECK_INTERVAL=300      # For daemon mode (not currently used)
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
```

## How It Works

1. **Email Fetching**: Connects to your email via IMAP and fetches all emails from "Receipts" folder
2. **Image Extraction**:
   - Extracts image attachments from emails
   - Parses HTML for `<img>` tags and downloads linked images
   - Filters by size (100x100 to 2000x2000), file size (>10KB), URL patterns
   - Matches images to extracted items
3. **AI Extraction**: Sends receipt text to the configured Ollama model for structured JSON extraction
4. **Validation**:
   - AI provides initial confidence score (0.0-1.0)
   - System cross-checks item prices vs receipt total
   - Reduces confidence if price mismatch >20%
5. **Consumable Filtering**:
   - Checks if all items are consumable (food, cleaning supplies, etc.)
   - Skips adding to Homebox if all items are consumable
   - Mixed receipts (e.g., TV + snacks) still get processed
   - Consumable receipts moved to separate folder for organization
6. **Homebox Integration**:
   - Gets "Unassigned" location ID from Homebox
   - Creates item with basic fields (name, description, quantity, location)
   - Immediately updates item with purchase details (price, date, manufacturer, etc.)
   - Uploads product images (from email or DuckDuckGo search)
7. **Results**:
   - High confidence (≥0.7): Items added to Homebox with images
   - Low confidence (<0.7): Saved to `data/failed/` for manual review
   - Consumable receipts: Skipped and moved to `Receipts/Consumables`
   - All processed receipts logged to `data/processed/`

## Usage Modes

### Current: One-Time Batch Processing (Live)

```bash
python run_once.py --live
```

Processes all emails in "Receipts" folder once and exits. Successfully processed receipts are moved to subfolder for organization.

### Processing Physical Receipts

To process physical receipts (paper receipts from stores):

1. **Take a photo** of the receipt with your phone (make sure text is clear and readable)
2. **Email the photo to yourself** as an attachment
3. **Move the email** to your "Receipts" folder
4. **Run the processor**: `python run_once.py`

The system will automatically:
- Detect that the email has minimal text and an image attachment
- Run OCR (Optical Character Recognition) to extract text from the receipt photo
- Process the OCR'd text just like a regular email receipt
- Extract items and add them to Homebox

**Tips for best OCR results:**
- Take photos in good lighting
- Keep the receipt flat and in focus
- Make sure all text is visible and not cut off
- Higher resolution photos work better

**Note:** EasyOCR may download its model weights on first use. The safe synthetic tests do not initialize OCR.

### Future: Daemon Mode

```bash
python src/app.py --live
```

Runs continuously, checking email every 5 minutes. Will auto-move emails to success/manual folders. (Currently implemented but not actively used)

## Troubleshooting

### Email Connection Issues

**Problem:** "Failed to connect to email"
- Use an **App Password** if required by your provider (Gmail, iCloud, Yahoo require this)
- Check IMAP is enabled in your email settings
- Verify `.env` has correct IMAP host/port for your provider
- See [IMAP_PROVIDERS.md](IMAP_PROVIDERS.md) for provider-specific troubleshooting

### Homebox Authentication

**Problem:** "401 Unauthorized" or "Failed to login"
- Verify Homebox username/password in `.env`
- Check Homebox URL is accessible (https://...)
- Token already includes "Bearer" prefix (handled automatically)

**Problem:** "Location 'Unassigned' not found"
- Create a location called "Unassigned" in Homebox
- Or change `default_location` in `config/config.yml`

### Extraction Issues

**Problem:** "Low confidence" or prices missing
- Check `data/failed/` to see raw email content
- Long product names may need `AI_MAX_TOKENS=4096` or higher
- Adjust confidence threshold in `config/config.yml` (currently 0.7)

**Problem:** Items created but no purchase price
- System uses two-step process (create, then update)
- Check debug logs: `python run_once.py` shows update requests
- Price format: float, not string

### Ollama Connection

**Problem:** Cannot reach Ollama or model is missing
- Verify `OLLAMA_HOST` is reachable from the app/container
- Verify the configured `AI_MODEL` tag exists on that Ollama server
- For Docker, the compose file currently targets the host at `host.docker.internal:11434`

### OCR Issues

**Problem:** OCR not extracting text from physical receipt photos
- Make sure photo is clear, in focus, and well-lit
- Check that `enable_ocr: true` in `config/config.yml`
- Try with a higher resolution photo
- Check logs to see if OCR is running

**Problem:** EasyOCR initialization fails
```bash
# Manually test EasyOCR
python -c "import easyocr; reader = easyocr.Reader(['en'], gpu=False)"
```

**Problem:** OCR is slow
- First run downloads OCR models (~100MB)
- Subsequent runs should be fast with GPU acceleration
- Check that `gpu=True` is working (logs will show initialization)

## Running Automatically

### Option 1: Manual Runs (Current)

Run `python run_once.py --live` whenever you want to process new receipts. This reads/moves real mailbox messages and may write to Homebox.

### Option 2: Scheduled Runs (Cron)

Add to crontab to run every hour:

```bash
0 * * * * cd /path/to/email-to-homebox && /path/to/email-to-homebox/venv/bin/python run_once.py --live >> data/logs/cron.log 2>&1
```

### Option 3: Daemon Mode (Future)

Use `src/app.py --live` for continuous monitoring. Not currently recommended until email moving is fully tested.

## Important Notes

### Homebox API Quirks

The Homebox API (sysadminsmedia/homebox) has a **two-step item creation** process:
1. `POST /api/v1/entities` creates an item entity with basic fields (`name`, `parentId`, `description`, `quantity`, tags and supported identifiers).
2. When purchase-specific fields are present, `PUT /api/v1/entities/{id}` updates the entity using the full entity response as a preservation baseline. Legacy `locationId` and `purchaseTime` input values are translated to `parentId` and `purchaseDate`.

Homebox v0.26.2 removed `/api/v1/items` and `/api/v1/locations`; locations are entities queried with `isLocation=true`. Attachments use `/api/v1/entities/{id}/attachments`, and the former labels workflow now uses tags. See the [official entity-merge API migration guide](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/docs/src/content/docs/en/advanced/entity-merge-upgrade.mdx).

This is handled automatically by `homebox_client.py`.

### Email Moving

Successfully processed receipts are automatically moved to organized subfolders:
- **High confidence (≥0.7)**: Moved to `Receipts/Receipts (in Homebox)`
- **Low confidence (<0.7)**: Moved to `Receipts/Receipts (process manually)`
- **Partial Homebox write** (entity exists, purchase update failed): stopped and moved to `Receipts/Receipts (process manually)`; reconcile the returned entity ID before retrying
- **Consumable items only**: Moved to `Receipts/Consumables` (not added to Homebox)
- **Failed extraction**: Stays in original `Receipts` folder

**Important:** Create these subfolders before running:
1. `Receipts/Receipts (in Homebox)`
2. `Receipts/Receipts (process manually)`
3. `Receipts/Consumables`

**Note:** Most email providers (Gmail, Outlook, iCloud, Fastmail) use "/" for nested folders. If email moving fails, check [IMAP_PROVIDERS.md](IMAP_PROVIDERS.md) for your provider's folder naming convention.

## Development

See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details, data flow, and implementation notes.

### Key Files
- `src/receipt_extractor_mlx.py` - AI extraction logic, confidence validation
- `src/homebox_client.py` - Two-step API creation process
- `config/config.yml` - AI prompts, field mappings

### Testing
```bash
python test_email.py      # Test email + extraction
python test_homebox.py    # Test Homebox API
python run_once.py --live # Process receipts (live mailbox/Homebox access)
```

## Privacy & Security

- ✅ All AI processing happens **locally** on your Mac
- ✅ Receipts never sent to cloud AI services
- ✅ Email credentials stored in `.env` (gitignored)
- ✅ Failed receipts saved locally for review
- ⚠️ Store `.env` securely (contains passwords)

## Roadmap

### Recently Completed ✅
- 📸 **Image extraction & upload** (2025-10-08)
  - Extracts images from email attachments
  - Downloads images from HTML `<img>` tags
  - DuckDuckGo search fallback when no email images
  - Smart filtering by size, URL patterns, dimensions
  - Automatic upload to Homebox items
- 🍎 **Consumable filtering** (2025-10-09)
  - Automatically skip receipts with only consumable items (food, cleaning supplies)
  - Configurable categories (food, health, etc.)
  - Only skips if ALL items are consumable - mixed receipts still processed
  - Moves consumable receipts to separate folder for organization
- 📸 **OCR for physical receipts** (2025-10-13)
  - Extract text from receipt photos using EasyOCR
  - Uses an available backend supported by EasyOCR
  - Automatically processes physical receipt photos emailed to yourself
  - Smart detection: runs OCR when email body is minimal

### Planned Features
- 📄 **Email PDF attachment** - Save original receipt email as PDF attachment
- 📚 **Product manual finder** - Auto-find and attach product manuals
- 📧 **Multi-provider support** - IMAP support for Outlook, Fastmail, etc.

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed implementation notes.

## Contributing

This is a personal project build almost entirely with Claude. Feel free to fork and continue working on it yourself, but I probably won't be taking PRs.

## License

MIT - Use however you want!

## Credits

Built with:
- [Ollama](https://ollama.com/) - local model serving used by the checked-in extractor
- [Homebox](https://github.com/sysadminsmedia/homebox) - Home inventory management
- [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) - Base model
- [DDGS](https://github.com/deedy5/ddgs) - DuckDuckGo search (for image fallback)