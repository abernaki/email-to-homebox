"""
Receipt Extractor - Ollama Implementation
Uses Ollama HTTP API for local inference
"""

import os
import json
import logging
import re
import html
import quopri
import time
import requests as http_requests

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434"


class ReceiptExtractor:
    """Extracts receipt data using Ollama API"""

    def __init__(self, config):
        self.config = config
        self.model_name = os.getenv('AI_MODEL', 'qwen2.5:7b')
        self.temperature = float(os.getenv('AI_TEMPERATURE', '0.1'))
        self.max_tokens = int(os.getenv('AI_MAX_TOKENS', '2048'))
        self.ollama_host = os.getenv('OLLAMA_HOST', _DEFAULT_OLLAMA_HOST).rstrip('/')
        self.last_response_metrics = {}

        self._check_connection()

    def _check_connection(self):
        """Verify Ollama is reachable and warn if model is missing"""
        try:
            response = http_requests.get(f"{self.ollama_host}/api/tags", timeout=10)
            response.raise_for_status()
            available = [m['name'] for m in response.json().get('models', [])]
            logger.info(f"Connected to Ollama at {self.ollama_host}")
            base_name = self.model_name.split(':')[0]
            if not any(base_name in m for m in available):
                logger.warning(
                    f"Model '{self.model_name}' not found in Ollama. "
                    f"Run: ollama pull {self.model_name}"
                )
        except Exception as e:
            logger.error(f"Cannot reach Ollama at {self.ollama_host}: {e}")
            raise

    def _clean_email_text(self, text):
        if not text:
            return text

        try:
            if '=3D' in text or '=C3' in text or '=20' in text:
                text_bytes = text.encode('utf-8', errors='ignore')
                decoded_bytes = quopri.decodestring(text_bytes)
                text = decoded_bytes.decode('utf-8', errors='ignore')
                logger.debug("Decoded quoted-printable encoding in email")

            if '&' in text:
                text = html.unescape(text)
                logger.debug("Decoded HTML entities in email")

            text = re.sub(r'=\s*\n', '', text)
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            lines = [line.strip() for line in text.split('\n')]
            text = '\n'.join(lines)

            return text

        except Exception as e:
            logger.warning(f"Error cleaning email text: {e}")
            return text

    def extract(self, email_data, options=None):
        """Extract receipt data from email"""
        try:
            logger.info(f"Extracting data from: {email_data.get('subject')}")

            raw_body = email_data.get('body', '')
            cleaned_body = self._clean_email_text(raw_body)

            if '--- OCR from Image' in cleaned_body:
                ocr_start = cleaned_body.find('--- OCR from Image')
                ocr_text = cleaned_body[ocr_start:ocr_start+500]

                suspicious_chars = sum(1 for c in ocr_text if c in '{}[]#*~^|\\@')
                total_chars = len(ocr_text.replace('\n', '').replace(' ', ''))

                if total_chars > 50 and suspicious_chars / total_chars > 0.15:
                    logger.warning("OCR appears to have produced garbled text (high noise ratio)")
                    return {'_manual_review': True, '_reason': 'garbled_ocr'}

            pdf_text = email_data.get('pdf_text')
            if 'pdf_data' in email_data and not pdf_text:
                logger.error("PDF attachment found but text extraction failed - marking for manual review")
                return {'_manual_review': True, '_reason': 'pdf_extraction_failed'}

            full_content = cleaned_body
            if pdf_text:
                logger.info("Using PDF text for extraction (prioritized over email body)")
                full_content = f"--- PDF Receipt Content ---\n{pdf_text}\n\n--- Email Body ---\n{cleaned_body[:3000]}"

            system_prompt = self.config.get('system_prompt', '')
            extraction_prompt = self.config.get('extraction_prompt', '')

            email_content = f"""
Subject: {email_data.get('subject')}
From: {email_data.get('from')}
Date: {email_data.get('date')}

Email Body:
{full_content[:8000]}
"""

            response = self._generate_response(
                system_prompt, extraction_prompt, email_content, options=options
            )

            if not response:
                logger.error("No response from model")
                return None

            logger.debug(f"Raw LLM response (first 1000 chars): {response[:1000]}")

            receipt_data = self._parse_response(response)

            if receipt_data:
                logger.debug(f"Parsed {len(receipt_data.get('items', []))} items from response")

            if receipt_data:
                receipt_data = self._validate_and_adjust_confidence(receipt_data)
                logger.info(f"Extracted {len(receipt_data.get('items', []))} items "
                            f"with confidence {receipt_data.get('confidence', 0):.2f}")

            return receipt_data

        except Exception as e:
            logger.error(f"Error extracting receipt data: {e}", exc_info=True)
            return None

    def _generate_response(self, system_prompt, user_prompt, content, options=None):
        """Generate response using Ollama /api/chat"""
        try:
            self.last_response_metrics = {}
            request_options = {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            }
            request_options.update(options or {})
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{user_prompt}\n\n{content}"}
                ],
                "stream": False,
                "options": request_options
            }

            logger.debug(f"Sending request to Ollama (max {self.max_tokens} tokens)...")
            started_at = time.perf_counter()
            response = http_requests.post(
                f"{self.ollama_host}/api/chat",
                json=payload,
                timeout=300,
            )
            client_wall_seconds = time.perf_counter() - started_at
            response.raise_for_status()
            result = response.json()
            self.last_response_metrics = {
                'client_wall_seconds': client_wall_seconds,
                **{
                    name: result[name]
                    for name in (
                        'total_duration',
                        'load_duration',
                        'prompt_eval_count',
                        'prompt_eval_duration',
                        'eval_count',
                        'eval_duration',
                    )
                    if name in result
                }
            }
            return result['message']['content']

        except http_requests.Timeout:
            logger.error("Ollama request timed out after 300s")
            return None
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return None

    def _parse_response(self, response):
        """Parse AI response and extract JSON"""
        try:
            if "```json" in response.lower():
                start = response.lower().find("```json") + 7
                end = response.find("```", start)
                if end == -1:
                    end = len(response)
                json_str = response[start:end].strip()
            elif "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
            else:
                json_str = response.strip()

            data = json.loads(json_str)
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

        if 'items' not in data or not isinstance(data['items'], list):
            logger.warning("No items array found in response")
            return None

        if not data['items']:
            logger.warning("Empty items array - receipt has no line items")
            logger.debug(f"Full response data: {data}")
            return {'_no_items_found': True, 'store': data.get('store'), 'total': data.get('total')}

        cleaned_items = []
        for item in data['items']:
            if not isinstance(item, dict):
                continue

            if 'name' not in item or not item['name']:
                continue

            cleaned_item = {
                'name': str(item.get('name', '')).strip(),
                'price': self._parse_number(item.get('price', 0)),
                'quantity': int(item.get('quantity', 1)) if item.get('quantity') else 1,
                'category': str(item.get('category', 'other')).lower().strip()
            }

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

        items_total = sum(
            item.get('price', 0) * item.get('quantity', 1)
            for item in data.get('items', [])
        )
        receipt_total = data.get('total', 0)

        if items_total > 0 and receipt_total > 0:
            difference = abs(receipt_total - items_total)
            percent_diff = (difference / receipt_total) * 100

            if percent_diff > 20:
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
        data['_confidence_reasons'] = confidence_reasons
        return data

    def _detect_hallucinations(self, data, email_data):
        """
        Detect potential AI hallucinations and adjust confidence accordingly.
        """
        confidence = data.get('confidence', 0.8)
        confidence_reasons = data.get('_confidence_reasons', [])

        food_merchant_keywords = [
            'cafe', 'coffee', 'restaurant', 'bar', 'bistro', 'kitchen',
            'grill', 'deli', 'bakery', 'burger', 'pizza', 'taco', 'burrito',
            'wine', 'brewery', 'pub', 'lounge', 'station llc', 'via square'
        ]

        generic_product_names = [
            'wireless earbuds', 'smartwatch', 'laptop', 'tablet', 'headphones',
            'charger', 'phone case', 'speaker', 'keyboard', 'mouse'
        ]

        store_name = data.get('store', '').lower()
        is_food_merchant = any(keyword in store_name for keyword in food_merchant_keywords)

        hallucination_score = 0
        hallucination_indicators = []

        for item in data.get('items', []):
            item_name = item.get('name', '').lower()
            category = item.get('category', '').lower()
            manufacturer = str(item.get('manufacturer', '')).strip()
            model_number = str(item.get('model_number', '')).strip()
            description = item.get('description', '').lower()

            if any(generic_name in item_name for generic_name in generic_product_names):
                hallucination_score += 0.3
                hallucination_indicators.append(f"Generic product name detected: '{item.get('name')}'")

            na_values = ['n/a', 'not available', 'unknown', 'none', '']
            if manufacturer.lower() in na_values and model_number.lower() in na_values:
                hallucination_score += 0.2
                hallucination_indicators.append(f"No manufacturer/model details for '{item.get('name')}'")

            if is_food_merchant and category == 'electronics':
                hallucination_score += 0.4
                hallucination_indicators.append(
                    f"Electronics category '{item.get('name')}' from food merchant '{data.get('store')}'"
                )

            generic_descriptions = [
                'wireless earbuds with bluetooth connectivity',
                'smartwatch with fitness tracking',
                'laptop computer',
                'wireless headphones with bluetooth'
            ]
            if any(generic_desc in description for generic_desc in generic_descriptions):
                hallucination_score += 0.2
                hallucination_indicators.append(f"Generic description for '{item.get('name')}'")

        if hallucination_score > 0:
            penalty = min(0.5, hallucination_score)
            original_confidence = confidence
            confidence = max(0.3, confidence - penalty)

            reason = (
                f"Potential hallucination detected (score: {hallucination_score:.2f}). "
                f"Confidence reduced from {original_confidence:.2f} to {confidence:.2f}. "
                f"Indicators: {'; '.join(hallucination_indicators)}"
            )
            confidence_reasons.append(reason)
            logger.warning(reason)

        data['confidence'] = confidence
        data['_confidence_reasons'] = confidence_reasons
        data['_hallucination_score'] = hallucination_score
        data['_hallucination_indicators'] = hallucination_indicators
        return data
