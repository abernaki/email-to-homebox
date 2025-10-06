#!/usr/bin/env python3
"""
Test script to verify email fetching works
"""

import os
import sys
import yaml
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from email_fetcher import EmailFetcher
from receipt_extractor_mlx import ReceiptExtractor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()


def load_config():
    """Load config"""
    with open('config/config.yml', 'r') as f:
        return yaml.safe_load(f)


def test_email_and_extraction():
    """Test email fetching and extraction"""

    logger.info("=" * 60)
    logger.info("Email Fetching & Extraction Test")
    logger.info("=" * 60)

    # Load config
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return False

    # Initialize email fetcher
    logger.info("\nInitializing email fetcher...")
    try:
        email_fetcher = EmailFetcher(config['email'])
        logger.info("✓ Email fetcher initialized\n")
    except Exception as e:
        logger.error(f"Failed to initialize email fetcher: {e}")
        return False

    # Initialize MLX extractor
    logger.info("Initializing MLX extractor...")
    logger.info("This will download the model on first run (~4-5GB)")
    logger.info("Please be patient, this may take 5-10 minutes...\n")

    try:
        extractor = ReceiptExtractor(config['ai'])
        logger.info("✓ MLX extractor initialized\n")
    except Exception as e:
        logger.error(f"Failed to initialize extractor: {e}")
        return False

    # Fetch receipt emails
    logger.info("Fetching receipt emails from 'Receipts' folder...")
    try:
        emails = email_fetcher.fetch_receipts(unread_only=False)

        if not emails:
            logger.warning("✗ No receipt emails found in 'Receipts' folder")
            logger.info("\nMake sure you have:")
            logger.info("1. Created a 'Receipts' label/folder in Gmail")
            logger.info("2. Moved some receipt emails to that folder")
            return False

        logger.info(f"✓ Found {len(emails)} receipt email(s)\n")

        # Process each email
        for i, email_data in enumerate(emails, 1):
            logger.info("=" * 60)
            logger.info(f"Email {i}/{len(emails)}")
            logger.info("=" * 60)
            logger.info(f"Subject: {email_data.get('subject', 'N/A')}")
            logger.info(f"From: {email_data.get('from', 'N/A')}")
            logger.info(f"Date: {email_data.get('date', 'N/A')}")
            logger.info("")

            # Extract data
            logger.info("Extracting receipt data...")
            try:
                result = extractor.extract(email_data)

                if result:
                    logger.info("✓ Extraction successful!\n")

                    # Show confidence reasoning if available
                    if '_confidence_reasons' in result:
                        logger.info("Confidence Analysis:")
                        for reason in result['_confidence_reasons']:
                            logger.info(f"  • {reason}")
                        logger.info("")

                    logger.info("Extracted JSON:")
                    logger.info("-" * 60)
                    # Remove internal fields before displaying
                    display_result = {k: v for k, v in result.items() if not k.startswith('_')}
                    print(json.dumps(display_result, indent=2))
                    logger.info("-" * 60)
                else:
                    logger.warning("✗ Extraction failed - no data returned")

                logger.info("")

            except Exception as e:
                logger.error(f"✗ Extraction error: {e}", exc_info=True)

            # Only process first email for testing
            if i == 3:
                logger.info("\n(Processing only first email for testing)")
                break

        logger.info("=" * 60)
        logger.info("Test completed!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"Error fetching emails: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = test_email_and_extraction()
    sys.exit(0 if success else 1)
