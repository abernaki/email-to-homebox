#!/usr/bin/env python3
"""
One-time receipt processor - processes all emails in Receipts folder once
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from email_fetcher import EmailFetcher
from receipt_extractor_mlx import ReceiptExtractor
from homebox_client import HomeboxClient
from app import process_receipt, load_config

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set all loggers to DEBUG
logging.getLogger('homebox_client').setLevel(logging.DEBUG)
logging.getLogger('app').setLevel(logging.DEBUG)

# Load environment
load_dotenv()


def main():
    """Run one-time processing of receipts"""
    logger.info("=" * 60)
    logger.info("One-Time Receipt Processor")
    logger.info("=" * 60)

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

    logger.info("=" * 60)

    # Fetch all emails (not just unread)
    logger.info("Fetching emails from 'Receipts' folder...")
    emails = email_fetcher.fetch_receipts(unread_only=False)

    if not emails:
        logger.info("No emails found in Receipts folder")
        return

    logger.info(f"Found {len(emails)} email(s) to process\n")

    # Process each email
    success_count = 0
    low_conf_count = 0
    consumable_count = 0
    failed_count = 0

    for i, email_data in enumerate(emails, 1):
        logger.info(f"[{i}/{len(emails)}] Processing: {email_data.get('subject', 'N/A')}")

        result = process_receipt(email_data, extractor, homebox, config)

        # Handle result based on status
        if result['status'] == 'success':
            success_count += 1
            # Move to success folder if configured
            move_folder = config['email'].get('move_to_folder_on_success')
            if move_folder:
                # email_fetcher.move_to_folder(email_data['uid'], move_folder)
                logger.info(f"✓ Moved to '{move_folder}'\n")
            else:
                logger.info(f"✓ Successfully processed\n")
        elif result['status'] == 'low_confidence':
            low_conf_count += 1
            # Move to manual processing folder
            manual_folder = config['email'].get('move_to_folder_on_low_confidence', 'Receipts (process manually)')
            if manual_folder:
                email_fetcher.move_to_folder(email_data['uid'], manual_folder)
                logger.info(f"⚠ Low confidence - moved to '{manual_folder}'\n")
            else:
                logger.info(f"⚠ Low confidence\n")
        elif result['status'] == 'consumable':
            consumable_count += 1
            # Move to consumables folder
            consumable_folder = config['email'].get('move_to_folder_on_consumable', 'Receipts/Consumables')
            if consumable_folder:
                email_fetcher.move_to_folder(email_data['uid'], consumable_folder)
                logger.info(f"⊝ Consumable items - moved to '{consumable_folder}'\n")
            else:
                logger.info(f"⊝ Consumable items - skipped\n")
        else:
            failed_count += 1
            logger.error(f"✗ Failed to process\n")

    # Summary
    logger.info("=" * 60)
    logger.info("Processing Complete!")
    logger.info("=" * 60)
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Low confidence (manual): {low_conf_count}")
    logger.info(f"Consumables (skipped): {consumable_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total: {len(emails)}")


if __name__ == '__main__':
    main()
