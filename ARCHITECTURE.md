# Architecture & Technical Documentation

## Overview

This system automatically processes receipt emails, extracts purchase data using local AI (MLX on Apple Silicon), and adds items to Homebox inventory management system.

## Current State (2025-10-05)

### What's Working
- ✅ Email fetching from Gmail IMAP (specific folder: "Receipts")
- ✅ MLX-based AI extraction using Qwen2.5-7B-Instruct-4bit model
- ✅ Homebox API integration with two-step item creation
- ✅ Confidence-based validation with price cross-checking
- ✅ Automatic location assignment ("Unassigned" location)
- ✅ Automatic email organization (moves to success/manual subfolders)
- ✅ One-time batch processing script (`run_once.py`)
- ✅ Test scripts for debugging

### Known Issues
- Main daemon app (`src/app.py`) exists but `run_once.py` is recommended for manual runs

## Architecture

### Components

#### 1. Email Fetcher (`src/email_fetcher.py`)
- Connects to Gmail via IMAP
- Fetches emails from configured folders
- Can filter by read/unread status
- Supports moving emails between folders

**Key Methods:**
- `fetch_receipts(unread_only=True)` - Get receipt emails
- `move_to_folder(uid, destination_folder, source_folder='Receipts')` - Move emails

#### 2. Receipt Extractor (`src/receipt_extractor_mlx.py`)
- Uses MLX-LM for Apple Silicon GPU acceleration
- Model: Qwen2.5-7B-Instruct-4bit (~4-5GB)
- Extracts structured JSON from receipt text
- Validates and adjusts confidence scores

**Extraction Flow:**
1. Loads MLX model on initialization
2. Formats email content with system/user prompts
3. Generates JSON response (max 4096 tokens)
4. Parses and validates JSON
5. Cross-checks item prices vs receipt total
6. Adjusts confidence if price mismatch >20%

**Extracted Fields:**
- Items: name, price, quantity, category, description, manufacturer, model_number, serial_number
- Receipt: store, order_date, total, order_id, confidence

#### 3. Homebox Client (`src/homebox_client.py`)
- Handles authentication via username/password login
- Token-based Bearer auth with auto-refresh on 401
- Two-step item creation (Homebox API limitation)

**Two-Step Item Creation:**
1. **POST /api/v1/items** - Create with: name, locationId, description, quantity
2. **PUT /api/v1/items/{id}** - Update with: purchasePrice, purchaseFrom, purchaseTime, manufacturer, modelNumber, serialNumber

**Key Methods:**
- `_login()` - Get bearer token
- `get_location_id_by_name(name)` - Find location by name
- `create_item(item_data)` - Two-step create + update

#### 4. Main App (`src/app.py`)
- Orchestrates the full workflow
- Processes receipts with confidence thresholds
- Maps extracted data to Homebox format
- Saves failed receipts for review

**Processing Flow:**
1. Extract receipt data with MLX
2. Check confidence (min 0.7)
3. Get "Unassigned" location ID
4. Map items to Homebox format
5. Create items (two-step process)
6. Move email based on result

### Configuration

#### Environment Variables (`.env`)
```bash
# Email
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=app-password
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993

# Homebox
HOMEBOX_URL=https://your-homebox-url/
HOMEBOX_USERNAME=username
HOMEBOX_PASSWORD=password

# MLX Model
AI_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit
AI_MAX_TOKENS=4096

# Processing
CHECK_INTERVAL=300
MIN_CONFIDENCE=0.7
```

#### Config File (`config/config.yml`)
- Email folder settings
- AI prompts for extraction
- Homebox location mapping
- Category mappings
- Confidence thresholds

### Data Flow

```
Email (IMAP) → Email Fetcher → Receipt Extractor (MLX) → Validation
                                                             ↓
                                              Homebox Client ← App Logic
                                                             ↓
                                              Homebox API (two-step create)
```

### Confidence Validation

The system validates extraction confidence in two ways:

1. **Model Confidence** - AI's self-assessed confidence (0.0-1.0)
2. **Price Validation** - Compares sum of item prices vs receipt total
   - Allows 20% difference (for tax/shipping)
   - Reduces confidence if mismatch >20%
   - Logs warning with price details

**Confidence Thresholds:**
- ≥0.7: Auto-process and add to Homebox
- <0.7: Flag for manual review

### Scripts

- **`run_once.py`** - Process all emails in Receipts folder once (recommended)
- **`src/app.py`** - Daemon mode, checks every 5 minutes (not actively used)
- **`test_email.py`** - Test email fetching + extraction (shows JSON)
- **`test_homebox.py`** - Test Homebox API connection
- **`test_extraction.py`** - Test MLX extraction only

### Directory Structure

```
email-to-homebox/
├── src/
│   ├── app.py              # Main application
│   ├── email_fetcher.py    # IMAP email handling
│   ├── receipt_extractor_mlx.py  # MLX AI extraction
│   └── homebox_client.py   # Homebox API client
├── config/
│   └── config.yml          # Application configuration
├── data/
│   ├── logs/               # Application logs
│   ├── failed/             # Failed receipts for review
│   └── processed/          # Successfully processed receipts
├── run_once.py             # One-time batch processor
├── test_*.py               # Test scripts
├── .env                    # Environment variables (not in git)
└── env.sample              # Example environment file
```

## Homebox API Notes

### Authentication
- POST `/api/v1/users/login` with form data (username/password)
- Returns token with "Bearer " prefix already included
- Token expires, auto-refresh on 401

### Item Creation (Important!)
Homebox API has limited fields on create endpoint:

**Create (POST /api/v1/items):**
- name (required)
- locationId (required)
- description, quantity, labelIds, parentId (optional)

**Update (PUT /api/v1/items/{id}):**
- name, locationId (required even if not changing)
- purchasePrice, purchaseFrom, purchaseTime
- manufacturer, modelNumber, serialNumber
- All other extended fields

**Current Implementation:** Create with basic fields, immediately update with purchase info.

## Development Notes

### MLX Model Performance
- First run downloads ~4-5GB model
- Inference on M1/M2/M3 is fast (~2-3 sec per receipt)
- Max tokens set to 4096 to handle long Amazon product names
- Temperature not used (deterministic output preferred)

### Email Folder Structure
- Gmail nested labels use "/" separator: `"Receipts/Receipts (in Homebox)"`
- Must select source folder before moving emails
- IMAP requires SELECTED state for COPY/DELETE operations

### Future Improvements
- [ ] Add retry logic for transient failures
- [ ] Support for more email providers
- [ ] Custom field mappings per store
- [ ] Image/PDF receipt support
- [ ] Duplicate detection
- [ ] Batch mode optimizations

## Quick Start for Future Sessions

1. Activate venv: `source venv/bin/activate`
2. Check dependencies: `pip list`
3. Test email: `python test_email.py`
4. Test Homebox: `python test_homebox.py`
5. Run processor: `python run_once.py`

## Debugging

Enable debug logging in any script:
```python
logging.basicConfig(level=logging.DEBUG)
```

Check logs:
- `data/logs/processor.log` - Main app logs
- `data/failed/` - Failed receipt extractions
- `data/processed/` - Successfully processed receipts
