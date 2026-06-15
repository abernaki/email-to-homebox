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

# Global OCR reader instance (lazy-loaded)
_ocr_reader = None


def extract_shopify_products(soup):
    """
    Extract product information from Shopify/Leap receipt emails.

    Returns:
        Formatted product text or None if no Shopify products found
    """
    # Look for Shopify order list items
    items = soup.find_all(class_='order-list__item-title')
    if not items:
        return None

    logger.info(f"Found {len(items)} Shopify product(s)")
    product_text = "--- SHOPIFY ORDER ITEMS ---\n\n"

    for item in items:
        # Get product name (clean up the weird characters)
        name = item.get_text(strip=True)
        # Remove common quantity indicators like נ1, ×1, etc.
        name = name.replace('נ', ' × ').replace('×', ' × ')

        product_text += f"Product: {name}\n"

        # Find the parent row to get price info
        row = item.find_parent('tr')
        if row:
            # Get variant/size
            variant = row.find(class_='order-list__item-variant')
            if variant:
                product_text += f"Variant: {variant.get_text(strip=True)}\n"

            # Get discount info
            discount = row.find(class_='order-list__item-discount-allocation')
            if discount:
                product_text += f"Discount: {discount.get_text(strip=True)}\n"

            # Get original price
            original_price = row.find(class_='order-list__item-original-price')
            if original_price:
                product_text += f"Original Price: {original_price.get_text(strip=True)}\n"

            # Get final price
            final_price = row.find(class_='order-list__item-price')
            if final_price:
                product_text += f"Final Price: {final_price.get_text(strip=True)}\n"

        product_text += "\n"

    return product_text


def extract_text_from_html(html):
    """
    Smart HTML to text extraction that prioritizes receipt content.

    Strategy:
    1. Check for Shopify/Leap structured product data
    2. Look for <pre> tags (often contain formatted receipt text)
    3. Remove script, style, and navigation elements
    4. Extract remaining text with proper formatting

    Args:
        html: Raw HTML string

    Returns:
        Extracted text string
    """
    try:
        soup = BeautifulSoup(html, 'lxml')

        structured_content = ""

        # First, check for Shopify/Leap product structure
        shopify_products = extract_shopify_products(soup)
        if shopify_products:
            structured_content += shopify_products + "\n"

        # Check for <pre> tags which often contain receipt text
        pre_tags = soup.find_all('pre')
        if pre_tags:
            logger.info(f"Found {len(pre_tags)} <pre> tag(s) - prioritizing this content")
            # Combine all pre tag content
            pre_content = '\n\n--- RECEIPT DATA ---\n'.join(
                pre.get_text(separator='\n', strip=True) for pre in pre_tags
            )
            structured_content += pre_content + "\n"

        # Remove unwanted elements that add noise
        for tag in soup(['script', 'style', 'meta', 'link', 'noscript', 'head']):
            tag.decompose()

        # Get the main text content
        main_text = soup.get_text(separator='\n', strip=True)

        # If we found structured content, put it first
        if structured_content:
            return f"{structured_content}\n--- EMAIL BODY ---\n{main_text}"
        else:
            return main_text

    except Exception as e:
        logger.warning(f"Error extracting HTML: {e}")
        # Fallback to simple extraction
        soup = BeautifulSoup(html, 'lxml')
        return soup.get_text(separator='\n', strip=True)


