#!/usr/bin/env python3
"""
Receipt Processor - Main Application (MLX Version)
Monitors email for receipts, extracts data with MLX-LM, and adds to Homebox
"""

import os
import sys
import time
import logging
import yaml
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from email_fetcher import EmailFetcher
from receipt_extractor_mlx import ReceiptExtractor
from homebox_client import HomeboxClient
from image_handler import search_product_image, match_images_to_items

# Load environment variables
load_dotenv()

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


def process_receipt(email_data, extractor, homebox, config):
    """Process a single receipt email"""
    try:
        logger.info(f"Processing email: {email_data['subject']}")

        # Extract receipt data using MLX
        receipt_data = extractor.extract(email_data)

        if not receipt_data:
            logger.warning("Failed to extract receipt data")
            save_failed_receipt(email_data, "extraction_failed")
            return {'status': 'failed', 'reason': 'extraction_failed'}

        # Check confidence level
        confidence = receipt_data.get('confidence', 0)
        min_confidence = config['processing']['min_confidence']

        if confidence < min_confidence:
            logger.warning(f"Low confidence ({confidence:.2f} < {min_confidence})")
            save_failed_receipt(email_data, "low_confidence", receipt_data)
            return {'status': 'low_confidence', 'confidence': confidence}

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
            image_matches = match_images_to_items(email_images, receipt_data.get('items', []))

        # Add items to Homebox
        success_count = 0
        created_items = []  # Track created items for image upload

        for idx, item in enumerate(receipt_data.get('items', [])):
            try:
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
            except Exception as e:
                logger.error(f"Error adding item {item.get('name')}: {e}")

        # Upload images to created items
        if created_items:
            upload_images_to_items(created_items, image_matches, homebox, config)
        
        # Save processed receipt
        if config['processing']['save_processed']:
            save_processed_receipt(email_data, receipt_data)

        logger.info(f"Successfully processed {success_count}/{len(receipt_data['items'])} items")
        return {'status': 'success', 'items_added': success_count}

    except Exception as e:
        logger.error(f"Error processing receipt: {e}", exc_info=True)
        save_failed_receipt(email_data, str(e))
        return {'status': 'failed', 'reason': str(e)}


def map_to_homebox_item(item, receipt_data, config, location_id):
    """Map extracted item data to Homebox item format"""
    category = item.get('category', 'other')
    homebox_category = config['homebox']['category_map'].get(category, 'General')

    # Format notes using template
    notes_template = config['homebox']['notes_template']
    notes = notes_template.format(
        store=receipt_data.get('store', 'Unknown'),
        date=receipt_data.get('order_date', 'Unknown'),
        order_id=receipt_data.get('order_id', 'N/A')
    )

    # Add description from item if available
    if item.get('description'):
        notes = f"{item['description']}\n\n{notes}"

    homebox_item = {
        'name': item['name'],
        'description': notes,
        'quantity': item.get('quantity', 1),
        'locationId': location_id
    }

    # Add purchase info if available (will be sent in update request)
    if item.get('price') and item['price'] > 0:
        homebox_item['purchasePrice'] = float(item['price'])

    if receipt_data.get('store'):
        homebox_item['purchaseFrom'] = receipt_data['store']

    if receipt_data.get('order_date'):
        homebox_item['purchaseTime'] = receipt_data['order_date']

    # Add manufacturer/model info if available in item data
    if item.get('manufacturer'):
        homebox_item['manufacturer'] = item['manufacturer']

    if item.get('model_number'):
        homebox_item['modelNumber'] = item['model_number']

    if item.get('serial_number'):
        homebox_item['serialNumber'] = item['serial_number']

    return homebox_item


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
                else:
                    logger.warning(f"Failed to upload image for: {item_name}")
            except Exception as e:
                logger.error(f"Error uploading image for {item_name}: {e}")
        else:
            logger.debug(f"No image available for: {item_name}")


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


def main():
    """Main application loop"""
    logger.info("=" * 60)
    logger.info("Receipt Processor Starting (MLX-powered)")
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
        logger.info("✓ MLX Receipt Extractor initialized")
    except Exception as e:
        logger.error(f"Failed to initialize MLX: {e}")
        sys.exit(1)
    
    email_fetcher = EmailFetcher(config['email'])
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
            emails = email_fetcher.fetch_receipts()
            
            if emails:
                logger.info(f"Found {len(emails)} receipt email(s)")
                
                for email_data in emails:
                    result = process_receipt(email_data, extractor, homebox, config)

                    # Handle result based on status
                    if result['status'] == 'success':
                        # Move to success folder if configured
                        move_folder = config['email'].get('move_to_folder_on_success')
                        if move_folder:
                            email_fetcher.move_to_folder(email_data['uid'], move_folder)
                    elif result['status'] == 'low_confidence':
                        # Move to manual processing folder
                        manual_folder = config['email'].get('move_to_folder_on_low_confidence', 'Receipts (process manually)')
                        if manual_folder:
                            logger.info(f"Moving low confidence email to '{manual_folder}'")
                            email_fetcher.move_to_folder(email_data['uid'], manual_folder)
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