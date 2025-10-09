# Architecture & Technical Documentation

## Overview

This system automatically processes receipt emails, extracts purchase data using local AI (MLX on Apple Silicon), and adds items to Homebox inventory management system.

## Current State (2025-10-08)

### What's Working
- ✅ Email fetching from Gmail IMAP (specific folder: "Receipts")
- ✅ MLX-based AI extraction using Qwen2.5-7B-Instruct-4bit model
- ✅ Homebox API integration with two-step item creation
- ✅ Confidence-based validation with price cross-checking
- ✅ Automatic location assignment ("Unassigned" location)
- ✅ Automatic email organization (moves to success/manual subfolders)
- ✅ One-time batch processing script (`run_once.py`)
- ✅ Test scripts for debugging
- ✅ **NEW:** Product image extraction from emails (attachments + linked images)
- ✅ **NEW:** DuckDuckGo image search fallback
- ✅ **NEW:** Automatic image upload to Homebox items

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

#### 4. Image Handler (`src/image_handler.py`)
- Searches for product images using DuckDuckGo
- Filters and validates images
- Matches images to receipt items

**Key Methods:**
- `search_product_image(product_name, manufacturer)` - Search DuckDuckGo for product images
- `get_best_image(images)` - Select best image from list
- `match_images_to_items(images, items)` - Match images to items

**Image Filtering:**
- Size: 100x100 < dimensions < 2000x2000
- File size: > 10KB
- URL patterns: Exclude logos, tracking pixels, icons
- Quality: Prefer larger images (by area)

#### 5. Main App (`src/app.py`)
- Orchestrates the full workflow
- Processes receipts with confidence thresholds
- Maps extracted data to Homebox format
- Saves failed receipts for review
- Handles image extraction and upload

**Processing Flow:**
1. Extract receipt data with MLX
2. Check confidence (min 0.7)
3. Get "Unassigned" location ID
4. Extract images from email (attachments + HTML links)
5. Match images to items
6. Map items to Homebox format
7. Create items (two-step process)
8. Upload images to items (email images first, DuckDuckGo fallback)
9. Move email based on result

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
                     ↓                                       ↓
                Extract Images                    Homebox Client ← App Logic
                (attachments +                              ↓
                 HTML links)                      Homebox API (two-step create)
                     ↓                                       ↓
                Match to Items                    Upload Images → Homebox API
                     ↓                                       ↑
             No images? ────────→ DuckDuckGo Search ────────┘
```

**Image Handling Flow:**
1. Email Fetcher extracts images from email (both attachments and HTML `<img>` tags)
2. Images are validated by size, dimensions, and URL patterns
3. Images are matched to extracted items (N largest images → N items)
4. After creating items in Homebox:
   - If email image available → upload to item
   - If no email image → search DuckDuckGo for product image
   - Upload found image to Homebox item as attachment

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
│   ├── email_fetcher.py    # IMAP email handling + image extraction
│   ├── receipt_extractor_mlx.py  # MLX AI extraction
│   ├── homebox_client.py   # Homebox API client + attachment upload
│   └── image_handler.py    # DuckDuckGo image search
├── config/
│   └── config.yml          # Application configuration
├── data/
│   ├── logs/               # Application logs
│   ├── failed/             # Failed receipts for review
│   ├── processed/          # Successfully processed receipts
│   └── test_images/        # Test images (created by test_images.py)
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

#### Completed (2025-10-08)
- [x] **Image extraction & upload** - Find product images in emails and attach to Homebox items
  - Extracts images from email attachments
  - Downloads images from HTML `<img>` tags
  - DuckDuckGo search fallback when no email images
  - Automatic upload to Homebox items

#### High Priority
- [ ] **Email as PDF attachment** - Convert original receipt email to PDF and attach to item
- [ ] **Product manual finder** - Search for and attach product manuals to items
- [ ] **IMAP support for other providers** - Extend beyond Gmail (Outlook, Fastmail, etc.)

#### Medium Priority
- [ ] Add retry logic for transient failures
- [ ] Custom field mappings per store
- [ ] Duplicate detection (check if item already exists)
- [ ] Batch mode optimizations

#### Low Priority
- [ ] PDF receipt parsing (not just email text)
- [ ] OCR for image-only receipts

## Quick Start for Future Sessions

### Current Status Check
1. Activate venv: `source venv/bin/activate`
2. Check dependencies: `pip list`
3. Test email: `python test_email.py`
4. Test Homebox: `python test_homebox.py`
5. Run processor: `python run_once.py`

### Where We Left Off (2025-10-05)

**What's Working:**
- ✅ Core extraction pipeline (email → AI → Homebox)
- ✅ Two-step Homebox API integration (create + update)
- ✅ Confidence validation with price cross-checking
- ✅ Email organization (auto-move to subfolders)
- ✅ All test scripts functional

**Known Quirks:**
- Homebox API requires two requests: POST to create, PUT to update with price/details
- Gmail nested labels need "/" separator in config
- MLX model needs 4096 tokens for long Amazon product names
- Price must be float in update request (not string)

**Recently Completed (2025-10-08):**

✅ **Image extraction & upload** - COMPLETE
- `src/email_fetcher.py` - Added `_extract_images()` method
  - Extracts image attachments from emails
  - Parses HTML for `<img>` tags and downloads linked images
  - Filters by size (100x100 to 2000x2000), file size (>10KB), URL patterns
  - Validates with Pillow
- `src/homebox_client.py` - Added `upload_attachment()` method
  - Multipart form upload to `/api/v1/items/{id}/attachments`
  - Handles authentication and retry on 401
- `src/image_handler.py` - NEW file for image search
  - DuckDuckGo search fallback when no email images
  - Image filtering and validation
  - Matching images to items
- `src/app.py` - Updated `process_receipt()` flow
  - Extracts images from email
  - Matches images to items
  - Uploads to Homebox after item creation
  - DuckDuckGo fallback if no email images
- `config/config.yml` - Added `enable_image_search` setting
- New dependencies: `Pillow>=10.0.0`, `duckduckgo-search>=5.0.0`

**Next Session - Start Here:**

To work on **email as PDF**:
1. Research Python libraries: `weasyprint` or `pdfkit` for HTML→PDF conversion
2. Email body is already extracted in `email_fetcher.py`
3. Homebox attachment API likely POST to `/api/v1/items/{id}/attachments`

To work on **product manuals**:
1. Extract manufacturer + model from receipt (already in JSON)
2. Search for "{manufacturer} {model} manual PDF"
3. Download and attach to item

To work on **other IMAP providers**:
1. `email_fetcher.py` already uses standard IMAP (should work anywhere)
2. Main changes needed in `.env` (different host/port)
3. Test with Outlook: `outlook.office365.com:993`

## Debugging

Enable debug logging in any script:
```python
logging.basicConfig(level=logging.DEBUG)
```

Check logs:
- `data/logs/processor.log` - Main app logs
- `data/failed/` - Failed receipt extractions
- `data/processed/` - Successfully processed receipts

View Homebox API requests/responses:
- Set `logging.getLogger('homebox_client').setLevel(logging.DEBUG)` in script
