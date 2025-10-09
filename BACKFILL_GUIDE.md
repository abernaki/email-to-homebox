# Backfill Images Guide

This guide explains how to add product images to existing items in your Homebox inventory using the `backfill_images.py` script.

## Why Use the Backfill Script?

The backfill script is useful for:

- **Testing image search** - Process just 1-2 items at a time to test DuckDuckGo search
- **Adding images to existing items** - Don't need to process receipt emails
- **Avoiding rate limits** - Control exactly how many searches to run
- **Backfilling your inventory** - Add images to items created before image feature

## Quick Start

### Test with 1 Item

```bash
python backfill_images.py --max-items 1
```

This will:
1. Fetch 1 item from Homebox that doesn't have images
2. Search DuckDuckGo for a product image
3. Upload the image to Homebox
4. Show success/failure result

### Preview Mode (Dry Run)

```bash
python backfill_images.py --max-items 10 --dry-run
```

This shows you which items would be processed without actually uploading images.

### Process Default Amount

```bash
python backfill_images.py
```

Processes 5 items (default safe amount to avoid rate limits).

## Command-Line Options

### `--max-items N`

Maximum number of items to process.

```bash
python backfill_images.py --max-items 1    # Test with 1 item
python backfill_images.py --max-items 10   # Process 10 items
python backfill_images.py --max-items 100  # Process 100 items (not recommended)
```

**Recommended values:**
- Testing: `1-2`
- Regular use: `5-10`
- Large backfill: Run multiple times with `5-10` to avoid rate limits

### `--location "Location Name"`

Filter items by location.

```bash
python backfill_images.py --location "Unassigned"
python backfill_images.py --location "Kitchen"
```

### `--dry-run`

Preview what would be done without uploading images.

```bash
python backfill_images.py --max-items 20 --dry-run
```

Output:
```
Items to process (20):
  1. USB-C Cable ($12.99) - Unassigned
  2. Phone Charger ($25.00) - Unassigned
  ...

Estimated time: ~60s (with rate limiting)
```

### `--force`

Skip the confirmation prompt.

```bash
python backfill_images.py --force
```

Useful for automation or when you're confident in the settings.

### `--include-with-images`

Process items even if they already have images (replaces existing images).

```bash
python backfill_images.py --include-with-images
```

**Warning:** This will add duplicate images if items already have them.

## Usage Examples

### Example 1: Test Image Search

**Goal:** Test if image search is working with 1 item.

```bash
python backfill_images.py --max-items 1
```

**Output:**
```
==========================================================
Homebox Image Backfill
==========================================================

Configuration:
  Max items: 1
  Location filter: None
  Rate limit delay: 2.5s
  Dry run: No

Fetching items from Homebox...
Found 47 total items in Homebox
Found 42 items without images

Items to process (1):
  1. USB-C Cable ($12.99) - Unassigned

Estimated time: ~3s (with rate limiting)

Proceed with image search and upload? [y/N]: y

==========================================================
Processing...
==========================================================

[1/1] USB-C Cable
  Searching DuckDuckGo for 'USB-C Cable'...
  ✓ Found image (800x800, 125,432 bytes)
  Uploading image...
  ✓ Successfully uploaded image

==========================================================
Summary
==========================================================
Processed: 1 items
Success: 1
Failed: 0
Skipped: 0
Time: 3.2s
```

### Example 2: Process Unassigned Items

**Goal:** Add images to all items in "Unassigned" location (limited to 5).

```bash
python backfill_images.py --location "Unassigned"
```

This only processes items in the "Unassigned" location, up to the default max of 5.

### Example 3: Large Backfill (Safe Approach)

**Goal:** Add images to 50 items without hitting rate limits.

**Don't do this:**
```bash
python backfill_images.py --max-items 50  # Will likely hit rate limits!
```

**Do this instead:**
```bash
# Run 1: Process 5 items
python backfill_images.py --max-items 5 --force

# Wait a few minutes...

# Run 2: Process 5 more items
python backfill_images.py --max-items 5 --force

# Repeat 10 times to process 50 items total
```

Or use a shell loop with delays:
```bash
for i in {1..10}; do
  echo "Batch $i of 10"
  python backfill_images.py --max-items 5 --force
  echo "Waiting 60 seconds before next batch..."
  sleep 60
done
```

### Example 4: Preview Large Backfill

**Goal:** See what items would be processed before committing.

```bash
python backfill_images.py --max-items 20 --dry-run
```

Review the list, then run without `--dry-run` if it looks good.

## Configuration

Edit `config/config.yml` to change default settings:

```yaml
backfill:
  # Default max items when --max-items not specified
  default_max_items: 5

  # Skip items that already have images
  skip_items_with_images: true

  # Default location filter
  default_location_filter: ""  # or "Unassigned"
```

The script also uses rate limiting settings from the `processing` section:

```yaml
processing:
  image_search_delay: 2.5  # Seconds between searches
```

## Rate Limiting

The backfill script uses the same rate limiting as receipt processing:

- **Delay between searches:** 2.5 seconds (configurable in `config.yml`)
- **First item:** No delay
- **Subsequent items:** 2.5s delay before each search

