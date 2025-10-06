#!/usr/bin/env python3
"""
Test script to verify MLX extraction works
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from receipt_extractor_mlx import ReceiptExtractor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Sample receipt email for testing
SAMPLE_RECEIPT = """
Subject: Your Amazon.com order #123-4567890-1234567
From: auto-confirm@amazon.com
Date: 2024-03-15

Hello,

Thank you for your order. Here are the details:

Order #123-4567890-1234567
Order Date: March 15, 2024

Items Ordered:
- Logitech MX Master 3S Wireless Mouse - Qty: 1 - $99.99
- USB-C Cable 6ft (2 pack) - Qty: 1 - $15.99
- Laptop Stand Aluminum - Qty: 1 - $39.99

Subtotal: $155.97
Tax: $12.48
Total: $168.45

Thank you for shopping with Amazon!
"""


def load_config():
    """Load config"""
    with open('config/config.yml', 'r') as f:
        return yaml.safe_load(f)


def test_extraction():
    """Test MLX extraction with sample receipt"""
    
    logger.info("=" * 60)
    logger.info("Receipt Extraction Test")
    logger.info("=" * 60)
    
    # Load config
    try:
        config = load_config()
        ai_config = config['ai']
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        logger.info("Make sure config/config.yml exists")
        return False
    
    # Initialize extractor
    logger.info("Initializing MLX extractor...")
    logger.info("This will download the model on first run (~4-5GB)")
    logger.info("Please be patient, this may take 5-10 minutes...\n")
    
    try:
        extractor = ReceiptExtractor(ai_config)
        logger.info("✓ MLX extractor initialized\n")
    except Exception as e:
        logger.error(f"Failed to initialize extractor: {e}")
        return False
    
    # Prepare test email data
    email_data = {
        'subject': 'Your Amazon.com order #123-4567890-1234567',
        'from': 'auto-confirm@amazon.com',
        'date': '2024-03-15',
        'body': SAMPLE_RECEIPT
    }
    
    # Extract data
    logger.info("Extracting receipt data from sample email...\n")
    
    try:
        result = extractor.extract(email_data)
        
        if not result:
            logger.error("✗ Extraction failed - no data returned")
            return False
        
        # Display results
        logger.info("=" * 60)
        logger.info("✓ EXTRACTION SUCCESSFUL!")
        logger.info("=" * 60)
        logger.info("")
        logger.info(f"Store: {result.get('store', 'N/A')}")
        logger.info(f"Order Date: {result.get('order_date', 'N/A')}")
        logger.info(f"Order ID: {result.get('order_id', 'N/A')}")
        logger.info(f"Total: ${result.get('total', 0):.2f}")
        logger.info(f"Confidence: {result.get('confidence', 0):.2%}")
        logger.info("")
        logger.info("Items:")
        logger.info("-" * 60)
        
        for i, item in enumerate(result.get('items', []), 1):
            logger.info(f"{i}. {item.get('name', 'Unknown')}")
            logger.info(f"   Price: ${item.get('price', 0):.2f}")
            logger.info(f"   Quantity: {item.get('quantity', 1)}")
            logger.info(f"   Category: {item.get('category', 'other')}")
            logger.info("")
        
        logger.info("=" * 60)
        logger.info("Test completed successfully!")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Edit .env with your email and Homebox credentials")
        logger.info("2. Run: python src/app.py")
        logger.info("")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Extraction failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = test_extraction()
    sys.exit(0 if success else 1)