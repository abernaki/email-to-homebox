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
        query = f"{manufacturer} {product_name} product"
    else:
        query = f"{product_name} product"

    logger.debug(f"Searching DuckDuckGo for: {query}")

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            # Search for images
            with DDGS() as ddgs:
                results = ddgs.images(
                    query=query,
                    max_results=max_results * 2,  # Get extra to filter
                    layout="square",
                    size="medium",
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

                        # Filter by size: 100x100 < size < 2000x2000
                        if not (100 < width < 2000 and 100 < height < 2000):
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

    # Sort by area (width * height), prefer larger images
    sorted_images = sorted(images, key=lambda x: x['width'] * x['height'], reverse=True)

    # Try to find an image with preferred minimum size
    for img in sorted_images:
        if img['width'] >= preferred_min_size and img['height'] >= preferred_min_size:
            return img

    # If no image meets preferred size, return the largest one
    return sorted_images[0]


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

    # Simple strategy: assign N largest images to N items (where N = min(images, items))
    num_matches = min(len(images), len(items))

    # Sort images by area (largest first)
    sorted_images = sorted(images, key=lambda x: x['width'] * x['height'], reverse=True)

    matches = {}
    for i in range(num_matches):
        matches[i] = sorted_images[i]

    logger.info(f"Matched {num_matches} image(s) to receipt items")
    return matches
