#!/usr/bin/env python3
"""
Test image extraction from receipt emails
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

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
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


def main():
    """Test image extraction from emails"""
    logger.info("=" * 60)
    logger.info("Image Extraction Test")
    logger.info("=" * 60)

    # Load configuration
    config = load_config()

    # Initialize email fetcher
    email_fetcher = EmailFetcher(config['email'], config.get('processing', {}))
    logger.info("✓ Email Fetcher initialized")

    # Fetch emails (not just unread)
    logger.info("\nFetching emails from 'Receipts' folder...")
    emails = email_fetcher.fetch_receipts(unread_only=False)

    if not emails:
        logger.info("No emails found in Receipts folder")
        return

    logger.info(f"Found {len(emails)} email(s)\n")

    # Test first email
    email_data = emails[0]

    logger.info("=" * 60)
    logger.info(f"Subject: {email_data.get('subject', 'N/A')}")
    logger.info(f"From: {email_data.get('from', 'N/A')}")
    logger.info(f"Date: {email_data.get('date', 'N/A')}")
    logger.info("=" * 60)

    images = email_data.get('images', [])

    if images:
        logger.info(f"\n✓ Found {len(images)} product image(s):\n")

        for i, img in enumerate(images, 1):
            logger.info(f"Image {i}:")
            logger.info(f"  Source: {img['source']}")
            logger.info(f"  Dimensions: {img['width']}x{img['height']}")
            logger.info(f"  Size: {img['size']:,} bytes")
            logger.info(f"  Filename: {img['filename']}")
            if img['url']:
                logger.info(f"  URL: {img['url'][:100]}...")
            logger.info("")

        # Save first image to test file
        test_dir = Path('data/test_images')
        test_dir.mkdir(parents=True, exist_ok=True)

        test_file = test_dir / f"test_image_1.jpg"
        with open(test_file, 'wb') as f:
            f.write(images[0]['data'])

        logger.info(f"✓ Saved first image to: {test_file}")
        logger.info(f"  You can open it to verify it's a product image")
    else:
        logger.info("\n⚠ No images found in this email")
        logger.info("  This might be expected if the email has:")
        logger.info("  - Only small images (logos, icons)")
        logger.info("  - Only tracking pixels")
        logger.info("  - Text-only content")
        logger.info("\nTry with a different email or check the debug logs above")

    logger.info("\n" + "=" * 60)
    logger.info("Test complete!")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
