"""
Homebox Client - Interacts with Homebox API
"""

import os
import logging
import mimetypes
import requests

from homebox_errors import PartialEntityUpdateError

logger = logging.getLogger(__name__)


class HomeboxClient:
    """Client for interacting with Homebox API"""

    def __init__(self):
        self.base_url = os.getenv('HOMEBOX_URL', '').rstrip('/')
        self.username = os.getenv('HOMEBOX_USERNAME', '')
        self.password = os.getenv('HOMEBOX_PASSWORD', '')
        self.api_key = os.getenv('HOMEBOX_API_KEY', '').strip()
        self.token = None

        # Initialize headers first
        self.headers = {
            'Content-Type': 'application/json'
        }

        if not self.base_url:
            logger.warning("Homebox URL not configured")
        elif self.api_key:
            self.headers['Authorization'] = self._bearer_authorization(self.api_key)
        elif self.username and self.password:
            self._login()
        else:
            logger.warning("Homebox API key or username/password not configured")

    @staticmethod
    def _bearer_authorization(token):
        """Return a correctly formatted bearer authorization header value."""
        if token.startswith('Bearer '):
            return token
        return f'Bearer {token}'

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
                self.headers['Authorization'] = self._bearer_authorization(self.token)
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
    
    @staticmethod
    def _entity_update_payload(entity, updates=None, item_id=None):
        """Build a complete EntityUpdate body while preserving existing entity data."""
        updates = dict(updates or {})
        payload = {
            'id': item_id or entity.get('id'),
            'name': entity.get('name', ''),
            'description': entity.get('description', ''),
            'serialNumber': entity.get('serialNumber', ''),
            'modelNumber': entity.get('modelNumber', ''),
            'manufacturer': entity.get('manufacturer', ''),
            'warrantyDetails': entity.get('warrantyDetails', ''),
            'warrantyExpires': entity.get('warrantyExpires', ''),
            'purchaseFrom': entity.get('purchaseFrom', ''),
            'soldTo': entity.get('soldTo', ''),
            'soldNotes': entity.get('soldNotes', ''),
            'notes': entity.get('notes', ''),
            'tagIds': [tag['id'] for tag in entity.get('tags', []) if tag.get('id')],
            'fields': entity.get('fields', []),
            'assetId': entity.get('assetId', ''),
            'quantity': entity.get('quantity', 0),
            'purchasePrice': entity.get('purchasePrice', 0),
            'soldPrice': entity.get('soldPrice', 0),
            'parentId': (entity.get('parent') or {}).get('id'),
            'entityTypeId': (entity.get('entityType') or {}).get('id'),
            'insured': entity.get('insured', False),
            'archived': entity.get('archived', False),
            'syncChildEntityLocations': entity.get('syncChildEntityLocations', False),
            'lifetimeWarranty': entity.get('lifetimeWarranty', False),
            'purchaseDate': entity.get('purchaseDate', ''),
            'soldDate': entity.get('soldDate', ''),
        }

        if 'parentId' in updates or 'locationId' in updates:
            parent_id = updates.pop('parentId', None)
            legacy_location_id = updates.pop('locationId', None)
            payload['parentId'] = parent_id if parent_id is not None else legacy_location_id
        if 'labelIds' in updates:
            updates.setdefault('tagIds', updates.pop('labelIds'))
        if 'purchaseTime' in updates:
            updates.setdefault('purchaseDate', updates.pop('purchaseTime'))
        for key, value in updates.items():
            if key in payload:
                payload[key] = value
        return payload

    def _update_entity(self, item_id, updates, current_entity=None):
        """Apply a full Homebox entity update, optionally reusing a fetched entity."""
        if current_entity is None:
            current_entity = self.get_item(item_id)
        if not current_entity:
            logger.error(f"Could not fetch entity {item_id} before update")
            return None
        try:
            response = requests.put(
                f"{self.base_url}/api/v1/entities/{item_id}",
                headers=self.headers,
                json=self._entity_update_payload(current_entity, updates, item_id),
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating entity {item_id}: {e}")
            return None

    def update_item(self, item_id, updates, current_entity=None):
        """Update an item using Homebox's full entity update contract."""
        return self._update_entity(item_id, updates, current_entity)

    def create_item(self, item_data):
        """Create an item entity and apply purchase details supported by Homebox."""
        create_data = {
            'name': item_data['name'],
            'parentId': item_data.get('parentId', item_data.get('locationId')),
            'description': item_data.get('description', ''),
            'quantity': item_data.get('quantity', 1),
            'tagIds': item_data.get('tagIds', item_data.get('labelIds', [])),
        }
        for field in ('modelNumber', 'manufacturer', 'entityTypeId'):
            if field in item_data:
                create_data[field] = item_data[field]

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/entities",
                headers=self.headers,
                json=create_data,
                timeout=30
            )
            if response.status_code == 401:
                if self.api_key:
                    logger.error("Homebox rejected the configured API key")
                else:
                    logger.warning("Token expired, attempting to re-login...")
                if not self.api_key and self._login():
                    response = requests.post(
                        f"{self.base_url}/api/v1/entities",
                        headers=self.headers,
                        json=create_data,
                        timeout=30
                    )
            if response.status_code != 201:
                logger.error(f"Failed to create entity. Status: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None

            result = response.json()
            entity_id = result.get('id')
            logger.info(f"✓ Created item: {item_data.get('name')} (ID: {entity_id})")

            extra_fields = {
                'purchasePrice', 'purchaseFrom', 'purchaseTime', 'purchaseDate',
                'serialNumber', 'notes', 'warrantyDetails', 'warrantyExpires',
            }
            if extra_fields.intersection(item_data):
                update_result = self._update_entity(entity_id, item_data, current_entity=result)
                if not update_result:
                    raise PartialEntityUpdateError(entity_id)
                result = update_result
            return result
        except PartialEntityUpdateError:
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating entity: {e}")
            return None
    
    def get_locations(self):
        """Get all locations from the paginated entities endpoint."""
        try:
            locations = []
            page = 1
            while True:
                response = requests.get(
                    f"{self.base_url}/api/v1/entities",
                    headers=self.headers,
                    params={'isLocation': 'true', 'page': page, 'pageSize': 100},
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                page_items = result.get('items', [])
                locations.extend(page_items)
                if len(locations) >= result.get('total', len(locations)) or not page_items:
                    return locations
                page += 1
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
        """Get all tags (Homebox labels were renamed to tags)."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/tags",
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
                f"{self.base_url}/api/v1/entities",
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
                f"{self.base_url}/api/v1/entities/{item_id}",
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
                'file': (
                    filename,
                    image_data,
                    mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                )
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
                f"{self.base_url}/api/v1/entities/{item_id}/attachments",
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
                if self.api_key:
                    logger.error("Homebox rejected the configured API key during upload")
                else:
                    logger.warning("Token expired during upload, attempting to re-login...")
                if not self.api_key and self._login():
                    # Update auth header
                    upload_headers['Authorization'] = self.headers.get('Authorization')
                    # Retry the request
                    response = requests.post(
                        f"{self.base_url}/api/v1/entities/{item_id}/attachments",
                        headers=upload_headers,
                        files=files,
                        data=data,
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

    def create_label(self, name, description="", color="#3B82F6"):
        """
        Create a new label in Homebox

        Args:
            name: Label name
            description: Optional description
            color: Hex color code (default: blue)

        Returns:
            Label data with ID, or None if failed
        """
        try:
            data = {
                'name': name,
                'description': description,
                'color': color
            }

            response = requests.post(
                f"{self.base_url}/api/v1/tags",
                headers=self.headers,
                json=data,
                timeout=10
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(f"✓ Created label: {name} (ID: {result.get('id')})")
                return result
            else:
                logger.error(f"Failed to create label '{name}': {response.status_code}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating label: {e}")
            return None

    def get_label_by_name(self, name):
        """
        Find a label by name

        Args:
            name: Label name to search for

        Returns:
            Label data with ID, or None if not found
        """
        labels = self.get_labels()
        if not labels:
            return None

        for label in labels:
            if label.get('name', '').lower() == name.lower():
                return label

        return None

    def ensure_label_exists(self, name, description="", color="#3B82F6"):
        """
        Get label by name, or create if it doesn't exist

        Args:
            name: Label name
            description: Description (used if creating)
            color: Color (used if creating)

        Returns:
            Label ID, or None if failed
        """
        # Try to find existing label
        label = self.get_label_by_name(name)
        if label:
            logger.debug(f"Found existing label: {name} (ID: {label.get('id')})")
            return label.get('id')

        # Create new label
        logger.info(f"Creating new label: {name}")
        label = self.create_label(name, description, color)
        if label:
            return label.get('id')

        return None

    def add_label_to_item(self, item_id, label_id):
        """
        Add a label to an item

        Args:
            item_id: Item ID
            label_id: Label ID to add

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current item to retrieve existing labels
            item = self.get_item(item_id)
            if not item:
                logger.error(f"Could not fetch item {item_id}")
                return False

            # Get current label IDs
            current_tags = item.get('tags', [])
            current_tag_ids = [tag.get('id') for tag in current_tags if tag.get('id')]

            # Add new label if not already present
            if label_id in current_tag_ids:
                logger.debug(f"Tag {label_id} already on entity {item_id}")
                return True

            current_tag_ids.append(label_id)
            if self._update_entity(item_id, {'tagIds': current_tag_ids}, current_entity=item):
                logger.debug(f"✓ Added label {label_id} to item {item_id}")
                return True
            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding label to item: {e}")
            return False