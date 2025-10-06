# Email to Homebox - Automated Receipt Processor

Automatically extract purchase data from email receipts using local AI (MLX on Apple Silicon) and add items to your Homebox inventory system.

## Features

- 🤖 **Local AI processing** using MLX-LM (Qwen2.5-7B-Instruct-4bit, optimized for Apple Silicon)
- 📧 **Gmail integration** via IMAP - monitors specific folder for receipts
- 🏠 **Homebox API integration** - automatically creates inventory items with purchase info
- 🔒 **Privacy-focused** - all AI processing happens locally on your Mac
- ⚡️ **Fast** - leverages Apple's Metal GPU for quick inference (~2-3 sec per receipt)
- 📊 **Smart validation** - cross-checks item prices vs receipt total, adjusts confidence
- 🎯 **Confidence scoring** - only processes high-confidence extractions (≥0.7)
- 📝 **Comprehensive logging** - failed receipts saved for manual review

## What It Extracts

From receipt emails, the system extracts:
- **Items**: name, price, quantity, category, description
- **Product details**: manufacturer, model number, serial number (when available)
- **Purchase info**: store, date, order ID, total amount
- **Metadata**: confidence score, validation results

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.10 or later
- 8GB+ RAM recommended (model uses ~5GB)
- Gmail account with app password
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
# Email settings
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993

# Homebox settings
HOMEBOX_URL=https://your-homebox-url/
HOMEBOX_USERNAME=your-homebox-username
HOMEBOX_PASSWORD=your-homebox-password

# MLX Model (default is good)
AI_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit
AI_MAX_TOKENS=4096
```

**Getting Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Create a new app password
3. Use that password in `.env` (not your regular Gmail password)

**Homebox Setup:**
1. Create a location called "Unassigned" in Homebox

**Gmail Setup:**
1. Create a Gmail label/folder called "Receipts"
2. Create subfolders: "Receipts/Receipts (in Homebox)" and "Receipts/Receipts (process manually)"
3. Move some receipt emails to the "Receipts" folder

### 3. Test

Test email fetching and extraction:

```bash
python test_email.py
```

This will:
- Download the AI model (~4-5GB, first run only, takes 5-10 min)
- Fetch a receipt from your "Receipts" folder
- Extract and display the JSON data
- Show confidence analysis

Test Homebox connection:

```bash
python test_homebox.py
```

### 4. Run

Process all receipts in your "Receipts" folder:

```bash
python run_once.py
```

This will:
- Fetch all emails from "Receipts" folder
- Extract item data using local AI
- Validate confidence scores (price cross-checking)
- Add high-confidence items (≥0.7) to Homebox
- Show summary of results

## Project Structure

```
email-to-homebox/
├── run_once.py           # One-time batch processor (recommended)
├── test_email.py         # Test email + extraction
├── test_homebox.py       # Test Homebox API
├── setup.sh              # Setup script
├── requirements.txt      # Python dependencies
├── .env                  # Your configuration (not in git)
├── env.sample            # Example environment file
├── config/
│   └── config.yml       # App configuration & prompts
├── src/
│   ├── app.py           # Main application logic
│   ├── email_fetcher.py # Email IMAP handling
│   ├── receipt_extractor_mlx.py  # MLX AI extraction
│   └── homebox_client.py         # Homebox API client
└── data/
    ├── logs/            # Application logs
    ├── failed/          # Failed receipts for review
    └── processed/       # Successfully processed receipts
```

## Configuration

### Email Settings (`config/config.yml`)

Configure email folders (currently set to "Receipts" folder only):

```yaml
email:
  folders:
    - Receipts  # Gmail label/folder to monitor

  # Email moving (optional, currently disabled in run_once.py)
  move_to_folder_on_success: "Receipts/Receipts (in Homebox)"
  move_to_folder_on_low_confidence: "Receipts/Receipts (process manually)"
