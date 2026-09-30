#!/usr/bin/env python3
"""Preview receipt extraction and Homebox item payloads without external writes."""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))

from homebox_mapping import map_to_homebox_item


def build_preview(email_data, extractor, config, location_id):
    """Extract and map one supplied message, without constructing a Homebox client."""
    receipt_data = extractor.extract(email_data)
    if not receipt_data:
        return {'status': 'extraction_failed', 'extracted': None, 'mapped_items': []}

    if receipt_data.get('_manual_review'):
        status = 'manual_review'
    elif receipt_data.get('_no_items_found'):
        status = 'no_items'
    elif receipt_data.get('confidence', 0) < config['processing']['min_confidence']:
        status = 'low_confidence'
    else:
        status = 'ready_for_review'

    mapped_items = []
    if status == 'ready_for_review':
        mapped_items = [
            map_to_homebox_item(item, receipt_data, config, location_id)
            for item in receipt_data.get('items', [])
        ]

    return {
        'status': status,
        'extracted': receipt_data,
        'mapped_items': mapped_items
    }


def main():
    parser = argparse.ArgumentParser(
        description='Extract and map a synthetic receipt using Ollama; never accesses email or Homebox.'
    )
    parser.add_argument('--input', required=True, type=Path, help='JSON file containing one synthetic email object')
    parser.add_argument('--ollama-url', required=True, help='Explicit Ollama base URL, for example http://localhost:11434')
    parser.add_argument('--model', required=True, help='Existing Ollama model tag, for example qwen2.5:14b')
    parser.add_argument('--config', type=Path, default=ROOT / 'config' / 'config.yml')
    parser.add_argument(
        '--location-id',
        default='DRY_RUN_LOCATION_ID',
        help='Payload placeholder only; no Homebox lookup or write is performed'
    )
    args = parser.parse_args()

    try:
        email_data = json.loads(args.input.read_text(encoding='utf-8'))
        config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        parser.error(str(error))

    if not isinstance(email_data, dict) or not isinstance(email_data.get('body'), str):
        parser.error('Input JSON must be an object containing a string "body" field')
    if not isinstance(config, dict) or 'ai' not in config or 'processing' not in config or 'homebox' not in config:
        parser.error('Config must contain ai, processing, and homebox sections')

    os.environ['OLLAMA_HOST'] = args.ollama_url
    os.environ['AI_MODEL'] = args.model
    from receipt_extractor_mlx import ReceiptExtractor

    preview = build_preview(email_data, ReceiptExtractor(config['ai']), config, args.location_id)
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0 if preview['status'] == 'ready_for_review' else 2


if __name__ == '__main__':
    raise SystemExit(main())
