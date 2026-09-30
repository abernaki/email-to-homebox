#!/usr/bin/env python3
"""
Receipt Processor - Main Application
Monitors email for receipts, extracts data with Ollama, and adds to Homebox
"""

import os
import sys
import time
import argparse
import logging
import yaml
from datetime import datetime
from pathlib import Path

from homebox_mapping import map_to_homebox_item, sanitize_item_name
from homebox_errors import PartialEntityUpdateError

# Setup logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
log_dir = Path('data/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'processor.log')
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from YAML file"""
    config_file = os.getenv('CONFIG_FILE', 'config/config.yml')
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_file}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise


def is_all_consumable(receipt_data, config):
    """
    Check if all items in receipt are consumable

    Args:
        receipt_data: Extracted receipt data with items
        config: Application config

    Returns:
        tuple: (is_consumable: bool, categories: list)
    """
    processing_config = config.get('processing', {})
    consumable_categories = processing_config.get('consumable_categories', [])

    if not consumable_categories:
        return False, []

    items = receipt_data.get('items', [])
    if not items:
        return False, []

    # Get all item categories
    item_categories = [item.get('category', 'other') for item in items]

    # Check if all items are in consumable categories
    all_consumable = all(cat in consumable_categories for cat in item_categories)

    return all_consumable, item_categories


def process_receipt(email_data, extractor, homebox, config):
    """Process a single receipt email"""
    try:
        logger.info(f"Processing email: {email_data['subject']}")

        # Extract receipt data using Ollama
        receipt_data = extractor.extract(email_data)

        if not receipt_data:
            logger.warning("Failed to extract receipt data")
            save_failed_receipt(email_data, "extraction_failed")
            return {'status': 'failed', 'reason': 'extraction_failed'}

        # Check if manual review is needed (e.g., PDF extraction failed)
        if receipt_data.get('_manual_review'):
            reason = receipt_data.get('_reason', 'unknown')
            logger.warning(f"Manual review required: {reason}")
            save_failed_receipt(email_data, "manual_review", receipt_data)
            return {'status': 'failed', 'reason': 'manual_review', 'details': reason}

        # Check if LLM returned no items (e.g., Square receipts with no line items)
        if receipt_data.get('_no_items_found'):
            logger.info(f"Receipt has no line items (store: {receipt_data.get('store')}, total: {receipt_data.get('total')})")
            save_processed_receipt(email_data, receipt_data)  # Save for reference
            return {'status': 'no_items', 'store': receipt_data.get('store'), 'total': receipt_data.get('total')}

        # Check confidence level
        confidence = receipt_data.get('confidence', 0)
        min_confidence = config['processing']['min_confidence']

        if confidence < min_confidence:
            logger.warning(f"Low confidence ({confidence:.2f} < {min_confidence})")
            save_failed_receipt(email_data, "low_confidence", receipt_data)
            return {'status': 'low_confidence', 'confidence': confidence}

        # Check if all items are consumable
        processing_config = config.get('processing', {})
        if processing_config.get('skip_consumables', False):
            is_consumable, categories = is_all_consumable(receipt_data, config)
            if is_consumable:
                logger.info(f"All items are consumable (categories: {', '.join(set(categories))}), skipping")
                save_processed_receipt(email_data, receipt_data)  # Save for reference
                return {'status': 'consumable', 'categories': categories}

        # Get the default location ID
        default_location = config['homebox'].get('default_location', 'Unassigned')
        location_id = homebox.get_location_id_by_name(default_location)

        if not location_id:
            logger.error(f"Location '{default_location}' not found in Homebox")
            save_failed_receipt(email_data, "location_not_found", receipt_data)
            return {'status': 'failed', 'reason': 'location_not_found'}

        # Get images from email
        email_images = email_data.get('images', [])
        logger.info(f"Found {len(email_images)} image(s) in email")

        # Match images to items if available
        image_matches = {}
        if email_images:
            from image_handler import match_images_to_items

            image_matches = match_images_to_items(email_images, receipt_data.get('items', []))

        # Add items to Homebox
        success_count = 0
        created_items = []  # Track created items for image upload

        for idx, item in enumerate(receipt_data.get('items', [])):
            try:
                # Skip non-physical items (subscriptions, memberships, etc.)
                if is_non_physical_item(item, config):
                    logger.info(f"⊘ Skipping non-physical item: {item['name']}")
                    continue

                homebox_item = map_to_homebox_item(item, receipt_data, config, location_id)
                result = homebox.create_item(homebox_item)

                if result:
                    success_count += 1
                    item_id = result.get('id')
                    logger.info(f"✓ Added to Homebox: {item['name']} (${item['price']}) [ID: {item_id}]")

                    # Store item info for image upload
                    created_items.append({
                        'id': item_id,
                        'name': item['name'],
                        'price': item.get('price', 0.0),
                        'manufacturer': item.get('manufacturer'),
                        'index': idx
                    })
                else:
                    logger.error(f"✗ Failed to add: {item['name']}")
            except PartialEntityUpdateError as e:
                logger.error(
                    "Homebox entity %s was created without all purchase details; "
                    "stopping receipt processing to prevent duplicate creation",
                    e.entity_id,
                )
                try:
                    save_failed_receipt(email_data, 'partial_homebox_write', receipt_data)
                except Exception:
                    logger.exception("Could not persist partial Homebox write for manual review")
                return {
                    'status': 'partial_write',
                    'reason': 'purchase_update_failed',
                    'entity_id': e.entity_id,
                }
            except Exception as e:
                logger.error(f"Error adding item {item.get('name')}: {e}")

        # Upload images to created items
        if created_items:
            upload_images_to_items(created_items, image_matches, homebox, config)

        # Upload PDF to first item if available
        if created_items and 'pdf_data' in email_data:
            first_item_id = upload_pdf_to_first_item(created_items, email_data, homebox)
            # Add cross-references to other items
            if first_item_id and len(created_items) > 1:
                add_pdf_cross_references(created_items, first_item_id, homebox)

        # Save processed receipt
        if config['processing']['save_processed']:
            save_processed_receipt(email_data, receipt_data)

        logger.info(f"Successfully processed {success_count}/{len(receipt_data['items'])} items")
        return {'status': 'success', 'items_added': success_count}

    except Exception as e:
        logger.error(f"Error processing receipt: {e}", exc_info=True)
        save_failed_receipt(email_data, str(e))
        return {'status': 'failed', 'reason': str(e)}


def is_non_physical_item(item, config):
    """
    Detect if an item is non-physical (subscription, membership, digital item, etc.)

    Args:
        item: Item dict with 'name', 'category', 'description', etc.
        config: Configuration dict

    Returns:
        bool: True if item is non-physical and should be skipped
    """
    processing_config = config.get('processing', {})

    # Check if filtering is enabled
    if not processing_config.get('skip_non_physical', False):
        return False

    # Check category
    non_physical_categories = processing_config.get('non_physical_categories', [])
    if item.get('category') in non_physical_categories:
        logger.debug(f"Item '{item.get('name')}' is non-physical (category: {item.get('category')})")
        return True

    # Check keywords in name and description
    non_physical_keywords = processing_config.get('non_physical_keywords', [])
    item_text = f"{item.get('name', '')} {item.get('description', '')}".lower()

    for keyword in non_physical_keywords:
        if keyword.lower() in item_text:
            logger.debug(f"Item '{item.get('name')}' is non-physical (keyword: {keyword})")
            return True

    return False


def upload_images_to_items(created_items, image_matches, homebox, config):
    """
    Upload images to created Homebox items

    Args:
        created_items: List of created item dicts with 'id', 'name', 'manufacturer', 'index'
        image_matches: Dict mapping item indices to image data
        homebox: HomeboxClient instance
        config: Application config
    """
    processing_config = config.get('processing', {})
    enable_image_search = processing_config.get('enable_image_search', True)
    search_delay = processing_config.get('image_search_delay', 2.5)
    max_searches = processing_config.get('max_image_searches_per_receipt', 3)
    min_price = processing_config.get('image_search_min_price', 0.0)

    # Check if we should label items with AI-populated images
    label_ai_images = processing_config.get('label_ai_images', True)
    label_name = processing_config.get('ai_image_label_name', 'Verify Image')

    # Ensure label exists if labeling is enabled
    label_id = None
    if label_ai_images:
        label_id = homebox.ensure_label_exists(
            label_name,
            description="Items with AI-populated images that need manual verification",
            color="#F59E0B"  # Orange color for attention
        )
        if not label_id:
            logger.warning(f"Failed to create/find label '{label_name}', labeling disabled")
            label_ai_images = False

    search_count = 0

    for item_info in created_items:
        item_id = item_info['id']
        item_name = item_info['name']
        item_index = item_info['index']
        item_price = item_info.get('price', 0.0)
        manufacturer = item_info.get('manufacturer')

        # Check if we have a matched image from email
        image = image_matches.get(item_index)

        # If no email image and search is enabled, try DuckDuckGo
        if not image and enable_image_search:
            # Check if we've hit the search limit
            if search_count >= max_searches:
                logger.debug(f"Reached max searches ({max_searches}), skipping '{item_name}'")
                continue

            # Check if item meets minimum price threshold
            if item_price < min_price:
                logger.debug(f"Item price ${item_price:.2f} below threshold ${min_price:.2f}, skipping search for '{item_name}'")
                continue

            # Add delay before search (except for first search)
            if search_count > 0:
                logger.debug(f"Waiting {search_delay}s before next search (rate limit protection)")
                time.sleep(search_delay)

            logger.info(f"No email image for '{item_name}', searching DuckDuckGo... (search {search_count + 1}/{max_searches})")
            try:
                from image_handler import search_product_image

                search_results = search_product_image(item_name, manufacturer, max_results=1)
                search_count += 1

                if search_results:
                    image = search_results[0]
                    logger.info(f"Found image via DuckDuckGo for '{item_name}'")
                else:
                    logger.debug(f"No images found for '{item_name}'")
            except Exception as e:
                logger.error(f"Error searching for '{item_name}': {e}")
                search_count += 1  # Still count failed searches

        # Upload image if we have one
        if image:
            try:
                result = homebox.upload_attachment(
                    item_id=item_id,
                    image_data=image['data'],
                    filename=image.get('filename', f"{item_name[:30]}.jpg"),
                    attachment_type="photo"
                )
                if result:
                    logger.info(f"✓ Uploaded image for: {item_name}")

                    # Add label if enabled
                    if label_ai_images and label_id:
                        if homebox.add_label_to_item(item_id, label_id):
                            logger.debug(f"✓ Added '{label_name}' label to: {item_name}")
                        else:
                            logger.warning(f"Failed to add '{label_name}' label to: {item_name}")
                else:
                    logger.warning(f"Failed to upload image for: {item_name}")
            except Exception as e:
                logger.error(f"Error uploading image for {item_name}: {e}")
        else:
            logger.debug(f"No image available for: {item_name}")


def upload_pdf_to_first_item(created_items, email_data, homebox):
    """
    Upload PDF receipt to the first created item.

    Args:
        created_items: List of created item dicts with 'id' and 'name'
        email_data: Email data dict containing pdf_data and pdf_filename
        homebox: HomeboxClient instance

    Returns:
        str: The ID of the first item, or None if upload failed
    """
    if not created_items:
        return None

    first_item = created_items[0]
    item_id = first_item['id']
    item_name = first_item['name']

    pdf_data = email_data.get('pdf_data')
    pdf_filename = email_data.get('pdf_filename', 'receipt.pdf')

    if not pdf_data:
        return None

    try:
        logger.info(f"Uploading PDF receipt to first item: {item_name} [ID: {item_id}]")
        result = homebox.upload_attachment(
            item_id=item_id,
            image_data=pdf_data,
            filename=pdf_filename,
            attachment_type="attachment"
        )

        if result:
            logger.info(f"✓ Uploaded PDF receipt to: {item_name}")
            return item_id
        else:
            logger.warning(f"Failed to upload PDF to: {item_name}")
            return None

    except Exception as e:
        logger.error(f"Error uploading PDF to {item_name}: {e}")
        return None


def add_pdf_cross_references(created_items, first_item_id, homebox):
    """
    Add cross-reference notes to items 2+ pointing to first item with PDF.

    Args:
        created_items: List of created item dicts with 'id', 'name'
        first_item_id: ID of the first item (which has the PDF attached)
        homebox: HomeboxClient instance
    """
    if len(created_items) <= 1:
        return

    # Get Homebox URL for creating link
    homebox_url = homebox.base_url

    for item_info in created_items[1:]:  # Skip first item
        item_id = item_info['id']
        item_name = item_info['name']

        try:
            # Get current item details
            item_data = homebox.get_item(item_id)
            if not item_data:
                logger.warning(f"Could not fetch item {item_name} for cross-reference update")
                continue

            # Prepare update with cross-reference note
            current_description = item_data.get('description', '')

            # Add cross-reference to description
            cross_ref_note = f"\n\nReceipt PDF attached to: {homebox_url}/item/{first_item_id}"

            # Only add if not already present
            if first_item_id not in current_description:
                updated_description = current_description + cross_ref_note

                if homebox.update_item(
                    item_id,
                    {'description': updated_description},
                    current_entity=item_data
                ):
                    logger.info(f"✓ Added PDF cross-reference to: {item_name}")
                else:
                    logger.warning(f"Failed to add cross-reference to {item_name}")

        except Exception as e:
            logger.error(f"Error adding cross-reference to {item_name}: {e}")


def handle_receipt_result(result, email_data, email_fetcher, config):
    """
    Handle receipt processing result by moving email to appropriate folder

    Args:
        result: Dict with 'status' and other result data from process_receipt()
        email_data: Email data dict with 'uid', 'subject', etc.
        email_fetcher: EmailFetcher instance for moving emails
        config: Application config

    Returns:
        dict: Summary with 'moved_to' folder name if moved, or None
    """
    status = result.get('status')

    if status == 'success':
        # Move to success folder if configured
        move_folder = config['email'].get('move_to_folder_on_success')
        if move_folder:
            email_fetcher.move_to_folder(email_data['uid'], move_folder)
            logger.info(f"✓ Moved to '{move_folder}'")
            return {'moved_to': move_folder}
        else:
            logger.info(f"✓ Successfully processed")
            return {}

    elif status in ('low_confidence', 'partial_write'):
        # Move to manual processing folder
        manual_folder = config['email'].get('move_to_folder_on_low_confidence', 'Receipts/Manual Review')
        if manual_folder:
            email_fetcher.move_to_folder(email_data['uid'], manual_folder)
            if status == 'partial_write':
                logger.warning(
                    "Homebox item was partially written; moved to manual review folder "
                    "'%s' to prevent automatic reprocessing",
                    manual_folder,
                )
            else:
                logger.info(f"⚠ Low confidence - moved to '{manual_folder}'")
            return {'moved_to': manual_folder}
        else:
            logger.info(f"⚠ Low confidence")
            return {}

    elif status == 'consumable':
        # Move to consumables folder
        consumable_folder = config['email'].get('move_to_folder_on_consumable', 'Receipts/Consumables')
        if consumable_folder:
            email_fetcher.move_to_folder(email_data['uid'], consumable_folder)
            logger.info(f"⊝ Consumable items - moved to '{consumable_folder}'")
            return {'moved_to': consumable_folder}
        else:
            logger.info(f"⊝ Consumable items - skipped")
            return {}

    elif status == 'no_items':
        # Move to no items folder
        no_items_folder = config['email'].get('move_to_folder_on_no_items', 'Receipts/No Items')
        if no_items_folder:
            email_fetcher.move_to_folder(email_data['uid'], no_items_folder)
            logger.info(f"○ No line items found - moved to '{no_items_folder}'")
            return {'moved_to': no_items_folder}
        else:
            logger.info(f"○ No line items found")
            return {}

    else:  # failed or unknown status
        logger.error(f"✗ Failed to process (reason: {result.get('reason', 'unknown')})")
        return {}


def save_failed_receipt(email_data, reason, extracted_data=None):
    """Save failed receipt for manual review"""
    failed_dir = Path('data/failed')
    failed_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{reason}.txt"
    
    with open(failed_dir / filename, 'w') as f:
        f.write(f"Reason: {reason}\n")
        f.write(f"Subject: {email_data.get('subject')}\n")
        f.write(f"From: {email_data.get('from')}\n")
        f.write(f"Date: {email_data.get('date')}\n\n")
        f.write("Body:\n")
        f.write(email_data.get('body', ''))
        
        if extracted_data:
            f.write("\n\n--- Extracted Data ---\n")
            f.write(yaml.dump(extracted_data))
    
    logger.info(f"Saved failed receipt to {filename}")


def save_processed_receipt(email_data, receipt_data):
    """Save successfully processed receipt"""
    processed_dir = Path('data/processed')
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    store = receipt_data.get('store', 'unknown').replace(' ', '_')
    filename = f"{timestamp}_{store}.yml"
    
    data = {
        'email': {
            'subject': email_data.get('subject'),
            'from': email_data.get('from'),
            'date': email_data.get('date'),
        },
        'extracted': receipt_data
    }
    
    with open(processed_dir / filename, 'w') as f:
        yaml.dump(data, f)


def main(argv=None):
    """Main application loop"""
    parser = argparse.ArgumentParser(description='Monitor email receipts and create Homebox items.')
    parser.add_argument(
        '--live',
        action='store_true',
        help='Enable IMAP polling, mailbox moves, and Homebox writes'
    )
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('live processing is disabled by default; pass --live to opt in')

    from dotenv import load_dotenv
    from email_fetcher import EmailFetcher
    from receipt_extractor_mlx import ReceiptExtractor
    from homebox_client import HomeboxClient

    load_dotenv()
    logging.getLogger().setLevel(
        getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    )

    logger.info("=" * 60)
    logger.info("Receipt Processor Starting (Ollama-powered)")
    logger.info("=" * 60)
    
    # Create data directories
    for dir_name in ['logs', 'failed', 'processed']:
        Path(f'data/{dir_name}').mkdir(parents=True, exist_ok=True)
    
    # Load configuration
    config = load_config()
    
    # Initialize components
    logger.info("Initializing components...")
    
    try:
        extractor = ReceiptExtractor(config['ai'])
        logger.info("✓ Ollama Receipt Extractor initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Ollama extractor: {e}")
        sys.exit(1)
    
    email_fetcher = EmailFetcher(config['email'], config.get('processing', {}))
    logger.info("✓ Email Fetcher initialized")
    
    homebox = HomeboxClient()
    if homebox.test_connection():
        logger.info("✓ Homebox connection verified")
    else:
        logger.warning("⚠ Homebox connection failed - items won't be added")
    
    check_interval = int(os.getenv('CHECK_INTERVAL', 300))
    
    logger.info("=" * 60)
    logger.info(f"Monitoring email every {check_interval} seconds")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    while True:
        try:
            # Fetch unprocessed receipt emails
            logger.debug("Checking for new receipts...")
            emails = email_fetcher.fetch_receipts(unread_only=False)
            
            if emails:
                logger.info(f"Found {len(emails)} receipt email(s)")
                
                for email_data in emails:
                    result = process_receipt(email_data, extractor, homebox, config)
                    # Handle result and move email to appropriate folder
                    handle_receipt_result(result, email_data, email_fetcher, config)
            else:
                logger.debug("No new receipts found")
            
            # Wait before next check
            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            logger.info("\nShutting down gracefully...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            logger.info("Waiting 60 seconds before retrying...")
            time.sleep(60)


if __name__ == '__main__':
    main()