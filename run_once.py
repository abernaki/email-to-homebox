#!/usr/bin/env python3
"""
One-time receipt processor - processes all emails in Receipts folder once
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

logger = logging.getLogger(__name__)


def main(argv=None):
    """Run one-time processing of receipts"""
    parser = argparse.ArgumentParser(description='Process receipts from the configured IMAP mailbox.')
    parser.add_argument(
        '--live',
        action='store_true',
        help='Enable IMAP reads, mailbox moves, and Homebox writes'
    )
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('live processing is disabled by default; pass --live to opt in')

    from dotenv import load_dotenv

    load_dotenv()
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logging.getLogger('homebox_client').setLevel(level)
    logging.getLogger('app').setLevel(level)
    logging.getLogger('email_fetcher').setLevel(level)
    logging.getLogger('receipt_extractor_mlx').setLevel(level)

    from email_fetcher import EmailFetcher
    from receipt_extractor_mlx import ReceiptExtractor
    from homebox_client import HomeboxClient
    from app import process_receipt, load_config, handle_receipt_result

    logger.info("=" * 60)
    logger.info("One-Time Receipt Processor")
    logger.info("=" * 60)

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
    no_items_count = 0
    failed_count = 0

    for i, email_data in enumerate(emails, 1):
        logger.info(f"[{i}/{len(emails)}] Processing: {email_data.get('subject', 'N/A')}")

        result = process_receipt(email_data, extractor, homebox, config)

        # Update counters based on status
        status = result['status']
        if status == 'success':
            success_count += 1
        elif status == 'low_confidence':
            low_conf_count += 1
        elif status == 'consumable':
            consumable_count += 1
        elif status == 'no_items':
            no_items_count += 1
        else:
            failed_count += 1

        # Handle result (move email to appropriate folder)
        handle_receipt_result(result, email_data, email_fetcher, config)
        logger.info("")  # Add blank line for readability

    # Summary
    logger.info("=" * 60)
    logger.info("Processing Complete!")
    logger.info("=" * 60)
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Low confidence (manual): {low_conf_count}")
    logger.info(f"Consumables (skipped): {consumable_count}")
    logger.info(f"No items found: {no_items_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total: {len(emails)}")


if __name__ == '__main__':
    main()
