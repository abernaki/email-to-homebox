"""
Email Fetcher - Connects to email and retrieves receipt emails
"""

import os
import re
import logging
import email
import requests
import pdfplumber
from io import BytesIO
from email.header import decode_header
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from PIL import Image
from image_handler import should_skip_image_by_filename

logger = logging.getLogger(__name__)


class EmailFetcher:
    """Fetches receipt emails from IMAP server"""
    
    def __init__(self, config):
        self.config = config
        self.host = os.getenv('EMAIL_IMAP_HOST')
        self.port = int(os.getenv('EMAIL_IMAP_PORT', 993))
        self.username = os.getenv('EMAIL_ADDRESS')
        self.password = os.getenv('EMAIL_PASSWORD')
        self.client = None
        
    def connect(self):
        """Connect to IMAP server"""
        try:
            self.client = IMAPClient(self.host, port=self.port, use_uid=True, ssl=True)
            self.client.login(self.username, self.password)
            logger.info(f"Connected to {self.host}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to email: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from IMAP server"""
        if self.client:
            try:
                self.client.logout()
            except:
                pass
    
    def fetch_receipts(self, unread_only=True):
        """Fetch receipt emails"""
        if not self.connect():
            return []

        try:
            receipts = []

            for folder in self.config.get('folders', ['INBOX']):
                try:
                    self.client.select_folder(folder)
                    logger.debug(f"Checking folder: {folder}")

                    # Search for messages
                    if unread_only:
                        messages = self.client.search(['UNSEEN'])
                    else:
                        messages = self.client.search(['ALL'])
                    
                    if not messages:
                        continue
                    
                    # Fetch email data
                    for uid in messages:
                        try:
                            email_data = self._fetch_email(uid)
                            
                            if email_data: #and self._is_receipt(email_data):
                                email_data['uid'] = uid
                                email_data['folder'] = folder
                                receipts.append(email_data)
                        except Exception as e:
                            logger.error(f"Error fetching email {uid}: {e}")
                            continue
                
                except Exception as e:
                    logger.error(f"Error processing folder {folder}: {e}")
                    continue
            
            return receipts
            
        finally:
            self.disconnect()
    
    def _fetch_email(self, uid):
        """Fetch and parse a single email"""
        try:
            # Fetch email data
            response = self.client.fetch([uid], ['RFC822'])
            email_message = email.message_from_bytes(response[uid][b'RFC822'])

            # Extract basic info
            subject = self._decode_header(email_message.get('Subject', ''))
            from_addr = self._decode_header(email_message.get('From', ''))
            date = email_message.get('Date', '')

            # Extract body
            body = self._extract_body(email_message)

            # Extract images
            images = self._extract_images(email_message)

            # Extract PDF attachments
            pdf_data = self._extract_pdf_attachments(email_message)

            email_dict = {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body,
                'images': images
            }

            # Add PDF data if found
            if pdf_data:
                email_dict['pdf_data'] = pdf_data['pdf_data']
                email_dict['pdf_text'] = pdf_data['pdf_text']
                email_dict['pdf_filename'] = pdf_data['pdf_filename']

            return email_dict
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            return None
    
    def _decode_header(self, header):
        """Decode email header"""
        if not header:
            return ''
        
        decoded_parts = decode_header(header)
        result = []
        
        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                try:
                    result.append(content.decode(encoding or 'utf-8'))
                except:
                    result.append(content.decode('utf-8', errors='ignore'))
            else:
                result.append(str(content))
        
        return ''.join(result)
    
    def _extract_body(self, email_message):
        """Extract email body (text and HTML)"""
        plain_body = ''
        html_body = ''

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()

                if content_type == 'text/plain' and not plain_body:
                    try:
                        plain_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        pass
                elif content_type == 'text/html' and not html_body:
                    try:
                        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        # Convert HTML to text
                        soup = BeautifulSoup(html, 'lxml')
                        html_body = soup.get_text(separator='\n', strip=True)
                    except:
                        pass
        else:
            try:
                plain_body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                pass

        # Prefer HTML if plain text is too short/minimal (less than 1000 chars)
        # This handles cases like Best Buy where plain text is just a link
        if html_body and (not plain_body or len(plain_body) < 1000):
            logger.debug(f"Using HTML body (plain text too short: {len(plain_body)} chars)")
            return html_body

        # Otherwise use plain text (more readable for LLM)
        return plain_body if plain_body else html_body

    def _extract_images(self, email_message):
        """Extract and download product images from email"""
        images = []
        html_content = None

        # First pass: collect image attachments and HTML content
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()

                # Get HTML content for parsing img tags
                if content_type == 'text/html' and html_content is None:
                    try:
                        html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        pass

                # Get image attachments
                if content_type.startswith('image/'):
                    try:
                        image_data = part.get_payload(decode=True)
                        if image_data and len(image_data) > 10240:  # > 10KB
                            filename = part.get_filename() or 'attachment.jpg'
                            images.append({
                                'data': image_data,
                                'source': 'attachment',
                                'filename': filename,
                                'url': None
                            })
                            logger.debug(f"Found image attachment: {filename} ({len(image_data)} bytes)")
                    except Exception as e:
                        logger.debug(f"Error extracting image attachment: {e}")

        # Second pass: parse HTML for linked images
        if html_content:
            try:
                soup = BeautifulSoup(html_content, 'lxml')
                img_tags = soup.find_all('img')

                for img in img_tags:
                    src = img.get('src')
                    if not src or not src.startswith('http'):
                        continue

                    # Filter by URL patterns - exclude common non-product images
                    if self._should_skip_image_url(src):
                        logger.debug(f"Skipping image URL (pattern filter): {src[:100]}")
                        continue

                    # Download image
                    try:
                        logger.debug(f"Downloading image from: {src[:100]}")
                        response = requests.get(src, timeout=10, headers={
                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                        })

                        if response.status_code == 200 and len(response.content) > 10240:  # > 10KB
                            images.append({
                                'data': response.content,
                                'source': 'html_link',
                                'filename': src.split('/')[-1].split('?')[0] or 'linked.jpg',
                                'url': src
                            })
                            logger.debug(f"Downloaded image: {len(response.content)} bytes")
                    except Exception as e:
                        logger.debug(f"Failed to download image from {src[:100]}: {e}")
            except Exception as e:
                logger.debug(f"Error parsing HTML for images: {e}")

        # Sort images: prioritize HTML-linked images over attachments
        # Web images (html_link) are more likely to be product photos
        # Attachments are often logos or tracking pixels
        images.sort(key=lambda x: 0 if x['source'] == 'html_link' else 1)

        # Third pass: validate and filter images by dimensions
        filtered_images = []
        for img_data in images:
            try:
                image = Image.open(BytesIO(img_data['data']))
                width, height = image.size

                # Filter by size: 100x100 < size <= 4000x4000
                # Allow up to 4000px for high-quality product photos
                if 100 < width <= 4000 and 100 < height <= 4000:
                    img_data['width'] = width
                    img_data['height'] = height
                    img_data['size'] = len(img_data['data'])

                    # Filter by filename patterns (logos, icons, etc.)
                    filename = img_data.get('filename', '')
                    if should_skip_image_by_filename(filename):
                        logger.debug(f"Filtered out image by filename: {filename}")
                        continue

                    filtered_images.append(img_data)
                    logger.debug(f"Validated image: {width}x{height}, {img_data['source']}")
                else:
                    logger.debug(f"Filtered out image by size: {width}x{height}")
            except Exception as e:
                logger.debug(f"Error validating image: {e}")

        # Keep images in order found - first image is usually the product image
        # (not sorting by size, as that can prioritize wrong images)

        logger.info(f"Extracted {len(filtered_images)} product images from email")
        return filtered_images

    def _should_skip_image_url(self, url):
        """Check if image URL should be skipped based on patterns"""
        url_lower = url.lower()

        # Skip tracking pixels, logos, icons, buttons
        skip_patterns = [
            '/logo/', '/icon/', '/button/', '/tracking/', '/pixel/',
            '/badge/', '/banner/', '/footer/', '/header/', '/spacer/',
            'tracking', 'analytics', '1x1', 'transparent.gif'
        ]

        for pattern in skip_patterns:
            if pattern in url_lower:
                return True

        # Prefer URLs with product/item patterns
        include_patterns = [
            '/product/', '/item/', '/images/i/',  # Amazon: images-amazon.com/images/I/
            '/media/', '/catalog/', '/goods/', '/merchandise/'
        ]

        # If URL has product patterns, definitely keep it
        for pattern in include_patterns:
            if pattern in url_lower:
                return False

        # Otherwise, don't skip (neutral URLs)
        return False

    def _extract_pdf_attachments(self, email_message):
        """
        Extract PDF attachments and extract text from them.

        Returns:
            dict with keys: pdf_data (bytes), pdf_text (str), pdf_filename (str)
            or None if no PDF found
        """
        if not email_message.is_multipart():
            return None

        for part in email_message.walk():
            content_type = part.get_content_type()

            # Look for PDF attachments
            if content_type == 'application/pdf':
                try:
                    pdf_data = part.get_payload(decode=True)
                    filename = part.get_filename() or 'receipt.pdf'

                    if not pdf_data:
                        continue

                    logger.info(f"Found PDF attachment: {filename} ({len(pdf_data)} bytes)")

                    # Extract text from PDF
                    try:
                        pdf_text = ""
                        with pdfplumber.open(BytesIO(pdf_data)) as pdf:
                            for page_num, page in enumerate(pdf.pages, 1):
                                text = page.extract_text()
                                if text:
                                    pdf_text += f"\n--- Page {page_num} ---\n{text}\n"

                        if pdf_text.strip():
                            logger.info(f"Extracted {len(pdf_text)} characters from PDF")
                            return {
                                'pdf_data': pdf_data,
                                'pdf_text': pdf_text,
                                'pdf_filename': filename
                            }
                        else:
                            logger.warning(f"PDF {filename} has no extractable text")
                            return None

                    except Exception as e:
                        logger.error(f"Failed to extract text from PDF {filename}: {e}")
                        return None  # Treat as extraction failure

                except Exception as e:
                    logger.error(f"Error processing PDF attachment: {e}")
                    return None

        return None  # No PDF found

    def _is_receipt(self, email_data):
        """Check if email is likely a receipt"""
        subject = email_data.get('subject', '').lower()
        from_addr = email_data.get('from', '').lower()
        
        # Check subject patterns
        for pattern in self.config.get('subject_patterns', []):
            if re.search(pattern, subject, re.IGNORECASE):
                logger.debug(f"Receipt detected by subject pattern: {pattern}")
                return True
        
        # Check sender domains
        for domain in self.config.get('sender_domains', []):
            if domain.lower() in from_addr:
                logger.debug(f"Receipt detected by sender domain: {domain}")
                return True
        
        return False
    
    def mark_as_read(self, uid):
        """Mark an email as read"""
        try:
            if not self.connect():
                return False

            self.client.add_flags([uid], ['\\Seen'])
            logger.debug(f"Marked email {uid} as read")
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return False
        finally:
            self.disconnect()

    def move_to_folder(self, uid, destination_folder, source_folder='Receipts'):
        """Move an email to a different folder"""
        try:
            if not self.connect():
                return False

            # Select the source folder first
            self.client.select_folder(source_folder)

            # Copy to destination folder
            self.client.copy([uid], destination_folder)

            # Delete from current folder (adds \Deleted flag)
            self.client.delete_messages([uid])

            # Expunge to actually move it
            self.client.expunge()

            logger.debug(f"Moved email {uid} to {destination_folder}")
            return True
        except Exception as e:
            logger.error(f"Failed to move email to {destination_folder}: {e}")
            return False
        finally:
            self.disconnect()