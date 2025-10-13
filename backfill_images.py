#!/usr/bin/env python3
"""
Backfill images for existing Homebox items

This script searches for and uploads product images to existing items in your
Homebox inventory. Useful for testing image search and adding images to items
that were created without them.

Images are filtered by filename patterns to skip logos and icons.

Usage:
    python backfill_images.py                         # Process 5 items (default)
    python backfill_images.py --max-items 10          # Process 10 items
    python backfill_images.py --max-items 1           # Test with 1 item
    python backfill_images.py --location "Unassigned" # Filter by location
    python backfill_images.py --dry-run               # Preview what would be done
    python backfill_images.py --force                 # Skip confirmation prompt
    python backfill_images.py --include-with-images   # Process items even if they have images
"""

import os
import sys
import time
import yaml
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from homebox_client import HomeboxClient
from image_handler import search_product_image

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()


def load_config():
    """Load configuration"""
    config_path = Path('config/config.yml')
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_items_without_images(homebox, location_filter=None, max_items=None):
    """
    Fetch items from Homebox that don't have images

    Args:
        homebox: HomeboxClient instance
        location_filter: Optional location name to filter by
        max_items: Maximum items to return

    Returns:
        List of items without images
    """
    logger.info("Fetching items from Homebox...")

    all_items = []
    page = 1

    # Fetch all items (paginated)
    while True:
        result = homebox.get_items(page=page, page_size=50)
        if not result or 'items' not in result:
            break

        items = result.get('items', [])
        if not items:
            break

        all_items.extend(items)

        # Check if there are more pages
        total = result.get('total', 0)
        if len(all_items) >= total:
            break

        page += 1

    logger.info(f"Found {len(all_items)} total items in Homebox")

    # Filter items
    filtered_items = []

    for item in all_items:
        # Get full item details to check attachments
        item_id = item.get('id')
        full_item = homebox.get_item(item_id)

        if not full_item:
            continue

        # Check location filter
        if location_filter:
            location_name = full_item.get('location', {}).get('name', '')
            if location_name.lower() != location_filter.lower():
                continue

        # Check if item has attachments
        attachments = full_item.get('attachments', [])
        has_images = any(att.get('type') == 'photo' for att in attachments)

        if not has_images:
            filtered_items.append(full_item)

        # Stop if we have enough items
        if max_items and len(filtered_items) >= max_items:
            break

    logger.info(f"Found {len(filtered_items)} items without images")
    return filtered_items


