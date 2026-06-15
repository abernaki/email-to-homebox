#!/usr/bin/env python3
"""
Test HTML extraction for receipts with embedded <pre> tags.

This tests extraction from HTML emails that contain receipt data within
<pre> (preformatted) tags, which is common for receipts with:
- ASCII-formatted tables
- Monospace-formatted line items
- Fixed-width receipt layouts

The extractor should prioritize <pre> tag content over other HTML elements.
"""

import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text_from_html(html):
    """
    Smart HTML to text extraction that prioritizes receipt content.

    Strategy:
    1. Look for <pre> tags (often contain formatted receipt text)
    2. Remove script, style, and navigation elements
    3. Extract remaining text with proper formatting

    Args:
        html: Raw HTML string

    Returns:
        Extracted text string
    """
    try:
        soup = BeautifulSoup(html, 'lxml')

        # First, check for <pre> tags which often contain receipt text
        pre_tags = soup.find_all('pre')
        if pre_tags:
            logger.debug(f"Found {len(pre_tags)} <pre> tag(s) - prioritizing this content")
            # Combine all pre tag content at the beginning
            pre_content = '\n\n--- RECEIPT DATA ---\n'.join(
                pre.get_text(separator='\n', strip=True) for pre in pre_tags
            )
        else:
            pre_content = ""

        # Remove unwanted elements that add noise
        for tag in soup(['script', 'style', 'meta', 'link', 'noscript', 'head']):
            tag.decompose()

        # Get the main text content
        main_text = soup.get_text(separator='\n', strip=True)

        # If we found pre tags, put them first
        if pre_content:
            return f"{pre_content}\n\n--- EMAIL BODY ---\n{main_text}"
        else:
            return main_text

    except Exception as e:
        logger.warning(f"Error extracting HTML: {e}")
        # Fallback to simple extraction
        soup = BeautifulSoup(html, 'lxml')
        return soup.get_text(separator='\n', strip=True)

# Sample HTML email with <pre> tag containing receipt
# This pattern is common in receipts from electronics/retail stores
sample_html = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial; }
        .header { color: blue; }
    </style>
    <script>
        console.log("tracking code");
    </script>
</head>
<body>
    <h1>Your Receipt</h1>
    <p>Thank you for shopping</p>

    <pre style="border:1px solid #000000;">*********** START RECEIPT ***********

         Electronics Store #1531
                52 E 14th ST
             NEW YORK, NY 10003

4373913    800276                 71.99
  COLOR INDOOR LIGHT STRIP 2M
    89.99  Was Price
    18.00- Sale Discount
  Sales Tax              6.39
                              ----------
                      Subtotal    71.99
                     Sales Tax     6.39
                              ==========
                         Total    78.38

************ END RECEIPT ************
</pre>

    <div>
        <a href="#">Sign up for deals</a>
        <a href="#">Weekly ads</a>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    print("Testing HTML extraction...")
    print("=" * 60)

    extracted = extract_text_from_html(sample_html)

    print(extracted)
    print("=" * 60)

    # Check if the receipt content is prioritized
    if "--- EMAIL BODY ---" in extracted:
        print("✓ Pre tag content detected and prioritized")
    else:
        print("✗ Pre tag content NOT prioritized")

    if "COLOR INDOOR LIGHT STRIP 2M" in extracted:
        print("✓ Product name extracted")
    else:
        print("✗ Product name NOT found")

    if "71.99" in extracted:
        print("✓ Price extracted")
    else:
        print("✗ Price NOT found")

    # Check that receipt appears at the beginning
    receipt_start = extracted.find("START RECEIPT")
    if receipt_start >= 0 and receipt_start < 50:
        print("✓ Receipt data appears early in output (not buried in HTML)")
    else:
        print(f"✗ Receipt data appears at position {receipt_start} (should be near 0)")
