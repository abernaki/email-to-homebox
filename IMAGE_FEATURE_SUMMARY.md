# Product Image Extraction & Upload - Implementation Summary

**Date Completed:** 2025-10-08

## Overview

Successfully implemented automatic product image extraction and upload functionality. The system now:
1. Extracts images from receipt emails (attachments + HTML links)
2. Uses DuckDuckGo search as fallback when no email images found
3. Automatically uploads images to Homebox items

## What Was Changed

### New Files Created

1. **`src/image_handler.py`** - DuckDuckGo image search and matching
   - `search_product_image()` - Search for product images
   - `get_best_image()` - Select best image from results
   - `match_images_to_items()` - Match images to receipt items

2. **`test_images.py`** - Test script for image extraction
   - Fetches receipt email
   - Extracts and validates images
   - Saves test image to `data/test_images/`

### Modified Files

1. **`src/email_fetcher.py`**
   - Added `_extract_images()` method
   - Extracts image attachments from emails
   - Parses HTML for `<img>` tags
   - Downloads linked images from URLs
   - Filters by size, dimensions, URL patterns
   - Validates with Pillow

2. **`src/homebox_client.py`**
   - Added `upload_attachment()` method
   - Multipart form upload to `/api/v1/items/{id}/attachments`
   - Handles authentication and token refresh

3. **`src/app.py`**
   - Added `upload_images_to_items()` function
   - Modified `process_receipt()` to:
     - Extract images from email
     - Match images to items
     - Upload images after item creation
     - Fall back to DuckDuckGo search if needed

4. **`config/config.yml`**
   - Added `enable_image_search: true` setting
   - Controls DuckDuckGo fallback behavior

5. **`requirements.txt`**
   - Added `Pillow>=10.0.0` for image processing
   - Added `duckduckgo-search>=5.0.0` for image search

6. **Documentation Updates**
   - Updated `ARCHITECTURE.md` with image handling architecture
   - Updated `ReadMe.md` with image features and testing
   - Updated `.gitignore` to exclude test images

## How It Works

### Image Extraction Flow

1. **Email Processing**
   ```
   Email → Email Fetcher → Extract Images
                              ↓
                       Attachments + HTML <img> tags
                              ↓
                       Download & Validate
                              ↓
                       Filter by:
                       - Size: 100x100 to 2000x2000
                       - File size: > 10KB
                       - URL patterns (exclude logos/tracking)
                              ↓
                       Match to Items
   ```

2. **Image Upload Flow**
   ```
   Items Created → Check for matched email image
                              ↓
                       Email image? ──Yes──> Upload to Homebox
                              │
                              No
                              ↓
                   enable_image_search? ──No──> Skip
                              │
                              Yes
                              ↓
                   Search DuckDuckGo ──Found──> Upload to Homebox
                              │
                              Not Found
                              ↓
                            Skip
   ```

### Image Filtering

**Include patterns:**
- `/product/`, `/item/`, `/images/i/` (Amazon)
- `/media/`, `/catalog/`, `/goods/`

**Exclude patterns:**
- `/logo/`, `/icon/`, `/button/`, `/tracking/`
- `/badge/`, `/banner/`, `/footer/`, `/header/`
- `tracking`, `analytics`, `1x1`, `transparent.gif`

**Size constraints:**
- Dimensions: 100x100 to 2000x2000 pixels
- File size: > 10KB
- Prefers larger images (sorted by area)

## Testing

### Test Image Extraction

```bash
source venv/bin/activate
python test_images.py
```

This will:
- Fetch a receipt email
- Extract and validate images
- Show image metadata (dimensions, source, URL)
- Save first image to `data/test_images/test_image_1.jpg`

### Test Full Flow

```bash
python run_once.py
```

This will:
- Process all receipts in folder
- Extract images from emails
- Create items in Homebox
- Upload images to items
- Use DuckDuckGo search as fallback

## Configuration

In `config/config.yml`:

```yaml
processing:
  # Enable DuckDuckGo image search fallback
  enable_image_search: true
```

Set to `false` to disable DuckDuckGo fallback (only use email images).

## Dependencies Installed

```bash
pip install Pillow ddgs
```

Or update from requirements.txt:

```bash
pip install -r requirements.txt
```

**Note:** The package was originally `duckduckgo-search` but has been renamed to `ddgs`. If you see a deprecation warning, run:
```bash
pip uninstall duckduckgo-search
pip install ddgs
```

## Known Limitations

1. **Email Images**
   - Requires valid email credentials to test
   - May not find images in old/text-only emails
   - HTML parsing depends on email format

2. **DuckDuckGo Search**
   - Requires internet connection
   - Search quality depends on product name
   - May return incorrect images for generic products
   - Rate limiting may apply

3. **Image Matching**
   - Simple strategy: N largest images → N items
   - Cannot identify which image matches which item
   - Multi-item receipts may have mismatched images

4. **Homebox Upload**
   - Requires valid Homebox credentials
   - May fail if attachment quota exceeded
   - File size limits depend on Homebox configuration

## Future Enhancements

Possible improvements:
- AI-based image-to-item matching using product names
- Image deduplication (avoid uploading same image twice)
- Support for more image sources (product website scraping)
- Better handling of multi-item receipts
- Image quality assessment (blur detection, etc.)
- Retry logic for failed downloads
- Progress indicators for large batches

## Notes

- Image extraction is **non-blocking** - if it fails, receipt processing continues
- All image processing happens **locally** (except DuckDuckGo search)
- Images are **validated** before upload (dimensions, format, size)
- DuckDuckGo search is **optional** and can be disabled in config
- Test images saved to `data/test_images/` are **gitignored**

## Example Output

```
2025-10-08 22:58:53 - email_fetcher - INFO - Found 3 product images from email
2025-10-08 22:58:53 - app - INFO - ✓ Added to Homebox: USB Cable ($12.99) [ID: abc123]
2025-10-08 22:58:54 - homebox_client - INFO - ✓ Uploaded attachment: usb_cable.jpg
2025-10-08 22:58:54 - app - INFO - ✓ Uploaded image for: USB Cable
```

## Support

If you encounter issues:
1. Check email credentials in `.env`
2. Run `python test_images.py` to debug image extraction
3. Check logs in `data/logs/processor.log`
4. Verify Homebox connection with `python test_homebox.py`
5. Set `LOG_LEVEL=DEBUG` in `.env` for detailed output
