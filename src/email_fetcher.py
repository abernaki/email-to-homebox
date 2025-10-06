"""
Email Fetcher - Connects to email and retrieves receipt emails
"""

import os
import re
import logging
import email
from email.header import decode_header
from imapclient import IMAPClient
from bs4 import BeautifulSoup

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
            
            return {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body
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