```

**Note:** Subject patterns and sender domains are in the config but currently ALL emails in the configured folder are processed (no filtering).

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

Current default (recommended for 8GB+ RAM):

```bash
AI_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit  # ~5GB
AI_MAX_TOKENS=4096  # Needed for long product names
```

### Processing Settings

```bash
MIN_CONFIDENCE=0.7      # Only auto-add items with 70%+ confidence
CHECK_INTERVAL=300      # For daemon mode (not currently used)
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
```

## How It Works

1. **Email Fetching**: Connects to Gmail via IMAP and fetches all emails from "Receipts" folder
2. **AI Extraction**: Sends receipt text to local MLX model (Qwen2.5-7B) for structured JSON extraction
3. **Validation**:
   - AI provides initial confidence score (0.0-1.0)
   - System cross-checks item prices vs receipt total
   - Reduces confidence if price mismatch >20%
4. **Homebox Integration**:
   - Gets "Unassigned" location ID from Homebox
   - Creates item with basic fields (name, description, quantity, location)
   - Immediately updates item with purchase details (price, date, manufacturer, etc.)
5. **Results**:
   - High confidence (≥0.7): Items added to Homebox
   - Low confidence (<0.7): Saved to `data/failed/` for manual review
   - All processed receipts logged to `data/processed/`

## Usage Modes

### Current: One-Time Batch Processing (Recommended)

```bash
python run_once.py
```

Processes all emails in "Receipts" folder once and exits. Successfully processed receipts are moved to subfolder for organization.

### Future: Daemon Mode

```bash
python src/app.py
```

Runs continuously, checking email every 5 minutes. Will auto-move emails to success/manual folders. (Currently implemented but not actively used)

## Troubleshooting

### Email Connection Issues

**Problem:** "Failed to connect to email"
- For Gmail: Use an **App Password**, not your regular password
- Check IMAP is enabled in Gmail settings
- Verify `.env` has correct IMAP host/port

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

### Model Download

**Problem:** MLX model won't download
```bash
# Manually download
python -c "from mlx_lm import load; load('mlx-community/Qwen2.5-7B-Instruct-4bit')"
```

**Problem:** Out of memory
- Need 8GB+ RAM for 7B model
- Model uses ~5GB, system needs headroom

## Running Automatically

### Option 1: Manual Runs (Current)

Run `python run_once.py` whenever you want to process new receipts. Simple and reliable.

### Option 2: Scheduled Runs (Cron)

Add to crontab to run every hour:

```bash
0 * * * * cd /path/to/email-to-homebox && /path/to/email-to-homebox/venv/bin/python run_once.py >> data/logs/cron.log 2>&1
```

### Option 3: Daemon Mode (Future)

Use `src/app.py` for continuous monitoring. Not currently recommended until email moving is fully tested.

## Important Notes

### Homebox API Quirks

The Homebox API (sysadminsmedia/homebox) has a **two-step item creation** process:
1. POST creates item with basic fields only (name, location, description, quantity)
2. PUT updates item with extended fields (price, manufacturer, model, etc.)

This is handled automatically by `homebox_client.py`.

### Email Moving

Successfully processed receipts are automatically moved to organized subfolders:
- **High confidence (≥0.7)**: Moved to `Receipts/Receipts (in Homebox)`
- **Low confidence (<0.7)**: Moved to `Receipts/Receipts (process manually)`
- **Failed extraction**: Stays in original `Receipts` folder

**Important:** Create these Gmail labels/subfolders before running:
1. `Receipts/Receipts (in Homebox)`
2. `Receipts/Receipts (process manually)`

Gmail nested labels use "/" separator in the config.

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
python run_once.py        # Process receipts
```

## Privacy & Security

- ✅ All AI processing happens **locally** on your Mac
- ✅ Receipts never sent to cloud AI services
- ✅ Email credentials stored in `.env` (gitignored)
- ✅ Failed receipts saved locally for review
- ⚠️ Store `.env` securely (contains passwords)

## Contributing

This is a personal project but PRs welcome! Areas for improvement:
- Support for more email providers
- PDF/image receipt support
- Duplicate detection
- Better manufacturer/model extraction
- Alternative AI models

## License

MIT - Use however you want!

## Credits

Built with:
- [MLX-LM](https://github.com/ml-explore/mlx-lm) - Apple Silicon optimized LLM inference
- [Homebox](https://github.com/sysadminsmedia/homebox) - Home inventory management
- [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) - Base model