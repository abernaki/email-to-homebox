"""
Receipt Extractor - MLX Implementation
Uses MLX-LM for fast local inference on Apple Silicon
"""

import os
import json
import logging
from mlx_lm import load, generate

logger = logging.getLogger(__name__)


class ReceiptExtractor:
    """Extracts receipt data using MLX-LM on Apple Silicon"""
    
    def __init__(self, config):
        self.config = config
        self.model_name = os.getenv('AI_MODEL', 'mlx-community/Qwen2.5-7B-Instruct-4bit')
        self.temperature = float(os.getenv('AI_TEMPERATURE', '0.1'))
        self.max_tokens = int(os.getenv('AI_MAX_TOKENS', '2048'))
        
        self.model = None
        self.tokenizer = None
        self._load_model()
    
    def _load_model(self):
        """Load the MLX model and tokenizer"""
        try:
            logger.info(f"Loading MLX model: {self.model_name}")
            logger.info("This may take a few minutes on first run while downloading...")
            
            self.model, self.tokenizer = load(self.model_name)
            
            logger.info("✓ MLX model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load MLX model: {e}")
            raise
    
    def extract(self, email_data):
        """Extract receipt data from email"""
        try:
            logger.info(f"Extracting data from: {email_data.get('subject')}")
            
            # Prepare the prompt
            system_prompt = self.config.get('system_prompt', '')
            extraction_prompt = self.config.get('extraction_prompt', '')
            
            # Combine email content
            email_content = f"""
Subject: {email_data.get('subject')}
From: {email_data.get('from')}
Date: {email_data.get('date')}

Email Body:
{email_data.get('body', '')[:4000]}
"""  # Limit email body length to avoid context overflow
            
            # Generate response using MLX
            response = self._generate_response(system_prompt, extraction_prompt, email_content)
            
            if not response:
                logger.error("No response from model")
                return None
            
            # Parse JSON response
            receipt_data = self._parse_response(response)

            if receipt_data:
                # Validate and adjust confidence based on price consistency
                receipt_data = self._validate_and_adjust_confidence(receipt_data)

                logger.info(f"Extracted {len(receipt_data.get('items', []))} items "
                          f"with confidence {receipt_data.get('confidence', 0):.2f}")

            return receipt_data
            
        except Exception as e:
            logger.error(f"Error extracting receipt data: {e}", exc_info=True)
            return None
    
    def _generate_response(self, system_prompt, user_prompt, content):
        """Generate response using MLX"""
        try:
            # Format the prompt based on the model's chat template
            # Most instruction models use a similar format
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\n{content}"}
            ]
            
            # Apply chat template if available
            if hasattr(self.tokenizer, 'apply_chat_template'):
                prompt = self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                # Fallback to simple concatenation
                prompt = f"{system_prompt}\n\n{user_prompt}\n\n{content}"
            
            logger.debug(f"Generating response (max {self.max_tokens} tokens)...")
            
            # Generate using MLX
            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=self.max_tokens,
                verbose=False
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return None
    
    def _parse_response(self, response):
        """Parse AI response and extract JSON"""
        try:
            # Clean up response - remove prompt echo if present
            # MLX-LM sometimes includes the prompt in the response
            if "```json" in response.lower():
                # Extract from markdown code block
                start = response.lower().find("```json") + 7
                end = response.find("```", start)
                if end == -1:
                    end = len(response)
                json_str = response[start:end].strip()
            elif "{" in response and "}" in response:
                # Find JSON object
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
            else:
                # Try parsing entire response
                json_str = response.strip()
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Validate and clean
            return self._validate_receipt_data(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return None
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return None
    
    def _validate_receipt_data(self, data):
        """Validate and clean receipt data"""
        if not isinstance(data, dict):
            logger.warning("Response is not a dict")
            return None
        
        # Ensure items exist
        if 'items' not in data or not isinstance(data['items'], list):
            logger.warning("No items array found in response")
            return None
        
        if not data['items']:
            logger.warning("Empty items array")
            return None
        
        # Clean and validate items
        cleaned_items = []
        for item in data['items']:
            if not isinstance(item, dict):
                continue
            
            # Must have at least a name
            if 'name' not in item or not item['name']:
                continue
            
            # Create cleaned item with defaults
            cleaned_item = {
                'name': str(item.get('name', '')).strip(),
                'price': self._parse_number(item.get('price', 0)),
                'quantity': int(item.get('quantity', 1)) if item.get('quantity') else 1,
                'category': str(item.get('category', 'other')).lower().strip()
            }

            # Add optional fields if present
            if 'description' in item and item['description']:
                cleaned_item['description'] = str(item.get('description', '')).strip()

            if 'manufacturer' in item and item['manufacturer']:
                cleaned_item['manufacturer'] = str(item.get('manufacturer', '')).strip()

            if 'model_number' in item and item['model_number']:
                cleaned_item['model_number'] = str(item.get('model_number', '')).strip()

            if 'serial_number' in item and item['serial_number']:
                cleaned_item['serial_number'] = str(item.get('serial_number', '')).strip()

            cleaned_items.append(cleaned_item)
        
        if not cleaned_items:
            logger.warning("No valid items after cleaning")
            return None
        
        # Build cleaned receipt data
        cleaned_data = {
            'items': cleaned_items,
            'store': str(data.get('store', '')).strip(),
            'order_date': str(data.get('order_date', '')).strip(),
            'total': self._parse_number(data.get('total', 0)),
            'order_id': str(data.get('order_id', '')).strip(),
            'confidence': float(data.get('confidence', 0.8))
        }
        
        return cleaned_data
    
    def _parse_number(self, value):
        """Safely parse a number from various formats"""
        try:
            # Remove common currency symbols and commas
            if isinstance(value, str):
                value = value.replace('$', '').replace(',', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _validate_and_adjust_confidence(self, data):
        """Validate price consistency and adjust confidence score"""
        original_confidence = data.get('confidence', 0.8)
        adjusted_confidence = original_confidence
        confidence_reasons = []

        # Calculate sum of item prices
        items_total = sum(
            item.get('price', 0) * item.get('quantity', 1)
            for item in data.get('items', [])
        )

        receipt_total = data.get('total', 0)

        # Only validate if we have both values
        if items_total > 0 and receipt_total > 0:
            # Calculate percentage difference
            difference = abs(receipt_total - items_total)
            percent_diff = (difference / receipt_total) * 100

            # Adjust confidence based on price mismatch
            # Allow up to 20% difference for tax/shipping (no penalty)
            # Beyond that, reduce confidence
            if percent_diff > 20:
                # Reduce confidence proportionally
                penalty = min(0.3, (percent_diff - 20) / 100)
                adjusted_confidence = max(0.3, original_confidence - penalty)

                reason = (
                    f"Price mismatch: items=${items_total:.2f} vs total=${receipt_total:.2f} "
                    f"({percent_diff:.1f}% difference). Confidence reduced by {penalty:.2f}"
                )
                confidence_reasons.append(reason)
                logger.warning(reason)
            else:
                confidence_reasons.append(
                    f"Price validation passed: items=${items_total:.2f} vs total=${receipt_total:.2f} "
                    f"({percent_diff:.1f}% difference, within acceptable range)"
                )
        else:
            if items_total == 0:
                confidence_reasons.append("No item prices found for validation")
            if receipt_total == 0:
                confidence_reasons.append("No receipt total found for validation")

        data['confidence'] = adjusted_confidence
        data['_confidence_reasons'] = confidence_reasons  # Hidden field for debugging
        return data