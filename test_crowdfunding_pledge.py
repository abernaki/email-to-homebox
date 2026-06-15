#!/usr/bin/env python3
"""
Test extraction of crowdfunding/pledge receipts.

This tests extraction from crowdfunding platforms where "items" are represented
as pledge tiers or rewards rather than traditional products. Common with:
- Kickstarter pledges
- Indiegogo contributions
- Patreon tiers
- GoFundMe donations

These receipts often have:
- "Your pledge" or "Details" sections instead of "Items"
- Reward tiers as products
- Add-on items marked with "+" prefix
- Sometimes 100% discount codes (still valid items at original price)
"""

import sys
import logging
from dotenv import load_dotenv

sys.path.insert(0, 'src')

from receipt_extractor_mlx import ReceiptExtractor
from app import load_config

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

def main():
    config = load_config()
    extractor = ReceiptExtractor(config['ai'])

    # Read from a saved crowdfunding receipt (if available)
    # Otherwise, you can paste sample crowdfunding email body here
    try:
        with open('data/failed/20251013_232218_extraction_failed.txt', 'r') as f:
            content = f.read()

        # Extract the body
        body_start = content.find('Body:\n') + 6
        body = content[body_start:]

        # Extract subject, from, date
        lines = content.split('\n')
        subject = lines[1].replace('Subject: ', '')
        from_addr = lines[2].replace('From: ', '')
        date = lines[3].replace('Date: ', '')

        email_data = {
            'subject': subject,
            'from': from_addr,
            'date': date,
            'body': body
        }
    except FileNotFoundError:
        # Fallback to sample data if saved file doesn't exist
        print("Note: Using sample crowdfunding data (saved file not found)")
        email_data = {
            'subject': "Thanks for backing our project!",
            'from': "Crowdfunding Platform <noreply@crowdfunding.com>",
            'date': 'Wed, 13 Oct 2025 23:22:18 +0000',
            'body': """
Thank you for your pledge!

Your pledge:
$125 - Early Bird Special Tier
Includes the product plus exclusive backer rewards

Details:
+ Add-on: Extended Warranty ($25)
+ Add-on: Premium Case ($15)

Original total: $165
Discount code EARLYBIRD: -$40 (100% off add-ons!)
Final total: $125

Your contribution helps make this project a reality!
"""
        }

    print(f"Testing: {email_data['subject']}")
    print("="*60)
    print("Test type: Crowdfunding pledge receipt")
    print("Expected: Extract pledge tier and add-ons as items")
    print("="*60)

    # Patch to see LLM response
    original_parse = extractor._parse_response
    def debug_parse(response):
        with open('/tmp/crowdfunding_pledge_llm_response.txt', 'w') as f:
            f.write(response)
        print(f"\nLLM response saved to /tmp/crowdfunding_pledge_llm_response.txt")
        return original_parse(response)

    extractor._parse_response = debug_parse

    result = extractor.extract(email_data)

    print("\nExtraction result:")
    import json
    print(json.dumps(result, indent=2))

    # Validate expected behavior
    print("\n" + "="*60)
    if result.get('items'):
        print(f"✓ Found {len(result['items'])} item(s)")
        for item in result['items']:
            print(f"  - {item.get('name')}: ${item.get('price', 0)}")
    else:
        print("✗ Expected items to be extracted from pledge")

if __name__ == '__main__':
    main()
