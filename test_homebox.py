#!/usr/bin/env python3
"""
Test Homebox API connection and item creation
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, 'src')

from homebox_client import HomeboxClient

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()


def test_homebox():
    """Test Homebox API"""

    logger.info("=" * 60)
    logger.info("Homebox API Test")
    logger.info("=" * 60)

    # Initialize client
    logger.info("\n1. Initializing Homebox client...")
    client = HomeboxClient()

    logger.info(f"   Base URL: {client.base_url}")
    logger.info(f"   Username: {client.username}")
    logger.info(f"   Token: {client.token[:20] if client.token else 'None'}...")

    # Test connection
    logger.info("\n2. Testing connection...")
    if client.test_connection():
        logger.info("   ✓ Connection successful")
    else:
        logger.error("   ✗ Connection failed")
        return False

    # Get locations first
    logger.info("\n3. Getting locations...")
    locations = client.get_locations()

    if locations and len(locations) > 0:
        first_location = locations[0]
        location_id = first_location.get('id')
        logger.info(f"   Using location: {first_location.get('name')} (ID: {location_id})")
    else:
        logger.error("   No locations found - you need to create at least one location in Homebox first")
        return False

    # Test creating a simple item
    logger.info("\n4. Testing item creation...")
    test_item = {
        'name': 'Test Item from API',
        'description': 'This is a test item created by the receipt processor test script',
        'quantity': 1,
        'purchasePrice': 9.99,
        'locationId': location_id
    }

    logger.info(f"   Creating item: {test_item['name']}")
    result = client.create_item(test_item)

    if result:
        logger.info("   ✓ Item created successfully!")
        logger.info(f"   Item ID: {result.get('id', 'N/A')}")
        return True
    else:
        logger.error("   ✗ Failed to create item")
        return False


if __name__ == '__main__':
    success = test_homebox()

    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✓ All tests passed!")
    else:
        logger.error("✗ Tests failed - check your Homebox credentials")
    logger.info("=" * 60)

    sys.exit(0 if success else 1)