class EmailFetcher:
    """Fetches receipt emails from IMAP server"""

    def __init__(self, config, processing_config=None):
        self.config = config
        self.host = os.getenv('EMAIL_IMAP_HOST')
        self.port = int(os.getenv('EMAIL_IMAP_PORT', 993))
        self.username = os.getenv('EMAIL_ADDRESS')
        self.password = os.getenv('EMAIL_PASSWORD')
        self.client = None

        # Get OCR settings from processing_config if provided, otherwise from config
        if processing_config:
            self.ocr_enabled = processing_config.get('enable_ocr', True)
        else:
            # Legacy: try to get from config directly (for backward compatibility)
            self.ocr_enabled = config.get('enable_ocr', True)
        
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

            # If body is minimal/empty and we have images, try OCR
            # This handles physical receipt photos sent via email
            logger.debug(f"OCR check: enabled={self.ocr_enabled}, body_len={len(body.strip())}, images={len(images)}")
            if self.ocr_enabled and len(body.strip()) < 200 and images:
                logger.info(f"Body text is minimal ({len(body)} chars), attempting OCR on {len(images)} images...")
                ocr_text = self._extract_text_from_images(images)
                if ocr_text:
                    # Prepend OCR text to body (or replace if body is empty)
                    if body.strip():
                        body = ocr_text + "\n\n--- Original Email Body ---\n" + body
                    else:
                        body = ocr_text
                    logger.info(f"✓ OCR successful! Extracted {len(ocr_text)} characters")
                    logger.info(f"Body now has {len(body)} total characters")
                else:
                    logger.warning("✗ OCR returned no text from images")
            elif not self.ocr_enabled:
                logger.debug("OCR is disabled in config")
            elif len(body.strip()) >= 200:
                logger.debug(f"Body has sufficient text ({len(body)} chars), skipping OCR")

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

        logger.debug(f"Extracting body, is_multipart: {email_message.is_multipart()}")

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                logger.debug(f"Found part with content_type: {content_type}")

                if content_type == 'text/plain' and not plain_body:
                    try:
                        plain_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        pass
                elif content_type == 'text/html' and not html_body:
                    try:
                        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        logger.debug(f"Extracting HTML (length: {len(html)} chars)")
                        # Convert HTML to text using smart extraction
                        html_body = extract_text_from_html(html)
                        logger.debug(f"Extracted HTML to text (length: {len(html_body)} chars)")
                    except Exception as e:
                        logger.warning(f"Error extracting HTML: {e}")
                        pass
        else:
            # Non-multipart email - check content type
            content_type = email_message.get_content_type()
            logger.debug(f"Non-multipart email with content_type: {content_type}")

            try:
                payload = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')

                if content_type == 'text/html':
                    # It's HTML, extract it properly
                    logger.debug(f"Extracting HTML (length: {len(payload)} chars)")
                    html_body = extract_text_from_html(payload)
                    logger.debug(f"Extracted HTML to text (length: {len(html_body)} chars)")
                else:
                    # It's plain text
                    plain_body = payload
            except Exception as e:
                logger.warning(f"Error extracting body: {e}")
                pass

        # Prefer HTML if plain text is too short/minimal (less than 1000 chars)
        # This handles cases like Best Buy where plain text is just a link
        if html_body and (not plain_body or len(plain_body) < 1000):
            logger.info(f"Using HTML body (plain text too short: {len(plain_body) if plain_body else 0} chars)")
            return html_body

        # Otherwise use plain text (more readable for LLM)
        if plain_body:
            logger.info(f"Using plain text body ({len(plain_body)} chars)")
        else:
            logger.info("Using HTML body (no plain text available)")
        return plain_body if plain_body else html_body

    def _extract_images(self, email_message):
        """Extract and download product images from email"""
        images = []
        html_content = None
        inline_images = {}  # Map Content-ID to image data for inline images

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

                # Get image attachments (including inline images with Content-ID)
                if content_type.startswith('image/'):
                    try:
                        image_data = part.get_payload(decode=True)
                        if image_data and len(image_data) > 10240:  # > 10KB
                            filename = part.get_filename() or 'attachment.jpg'

                            # Check disposition to see if it's inline
                            content_disposition = str(part.get('Content-Disposition', ''))
                            is_inline = 'inline' in content_disposition.lower()

                            # Check if this is an inline image with Content-ID
                            content_id = part.get('Content-ID')
                            if content_id:
                                # Store by Content-ID for later lookup
                                # Remove < > brackets from Content-ID
                                cid = content_id.strip('<>')
                                inline_images[cid] = image_data
                                logger.debug(f"Found inline image with CID: {cid} ({len(image_data)} bytes)")
                            elif is_inline:
                                # Inline image without Content-ID (like Apple Mail inline images)
                                images.append({
                                    'data': image_data,
                                    'source': 'inline',
                                    'filename': filename,
                                    'url': None
                                })
                                logger.debug(f"Found inline image (no CID): {filename} ({len(image_data)} bytes)")
                            else:
                                # Regular attachment
                                images.append({
                                    'data': image_data,
                                    'source': 'attachment',
                                    'filename': filename,
                                    'url': None
                                })
                                logger.debug(f"Found image attachment: {filename} ({len(image_data)} bytes)")
                    except Exception as e:
                        logger.debug(f"Error extracting image attachment: {e}")

        # Second pass: parse HTML for linked images (both HTTP URLs and inline cid: references)
        if html_content:
            try:
                soup = BeautifulSoup(html_content, 'lxml')
                img_tags = soup.find_all('img')

                for img in img_tags:
                    src = img.get('src')
                    if not src:
                        continue

                    # Handle inline images with cid: references
                    if src.startswith('cid:'):
                        cid = src[4:]  # Remove 'cid:' prefix
                        if cid in inline_images:
                            images.append({
                                'data': inline_images[cid],
                                'source': 'inline',
                                'filename': f'inline_{cid}.jpg',
                                'url': None
                            })
                            logger.debug(f"Matched inline image with CID: {cid}")
                        else:
                            logger.debug(f"CID not found in inline images: {cid}")
                        continue

                    # Handle HTTP/HTTPS URLs
                    if not src.startswith('http'):
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

        # Sort images: prioritize inline > html_link > attachment
        # Inline images are most likely to be receipt photos
        # Web images (html_link) are more likely to be product photos
        # Attachments are often logos or tracking pixels
        source_priority = {'inline': 0, 'html_link': 1, 'attachment': 2}
        images.sort(key=lambda x: source_priority.get(x['source'], 3))

        # Third pass: validate and filter images by dimensions
        filtered_images = []
        for img_data in images:
            try:
                image = Image.open(BytesIO(img_data['data']))
                width, height = image.size

                # Filter by size: 100x100 < size <= 5000x5000
                # Allow up to 5000px for high-quality product photos and receipt images
                if 100 < width <= 5000 and 100 < height <= 5000:
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

    def _get_ocr_reader(self):
        """
        Get or initialize the global OCR reader.
        Lazy-loads EasyOCR to avoid initialization overhead if not needed.
        """
        global _ocr_reader
        if _ocr_reader is None:
            try:
                import easyocr
                logger.info("Initializing EasyOCR (this may take a moment on first run)...")
                # Initialize with English only for faster loading
                # gpu=True to use Apple Silicon GPU acceleration
                _ocr_reader = easyocr.Reader(['en'], gpu=True)
                logger.info("EasyOCR initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR: {e}")
                return None
        return _ocr_reader

    def _extract_text_from_images(self, images):
        """
        Extract text from images using OCR.

        Args:
            images: List of image dicts with 'data' (bytes) field

        Returns:
            str: Extracted text from all images combined
        """
        if not self.ocr_enabled:
            logger.debug("OCR is disabled in config")
            return ""

        if not images:
            logger.debug("No images provided for OCR")
            return ""

        # Get OCR reader
        reader = self._get_ocr_reader()
        if reader is None:
            logger.warning("OCR reader not available, skipping text extraction")
            return ""

        all_text = []
        for idx, img_data in enumerate(images):
            try:
                # Load image from bytes
                image = Image.open(BytesIO(img_data['data']))

                # Convert to RGB if needed (EasyOCR requires RGB)
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                logger.debug(f"Running OCR on image {idx+1}/{len(images)} ({image.size[0]}x{image.size[1]})...")

                # Run OCR
                results = reader.readtext(image, detail=0)  # detail=0 returns just text, no coordinates

                if results:
                    text = '\n'.join(results)
                    all_text.append(f"--- OCR from Image {idx+1} ---")
                    all_text.append(text)
                    logger.info(f"Extracted {len(text)} characters from image {idx+1}")
                else:
                    logger.debug(f"No text found in image {idx+1}")

            except Exception as e:
                logger.error(f"Error extracting text from image {idx+1}: {e}")
                continue

        combined_text = '\n\n'.join(all_text)
        if combined_text:
            logger.info(f"Total OCR extracted text: {len(combined_text)} characters from {len(images)} images")
        return combined_text

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