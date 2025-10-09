"""
Homebox Client - Interacts with Homebox API
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)


class HomeboxClient:
    """Client for interacting with Homebox API"""

    def __init__(self):
        self.base_url = os.getenv('HOMEBOX_URL', '').rstrip('/')
        self.username = os.getenv('HOMEBOX_USERNAME', '')
        self.password = os.getenv('HOMEBOX_PASSWORD', '')
        self.token = None

        # Initialize headers first
        self.headers = {
            'Content-Type': 'application/json'
        }

        if not self.base_url or not self.username or not self.password:
            logger.warning("Homebox URL, username, or password not configured")
        else:
            # Automatically login on initialization
            self._login()

    def _login(self):
        """Login to Homebox and get bearer token"""
        try:
            logger.debug("Logging into Homebox...")
            response = requests.post(
                f"{self.base_url}/api/v1/users/login",
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'username': self.username,
                    'password': self.password
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            self.token = data.get('token')

            if self.token:
                # Check if token already has "Bearer" prefix
                if self.token.startswith('Bearer '):
                    self.headers['Authorization'] = self.token
                else:
                    self.headers['Authorization'] = f'Bearer {self.token}'
                logger.debug("✓ Successfully logged into Homebox")
                return True
            else:
                logger.error("Login response missing token")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to login to Homebox: {e}")
            return False
    
    def test_connection(self):
        """Test connection to Homebox"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/status",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info("✓ Connected to Homebox successfully")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Homebox: {e}")
            return False
    
    def create_item(self, item_data):
        """Create a new item in Homebox (two-step: create then update)"""
        try:
            logger.debug(f"Creating item: {item_data.get('name')}")

            # Step 1: Create with basic fields only
            create_data = {
                'name': item_data['name'],
                'locationId': item_data['locationId']
            }

            # Add optional create fields
            if 'description' in item_data:
                create_data['description'] = item_data['description']
            if 'quantity' in item_data:
                create_data['quantity'] = item_data['quantity']
            if 'labelIds' in item_data:
                create_data['labelIds'] = item_data['labelIds']
            if 'parentId' in item_data:
                create_data['parentId'] = item_data['parentId']

            logger.debug(f"Create data: {create_data}")

            response = requests.post(
                f"{self.base_url}/api/v1/items",
                headers=self.headers,
                json=create_data,
                timeout=30
            )

            logger.debug(f"Create response status: {response.status_code}")

            if response.status_code == 201:
                result = response.json()
                item_id = result.get('id')
                logger.info(f"✓ Created item: {item_data.get('name')} (ID: {item_id})")

                # Step 2: Update with purchase price and other fields
                # Update requires name and locationId even if not changing them
                update_data = {
                    'name': result.get('name'),
                    'locationId': result.get('location', {}).get('id')
                }

                update_fields = ['purchasePrice', 'purchaseFrom', 'purchaseTime',
                                'manufacturer', 'modelNumber', 'serialNumber',
                                'notes', 'warrantyDetails', 'warrantyExpires',
                                'description', 'quantity']

                for field in update_fields:
                    if field in item_data:
                        update_data[field] = item_data[field]

                # Check if we have any fields to update beyond the required ones
                has_updates = any(field in item_data for field in update_fields)
                if has_updates:
                    logger.debug(f"Update data: {update_data}")
                    update_response = requests.put(
                        f"{self.base_url}/api/v1/items/{item_id}",
                        headers=self.headers,
                        json=update_data,
                        timeout=30
                    )
                    logger.debug(f"Update response status: {update_response.status_code}")

                    if update_response.status_code == 200:
                        result = update_response.json()
                        logger.debug(f"✓ Updated item with additional fields")
                    else:
                        logger.warning(f"Failed to update item fields: {update_response.status_code}")
                        logger.debug(f"Update response: {update_response.text}")

                return result
            elif response.status_code == 401:
                # Token expired, try to re-login once
                logger.warning("Token expired, attempting to re-login...")
                if self._login():
                    # Retry the request
                    response = requests.post(
                        f"{self.base_url}/api/v1/items",
                        headers=self.headers,
                        json=item_data,
                        timeout=30
                    )
                    if response.status_code == 201:
                        result = response.json()
                        logger.info(f"✓ Created item: {item_data.get('name')}")
                        return result

                logger.error(f"Failed to create item after re-login. Status: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None
            else:
                logger.error(f"Failed to create item. Status: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating item: {e}")
            return None
    
    def get_locations(self):
        """Get all locations"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/locations",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting locations: {e}")
            return None

    def get_location_id_by_name(self, location_name):
        """Get location ID by name"""
        locations = self.get_locations()
        if not locations:
            return None

        for location in locations:
            if location.get('name', '').lower() == location_name.lower():
                return location.get('id')

        logger.warning(f"Location '{location_name}' not found")
        return None
    
    def get_labels(self):
        """Get all labels"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/labels",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting labels: {e}")
            return None

    def get_items(self, page=1, page_size=50):
        """
        Get items from Homebox with pagination

        Args:
            page: Page number (default: 1)
            page_size: Items per page (default: 50)

        Returns:
            Dictionary with 'items' list and pagination info, or None if failed
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/items",
                headers=self.headers,
                params={'page': page, 'pageSize': page_size},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting items: {e}")
            return None

    def get_item(self, item_id):
        """
        Get single item by ID with full details including attachments

        Args:
            item_id: The ID of the item

        Returns:
            Item dictionary with full details, or None if failed
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/items/{item_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting item {item_id}: {e}")
            return None

    def upload_attachment(self, item_id, image_data, filename, attachment_type="photo"):
        """
        Upload an image attachment to a Homebox item

        Args:
            item_id: The ID of the item to attach to
            image_data: The binary image data (bytes)
            filename: The filename for the attachment
            attachment_type: Type of attachment (default: "photo")

        Returns:
            The attachment response data, or None if failed
        """
        try:
            logger.debug(f"Uploading attachment to item {item_id}: {filename}")

            # Prepare multipart form data
            # Note: Don't include Content-Type header for multipart, requests will set it
            files = {
                'file': (filename, image_data, 'image/jpeg')
            }
            data = {
                'type': attachment_type,
                'name': filename  # Homebox requires 'name' field
            }

            # Create headers without Content-Type for multipart upload
            upload_headers = {
                'Authorization': self.headers.get('Authorization')
            }

            response = requests.post(
                f"{self.base_url}/api/v1/items/{item_id}/attachments",
                headers=upload_headers,
                files=files,
                data=data,
                timeout=30
            )

            logger.debug(f"Upload response status: {response.status_code}")

            if response.status_code in [200, 201]:
                result = response.json()
                logger.info(f"✓ Uploaded attachment: {filename}")
                return result
            elif response.status_code == 401:
                # Token expired, try to re-login once
                logger.warning("Token expired during upload, attempting to re-login...")
                if self._login():
                    # Update auth header
                    upload_headers['Authorization'] = self.headers.get('Authorization')
                    # Retry the request
                    response = requests.post(
                        f"{self.base_url}/api/v1/items/{item_id}/attachments",
                        headers=upload_headers,
                        files={'file': (filename, image_data, 'image/jpeg')},
                        data={'type': attachment_type, 'name': filename},
                        timeout=30
                    )
                    if response.status_code in [200, 201]:
                        result = response.json()
                        logger.info(f"✓ Uploaded attachment after re-login: {filename}")
                        return result

                logger.error(f"Failed to upload attachment after re-login. Status: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None
            else:
                logger.error(f"Failed to upload attachment. Status: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error uploading attachment: {e}")
            return None