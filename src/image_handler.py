"""
Image Handler - Search and download product images
"""

import logging
import time
import requests
from io import BytesIO
from PIL import Image
from ddgs import DDGS

logger = logging.getLogger(__name__)


def should_skip_image_by_filename(filename):
    """
    Check if an image should be skipped based on filename patterns

    Images with these patterns in the filename are likely logos, icons,
    tracking pixels, or other non-product images.

    Args:
        filename: The image filename or URL

    Returns:
        bool: True if image should be skipped, False if it looks like a product image
    """
    if not filename:
        return False

    filename_lower = filename.lower()

    # Patterns that indicate non-product images
    skip_patterns = [
        'logo',
        'icon',
        'badge',
        'button',
        'banner',
        'pixel',
        'track',
        'spacer',
        'dot',
        'transparent',
        'blank',
        '1x1',
        'email_logo',  # Common in email templates
    ]

    for pattern in skip_patterns:
        if pattern in filename_lower:
            logger.debug(f"Skipping image with '{pattern}' in filename: {filename}")
            return True

    return False


def search_product_image(product_name, manufacturer=None, max_results=3, max_retries=3):
    """
    Search for product images using DuckDuckGo with retry logic

    Args:
        product_name: The name of the product
        manufacturer: Optional manufacturer name to improve search
        max_results: Maximum number of images to return (default: 3)
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        List of image data dictionaries with 'data', 'url', 'width', 'height', 'size'
    """
    # Build search query
    if manufacturer:
        query = f"{manufacturer} {product_name}"
    else:
        query = f"{product_name}"

    logger.debug(f"Searching DuckDuckGo for: {query}")

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            # Search for images
            with DDGS() as ddgs:
                results = ddgs.images(
                    query=query,
                    max_results=max_results * 2,  # Get extra to filter
                )

            images = []
            for result in results:
                try:
                    image_url = result.get('image')
                    if not image_url:
                        continue

                    # Download and validate image
                    logger.debug(f"Downloading image from: {image_url[:100]}")
                    response = requests.get(image_url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    })

                    if response.status_code != 200:
                        continue

                    image_data = response.content

                    # Validate image
                    if len(image_data) < 10240:  # Skip images < 10KB
                        logger.debug(f"Skipping small image: {len(image_data)} bytes")
                        continue

                    # Check dimensions
                    try:
                        image = Image.open(BytesIO(image_data))
                        width, height = image.size

                        # Filter by size: 100x100 < size <= 4000x4000
                        # Allow up to 4000px for high-quality product photos
                        if not (100 < width <= 4000 and 100 < height <= 4000):
                            logger.debug(f"Skipping image with dimensions: {width}x{height}")
                            continue

                        images.append({
                            'data': image_data,
                            'url': image_url,
                            'source': 'duckduckgo',
                            'filename': f"{product_name[:30].replace(' ', '_')}.jpg",
                            'width': width,
                            'height': height,
                            'size': len(image_data)
                        })

                        logger.debug(f"Found valid image: {width}x{height}, {len(image_data)} bytes")

                        # Stop once we have enough valid images
                        if len(images) >= max_results:
                            break

                    except Exception as e:
                        logger.debug(f"Error validating image: {e}")
                        continue

                except Exception as e:
                    logger.debug(f"Error processing search result: {e}")
                    continue

            logger.info(f"Found {len(images)} product image(s) via DuckDuckGo for '{product_name}'")
            return images

        except Exception as e:
            # Check if this is a rate limit error
            error_msg = str(e).lower()
            is_rate_limit = any(x in error_msg for x in ['rate limit', 'ratelimit', 'too many requests', '429'])

            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff: 2s, 4s, 8s
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"Rate limit detected, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Error searching for product images: {e}")
                return []

    # If we get here, all retries failed
    logger.error(f"Failed to search for '{product_name}' after {max_retries} attempts")
    return []


def get_best_image(images, preferred_min_size=200):
    """
    Get the best image from a list of images

    Args:
        images: List of image dictionaries with 'width', 'height', 'size'
        preferred_min_size: Preferred minimum dimension (default: 200)

    Returns:
        The best image dictionary, or None if no images
    """
    if not images:
        return None

    # Use first-wins logic: first image is usually the most relevant
    # Try to find the first image with preferred minimum size
    for img in images:
        if img['width'] >= preferred_min_size and img['height'] >= preferred_min_size:
            return img

    # If no image meets preferred size, return the first one
    return images[0]


def match_images_to_items(images, items):
    """
    Match extracted images to receipt items

    Args:
        images: List of image dictionaries
        items: List of item dictionaries from receipt extraction

    Returns:
        Dictionary mapping item indices to image data
    """
    if not images or not items:
        return {}

    # Simple strategy: assign first N images to N items (where N = min(images, items))
    # First image is usually the most relevant product image
    num_matches = min(len(images), len(items))

    matches = {}
    for i in range(num_matches):
        matches[i] = images[i]

    logger.info(f"Matched {num_matches} image(s) to receipt items")
    return matches
