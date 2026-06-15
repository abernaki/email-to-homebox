#!/usr/bin/env python3
"""
Test extraction of receipts with NO line items.

This tests the case where a receipt shows a total amount paid but does not
list individual product line items. Common with:
- Square "Custom Amount" transactions
- Simple payment confirmations
- Cash transactions without itemization

The extractor should return an empty items array and low confidence.
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

    # Example: Square receipt with "Custom Amount" - no product details
    email_data = {
        'subject': "Receipt for $30.90 from Local Store",
        'from': "Local Store via Square <receipts@messaging.squareup.com>",
        'date': 'Sat, 19 Nov 2022 17:04:38 +0000',
        'body': """Receipt for $30.90 at Local Store on Nov 19 2022 at 11:58 AM.
Square automatically sends receipts to the email address you used at any Square seller.
Learn more
Local Store
Let Local Store know how your experience was
$
30
.
90
Custom Amount × 1
$30.00
Purchase Subtotal
$30.00
Credit Card Fee (3%)
$0.90
Total
$30.90
Local Store
P.O. Box 230878
NEW YORK, NY 10023
Visa 4864 (Contactless)
Nov 19 2022 at 11:58 AM
#VGGI
Auth code: 05565D"""
    }

    print(f"Testing: {email_data['subject']}")
    print("="*60)
    print("Test type: No line items receipt (Custom Amount)")
    print("Expected: Empty items array, confidence < 0.7")
    print("="*60)

    # Patch to see LLM response
    original_parse = extractor._parse_response
    def debug_parse(response):
        with open('/tmp/no_line_items_llm_response.txt', 'w') as f:
            f.write(response)
        print(f"\nLLM response saved to /tmp/no_line_items_llm_response.txt")
        return original_parse(response)

    extractor._parse_response = debug_parse

    result = extractor.extract(email_data)

    print("\nExtraction result:")
    print(result)

    # Validate expected behavior
    print("\n" + "="*60)
    if result.get('items') == []:
        print("✓ Correctly returned empty items array")
    else:
        print("✗ Expected empty items array, got:", result.get('items'))

    if result.get('confidence', 1.0) < 0.7:
        print("✓ Confidence appropriately low")
    else:
        print("✗ Expected low confidence, got:", result.get('confidence'))

if __name__ == '__main__':
    main()