def backfill_images(items, config, dry_run=False):
    """
    Search for and upload images to items

    Args:
        items: List of items to process
        config: Configuration dict
        dry_run: If True, don't actually upload images

    Returns:
        Dict with success, failed, and skipped counts
    """
    processing_config = config.get('processing', {})
    search_delay = processing_config.get('image_search_delay', 2.5)

    # Check if we should label items with AI-populated images
    label_ai_images = processing_config.get('label_ai_images', True)
    label_name = processing_config.get('ai_image_label_name', 'Verify Image')

    homebox = HomeboxClient()

    # Ensure label exists if labeling is enabled
    label_id = None
    if label_ai_images and not dry_run:
        label_id = homebox.ensure_label_exists(
            label_name,
            description="Items with AI-populated images that need manual verification",
            color="#F59E0B"  # Orange color for attention
        )
        if not label_id:
            logger.warning(f"Failed to create/find label '{label_name}', labeling disabled")
            label_ai_images = False

    results = {
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    for idx, item in enumerate(items, 1):
        item_id = item.get('id')
        item_name = item.get('name', 'Unknown')
        manufacturer = item.get('manufacturer')
        purchase_price = item.get('purchasePrice', 0.0)

        logger.info(f"[{idx}/{len(items)}] {item_name}")

        # Add delay before search (except first item)
        if idx > 1:
            logger.debug(f"  Waiting {search_delay}s (rate limit protection)")
            if not dry_run:
                time.sleep(search_delay)

        # Search for image
        logger.info(f"  Searching DuckDuckGo for '{item_name}'...")

        if dry_run:
            logger.info(f"  [DRY RUN] Would search for image")
            results['success'] += 1
            continue

        try:
            # Search for image (get just 1 result, filtering handled by search function)
            search_results = search_product_image(item_name, manufacturer, max_results=1)

            if not search_results:
                logger.warning(f"  ✗ No images found")
                results['failed'] += 1
                continue

            image = search_results[0]
            logger.info(f"  ✓ Using image ({image['width']}x{image['height']}, {image['size']:,} bytes)")

            # Upload image
            logger.info(f"  Uploading image...")
            result = homebox.upload_attachment(
                item_id=item_id,
                image_data=image['data'],
                filename=image.get('filename', f"{item_name[:30]}.jpg"),
                attachment_type="photo"
            )

            if result:
                logger.info(f"  ✓ Successfully uploaded image")
                results['success'] += 1

                # Add label if enabled
                if label_ai_images and label_id:
                    if homebox.add_label_to_item(item_id, label_id):
                        logger.debug(f"  ✓ Added '{label_name}' label")
                    else:
                        logger.warning(f"  Failed to add '{label_name}' label")
            else:
                logger.warning(f"  ✗ Failed to upload image")
                results['failed'] += 1

        except Exception as e:
            logger.error(f"  ✗ Error processing item: {e}")
            results['failed'] += 1

    return results


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Backfill product images for existing Homebox items',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backfill_images.py                    # Process 5 items (default)
  python backfill_images.py --max-items 1      # Test with just 1 item
  python backfill_images.py --max-items 10     # Process 10 items
  python backfill_images.py --dry-run          # Preview without uploading
  python backfill_images.py --location "Unassigned"  # Filter by location
        """
    )

    parser.add_argument('--max-items', type=int, default=5,
                        help='Maximum number of items to process (default: 5)')
    parser.add_argument('--location', type=str, default=None,
                        help='Filter items by location name')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would be done without uploading')
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt')
    parser.add_argument('--include-with-images', action='store_true',
                        help='Include items that already have images')

    args = parser.parse_args()

    print("=" * 60)
    print("Homebox Image Backfill")
    print("=" * 60)

    # Load configuration
    config = load_config()
    processing_config = config.get('processing', {})

    print(f"\nConfiguration:")
    print(f"  Max items: {args.max_items}")
    print(f"  Location filter: {args.location or 'None'}")
    print(f"  Rate limit delay: {processing_config.get('image_search_delay', 2.5)}s")
    print(f"  Dry run: {'Yes' if args.dry_run else 'No'}")

    if args.dry_run:
        print("\n*** DRY RUN MODE - No images will be uploaded ***")

    # Initialize Homebox client
    homebox = HomeboxClient()
    if not homebox.test_connection():
        logger.error("Failed to connect to Homebox")
        sys.exit(1)

    # Fetch items
    print()
    items = get_items_without_images(
        homebox,
        location_filter=args.location,
        max_items=args.max_items
    )

    if not items:
        print("\nNo items found to process!")
        print("Try:")
        print("  - Removing --location filter")
        print("  - Using --include-with-images flag")
        print("  - Adding more items to Homebox")
        sys.exit(0)

    # Show items to process
    print(f"\nItems to process ({len(items)}):")
    for idx, item in enumerate(items, 1):
        name = item.get('name', 'Unknown')
        price = item.get('purchasePrice', 0.0)
        location = item.get('location', {}).get('name', 'Unknown')
        print(f"  {idx}. {name} (${price:.2f}) - {location}")

    # Estimate time
    delay = processing_config.get('image_search_delay', 2.5)
    est_time = (len(items) - 1) * delay + (len(items) * 3)  # 3s per search
    print(f"\nEstimated time: ~{int(est_time)}s (with rate limiting)")

    # Confirm
    if not args.force and not args.dry_run:
        response = input("\nProceed with image search and upload? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)

    # Process items
    print("\n" + "=" * 60)
    print("Processing...")
    print("=" * 60 + "\n")

    start_time = time.time()
    results = backfill_images(items, config, dry_run=args.dry_run)
    elapsed = time.time() - start_time

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Processed: {len(items)} items")
    print(f"Success: {results['success']}")
    print(f"Failed: {results['failed']}")
    print(f"Skipped: {results['skipped']}")
    print(f"Time: {elapsed:.1f}s")

    if args.dry_run:
        print("\n*** This was a dry run - no images were uploaded ***")
        print("Run without --dry-run to actually upload images")


if __name__ == '__main__':
    main()
