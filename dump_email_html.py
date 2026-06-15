#!/usr/bin/env python3
"""Dump raw HTML from a specific email for inspection"""

import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, 'src')

from email_fetcher import EmailFetcher
from app import load_config

load_dotenv()

def main():
    if len(sys.argv) < 2:
        print("Usage: python dump_email_html.py <search_term>")
        print("Example: python dump_email_html.py 'Wayfair'")
        sys.exit(1)

    search_term = sys.argv[1]

    config = load_config()
    fetcher = EmailFetcher(config['email'], config.get('processing', {}))

    # Connect to email
    fetcher.connect()

    # Search in Receipts folder for the term
    fetcher.client.select_folder('Receipts')
    messages = fetcher.client.search(['SUBJECT', search_term])

    if not messages:
        print(f"No emails found with subject containing '{search_term}'")
        fetcher.disconnect()
        sys.exit(1)

    # Get the first matching email
    uid = messages[0]
    print(f"Found email UID: {uid}")

    # Fetch the full email
    response = fetcher.client.fetch([uid], ['RFC822'])
    email_message = fetcher._parse_email_message(response[uid][b'RFC822'])

    # Find HTML parts
    html_parts = []
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == 'text/html':
                try:
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    html_parts.append(html_content)
                except:
                    pass
    else:
        if email_message.get_content_type() == 'text/html':
            html_content = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            html_parts.append(html_content)

    if not html_parts:
        print("No HTML parts found in email")
        fetcher.disconnect()
        sys.exit(1)

    # Save to file
    output_file = f'/tmp/{search_term.lower().replace(" ", "_")}_email.html'
    with open(output_file, 'w') as f:
        for i, html in enumerate(html_parts):
            if i > 0:
                f.write(f"\n\n<!-- ========== HTML PART {i+1} ========== -->\n\n")
            f.write(html)

    print(f"HTML saved to: {output_file}")
    print(f"Total HTML parts: {len(html_parts)}")
    print(f"Total size: {sum(len(h) for h in html_parts)} bytes")

    fetcher.disconnect()

if __name__ == '__main__':
    main()
