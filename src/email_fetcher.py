"""
Email Fetcher - Connects to email and retrieves receipt emails
"""

import os
import re
import logging
import email
import requests
from io import BytesIO
from email.header import decode_header
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from PIL import Image

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

            return {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body,
                'images': images
            }
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
        body = ''
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                
                if content_type == 'text/plain':
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        pass
                elif content_type == 'text/html' and not body:
                    try:
                        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        # Convert HTML to text
                        soup = BeautifulSoup(html, 'lxml')
                        body = soup.get_text(separator='\n', strip=True)
                    except:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                pass
        
        return body

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

        # Third pass: validate and filter images by dimensions
        filtered_images = []
        for img_data in images:
            try:
                image = Image.open(BytesIO(img_data['data']))
                width, height = image.size

                # Filter by size: 100x100 < size < 2000x2000
                if 100 < width < 2000 and 100 < height < 2000:
                    img_data['width'] = width
                    img_data['height'] = height
                    img_data['size'] = len(img_data['data'])
                    filtered_images.append(img_data)
                    logger.debug(f"Validated image: {width}x{height}, {img_data['source']}")
                else:
                    logger.debug(f"Filtered out image by size: {width}x{height}")
            except Exception as e:
                logger.debug(f"Error validating image: {e}")

        # Sort by area (largest first) - likely product images are bigger
        filtered_images.sort(key=lambda x: x['width'] * x['height'], reverse=True)

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