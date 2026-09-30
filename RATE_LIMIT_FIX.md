# Rate Limiting & Attachment Upload Fixes

**Date:** 2025-10-08

## Issues Fixed

### 1. DuckDuckGo Rate Limiting
**Problem:** Processing receipts with multiple items caused rapid-fire DuckDuckGo searches, triggering rate limits.

**Solution:** Implemented multi-layer rate limiting protection:
- Configurable delays between searches (default: 2.5 seconds)
- Maximum searches per receipt limit (default: 3)
- Optional price threshold to only search expensive items
- Exponential backoff retry logic (2s, 4s, 8s)
- Graceful error handling

### 2. Homebox Attachment Upload Failure
**Problem:** Attachment uploads were failing because Homebox requires a 'name' field in the upload request.

**Solution:** Added the 'name' field to the multipart form data in both the initial upload and retry logic.

## Changes Made

### Modified Files

1. **`config/config.yml`** - Added rate limiting settings:
   ```yaml
   processing:
     enable_image_search: true
     image_search_delay: 2.5               # Seconds between searches
     max_image_searches_per_receipt: 3     # Max searches per receipt
     image_search_min_price: 0.0           # Only search items above this price
   ```

2. **`src/app.py`** - `upload_images_to_items()` function:
   - Added search counter to track number of searches
   - Added configurable delay between searches (skips first search)
   - Added max searches limit (stops after N searches)
   - Added price threshold check (skip cheap items)
   - Improved error handling and logging
   - Added price field to created_items

3. **`src/homebox_client.py`** - `upload_attachment()` method:
   - Added 'name' field to multipart form data
   - Fixed both initial upload and retry logic

4. **`src/image_handler.py`** - `search_product_image()` function:
   - Added retry loop with max_retries parameter
   - Added exponential backoff for rate limit errors
   - Detects rate limit errors by message content
   - Returns empty list after all retries exhausted

## How It Works

### Rate Limiting Protection Flow

```
For each item without email image:
  ↓
Check search count < max_searches? ──No──> Skip item
  ↓ Yes
Check item price >= min_price? ──No──> Skip item
  ↓ Yes
Is this first search? ──No──> Wait [delay] seconds
  ↓ Yes
Try DuckDuckGo search (with retry logic):
  ↓
  Try search
    ↓
  Success? ──Yes──> Return images
    ↓ No
  Rate limit error? ──Yes──> Wait 2^attempt seconds, retry
    ↓ No
  Other error? ──Yes──> Return empty list
    ↓
  Max retries reached? ──Yes──> Return empty list
```

### Retry Logic (Exponential Backoff)

- **Attempt 1:** Immediate search
- **Attempt 2:** Wait 2 seconds, retry
- **Attempt 3:** Wait 4 seconds, retry
- **Attempt 4:** Wait 8 seconds, fail

Rate limit errors are detected by checking for these keywords in error messages:
- 'rate limit'
- 'ratelimit'
- 'too many requests'
- '429'

## Configuration Options

### In `config/config.yml`

```yaml
processing:
  # Enable/disable DuckDuckGo search entirely
  enable_image_search: true

  # Seconds to wait between searches (prevents rapid requests)
  image_search_delay: 2.5

  # Maximum searches per receipt (prevents hitting limits on large receipts)
  max_image_searches_per_receipt: 3

  # Only search for items above this price (0 = search all)
  # Example: Set to 20.0 to only search items over $20
  image_search_min_price: 0.0
```

### Recommended Settings

**Conservative (avoid rate limits):**
```yaml
image_search_delay: 3.0
max_image_searches_per_receipt: 2
image_search_min_price: 20.0  # Only search expensive items
```

**Balanced (default):**
```yaml
image_search_delay: 2.5
max_image_searches_per_receipt: 3
image_search_min_price: 0.0
```

**Aggressive (risk of rate limits):**
```yaml
image_search_delay: 1.5
max_image_searches_per_receipt: 5
image_search_min_price: 0.0
```

**Disable search (email images only):**
```yaml
enable_image_search: false
```

## Testing

Run the processor to test the fixes:

```bash
source venv/bin/activate
python run_once.py --live
```

You should see log messages like:
```
2025-10-08 - app - INFO - No email image for 'USB Cable', searching DuckDuckGo... (search 1/3)
2025-10-08 - app - DEBUG - Waiting 2.5s before next search (rate limit protection)
2025-10-08 - app - INFO - No email image for 'Phone Charger', searching DuckDuckGo... (search 2/3)
2025-10-08 - app - DEBUG - Reached max searches (3), skipping 'Headphones'
```

If rate limiting occurs, you'll see:
```
2025-10-08 - image_handler - WARNING - Rate limit detected, retrying in 2s (attempt 1/3)
```

## Example Scenarios

### Scenario 1: Large Receipt (10 items, no email images)
**Before fix:** All 10 items trigger immediate searches → Rate limited after ~5 searches → Processing fails

**After fix:**
- Item 1: Search immediately (0s delay)
- Item 2: Wait 2.5s, search
- Item 3: Wait 2.5s, search
- Items 4-10: Skipped (hit max_searches limit)
- Total time: ~5 seconds
- Result: 3 searches completed successfully, no rate limiting

### Scenario 2: Receipt with mixed prices
**Config:** `image_search_min_price: 20.0`

**Items:**
- Phone ($500) → Searched
- Cable ($10) → Skipped (below threshold)
- Case ($15) → Skipped (below threshold)
- Charger ($25) → Searched

**Result:** Only 2 searches for expensive items, saves API quota

### Scenario 3: Rate limit hit during search
**What happens:**
1. First search succeeds
2. Second search hits rate limit
3. System waits 2s, retries → succeeds
4. Third search succeeds
5. Processing continues normally

## Troubleshooting

### Still hitting rate limits?

1. **Increase delay:**
   ```yaml
   image_search_delay: 5.0  # Wait 5 seconds between searches
   ```

2. **Reduce max searches:**
   ```yaml
   max_image_searches_per_receipt: 1  # Only search first item
   ```

3. **Use price threshold:**
   ```yaml
   image_search_min_price: 50.0  # Only search items over $50
   ```

4. **Disable search entirely:**
   ```yaml
   enable_image_search: false  # Only use email images
   ```

### Attachments still failing to upload?

Check the logs for the exact error:
```bash
tail -f data/logs/processor.log
```

Common issues:
- Authentication failed → Check HOMEBOX_USERNAME and HOMEBOX_PASSWORD in `.env`
- File too large → Check Homebox file size limits
- Quota exceeded → Check Homebox storage quota

## Notes

- The first search in a batch has **no delay** to avoid unnecessary waiting
- Failed searches still count toward the max_searches limit
- Price threshold only applies to DuckDuckGo search, email images are always uploaded
- Retry logic only applies to rate limit errors, other errors fail immediately
- All configuration values have sensible defaults if not specified

## Performance Impact

With default settings (2.5s delay, 3 max searches):
- Receipt with 1 item: ~0s delay
- Receipt with 2 items: ~2.5s delay
- Receipt with 3 items: ~5s delay
- Receipt with 10+ items: ~5s delay (only searches first 3)

This is a reasonable tradeoff to avoid rate limiting while still providing image search functionality.