**Time estimates:**
- 1 item: ~3 seconds
- 5 items: ~15 seconds
- 10 items: ~30 seconds
- 20 items: ~60 seconds

**If you hit rate limits:**

1. **Reduce max-items:**
   ```bash
   python backfill_images.py --max-items 2
   ```

2. **Increase delay in config.yml:**
   ```yaml
   processing:
     image_search_delay: 5.0  # Increase from 2.5s to 5s
   ```

3. **Add delays between runs:**
   ```bash
   python backfill_images.py --max-items 3 --force
   sleep 60
   python backfill_images.py --max-items 3 --force
   ```

## Troubleshooting

### "No items found to process!"

**Possible causes:**
1. All items already have images
2. Location filter too restrictive
3. No items in Homebox

**Solutions:**
```bash
# Try without location filter
python backfill_images.py --max-items 5

# Include items with images (for testing)
python backfill_images.py --max-items 1 --include-with-images

# Check Homebox has items
python test_homebox.py
```

### "Failed to connect to Homebox"

**Check:**
1. Homebox is running
2. `.env` has correct `HOMEBOX_URL`
3. `.env` has correct `HOMEBOX_USERNAME` and `HOMEBOX_PASSWORD`

```bash
# Test connection
python test_homebox.py
```

### "No images found" for every item

**Possible causes:**
1. Product names too generic
2. Rate limiting (search returning empty)
3. DuckDuckGo issues

**Solutions:**
```bash
# Test with a well-known product
# (Temporarily edit an item name in Homebox to "iPhone 15 Pro")
python backfill_images.py --max-items 1

# Increase delay
# Edit config.yml: image_search_delay: 5.0

# Try again later (might be temporary DuckDuckGo issue)
```

### Rate limit errors

**Symptoms:**
```
WARNING - Rate limit detected, retrying in 2s (attempt 1/3)
WARNING - Rate limit detected, retrying in 4s (attempt 2/3)
ERROR - Failed to search for 'Product' after 3 attempts
```

**Solutions:**
1. **Use smaller max-items:**
   ```bash
   python backfill_images.py --max-items 1
   ```

2. **Add manual delays between runs:**
   ```bash
   python backfill_images.py --max-items 2
   sleep 120  # Wait 2 minutes
   python backfill_images.py --max-items 2
   ```

3. **Increase delay in config:**
   ```yaml
   processing:
     image_search_delay: 10.0  # Very conservative
   ```

## Best Practices

### For Testing

✅ **Do:**
- Start with `--max-items 1`
- Use `--dry-run` first
- Test with well-known products

❌ **Don't:**
- Process 50+ items at once
- Skip testing with dry-run
- Ignore rate limit warnings

### For Regular Use

✅ **Do:**
- Process 5-10 items at a time
- Add delays between large backfills
- Monitor for rate limit errors

❌ **Don't:**
- Run continuously without delays
- Process 100+ items in one run
- Ignore failed uploads

### For Large Backfills

✅ **Do:**
- Use automation with delays
- Process in batches of 5-10
- Monitor logs for issues

```bash
# Good approach for 50 items
for i in {1..10}; do
  python backfill_images.py --max-items 5 --force
  sleep 60
done
```

❌ **Don't:**
```bash
# Bad approach - will hit rate limits
python backfill_images.py --max-items 50
```

## Advanced Usage

### Filter by Multiple Criteria

The script currently supports location filtering. To add more filters, edit the script and add custom logic:

```python
# Example: Only items over $20
if full_item.get('purchasePrice', 0) < 20:
    continue
```

### Custom Delay Per Run

```bash
# Temporarily use longer delay
# Edit config.yml before running
python backfill_images.py --max-items 10
# Change back after
```

### Automation

Create a cron job to backfill a few items daily:

```bash
# Add to crontab
0 2 * * * cd /path/to/email-to-homebox && ./venv/bin/python backfill_images.py --max-items 5 --force >> data/logs/backfill.log 2>&1
```

This runs at 2 AM daily, processes 5 items, logs output.

## FAQ

**Q: Can I process all items at once?**
A: Technically yes with `--max-items 1000`, but you'll hit rate limits. Better to process in batches.

**Q: How do I know if an item already has images?**
A: The script automatically skips items with images (unless you use `--include-with-images`).

**Q: Can I undo uploaded images?**
A: Delete them manually in Homebox UI. The script doesn't have a delete function.

**Q: What happens if the script crashes?**
A: Already uploaded images remain. Re-run the script - it will skip items with images.

**Q: Can I process specific items by name?**
A: Not currently. You can use `--location` filter or edit the script to add name filtering.

**Q: Will this process receipts?**
A: No, this only processes existing items in Homebox. Use `run_once.py` for receipt processing.

## Related Commands

- **Process receipts:** `python run_once.py`
- **Test email:** `python test_email.py`
- **Test images:** `python test_images.py`
- **Test Homebox:** `python test_homebox.py`

## Summary

The backfill script is a safe way to add images to existing items while respecting rate limits. Key points:

- Start with `--max-items 1` for testing
- Use `--dry-run` to preview
- Process 5-10 items at a time for regular use
- Add delays between large backfills
- Monitor logs for rate limit warnings

For questions or issues, see the main [README.md](ReadMe.md) or check logs in `data/logs/`.
