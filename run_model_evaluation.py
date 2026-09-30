#!/usr/bin/env python3
"""Serially evaluate selected Ollama models on the checked-in synthetic receipt."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'tests' / 'fixtures' / 'synthetic_receipt.json'
EXPECTED = {
    'store': 'EXAMPLE SHOP',
    'order_id': '80421',
    'order_date': '2026-09-29',
    'total': 53.99,
    'items': [{'name': 'USB-C Travel Hub', 'price': 49.99, 'quantity': 1}],
}

sys.path.insert(0, str(ROOT / 'src'))


def _normalize_text(value):
    return re.sub(r'[^a-z0-9]+', '', str(value).lower())


def score_extraction(receipt):
    """Compare model output with the synthetic fixture's known receipt facts."""
    if not isinstance(receipt, dict):
        return {'all_fields_correct': False, 'fields': {}}

    actual_items = receipt.get('items', [])
    expected_item = EXPECTED['items'][0]
    actual_item = actual_items[0] if isinstance(actual_items, list) and actual_items else {}
    if not isinstance(actual_item, dict):
        actual_item = {}
    fields = {
        'store': _normalize_text(receipt.get('store', '')) == _normalize_text(EXPECTED['store']),
        'order_id': _normalize_text(receipt.get('order_id', '')) == EXPECTED['order_id'],
        'order_date': str(receipt.get('order_date', ''))[:10] == EXPECTED['order_date'],
        'total': _matches_price(receipt.get('total'), EXPECTED['total']),
        'item_count': len(actual_items) == len(EXPECTED['items']) if isinstance(actual_items, list) else False,
        'item_name': _normalize_text(actual_item.get('name', '')) == _normalize_text(expected_item['name']),
        'item_price': _matches_price(actual_item.get('price'), expected_item['price']),
        'item_quantity': actual_item.get('quantity') == expected_item['quantity'],
    }
    return {'all_fields_correct': all(fields.values()), 'fields': fields}


def _matches_price(value, expected):
    try:
        return abs(float(value) - expected) <= 0.01
    except (TypeError, ValueError):
        return False


def evaluate_one(model_name, email_data, config, ollama_url, num_gpu):
    os.environ['OLLAMA_HOST'] = ollama_url
    os.environ['AI_MODEL'] = model_name
    from receipt_extractor_mlx import ReceiptExtractor

    extractor = ReceiptExtractor(config['ai'])
    options = {'num_gpu': num_gpu} if num_gpu is not None else None
    receipt = extractor.extract(email_data, options=options)
    if not receipt:
        return {
            'model': model_name,
            'requested_num_gpu': num_gpu,
            'status': 'extraction_failed',
            'correctness': score_extraction(None),
            'metrics': extractor.last_response_metrics,
        }

    if receipt.get('_manual_review'):
        status = 'manual_review'
    elif receipt.get('_no_items_found'):
        status = 'no_items'
    elif receipt.get('confidence', 0) < config['processing']['min_confidence']:
        status = 'low_confidence'
    else:
        status = 'extracted'

    metrics = dict(extractor.last_response_metrics)
    if metrics.get('eval_duration') and metrics.get('eval_count') is not None:
        metrics['generation_tokens_per_second'] = (
            metrics['eval_count'] * 1_000_000_000 / metrics['eval_duration']
        )
    return {
        'model': model_name,
        'requested_num_gpu': num_gpu,
        'status': status,
        'confidence': receipt.get('confidence'),
        'correctness': score_extraction(receipt),
        'metrics': metrics,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Serially compare Ollama tags using only the checked-in synthetic receipt. '
            'Never accesses IMAP or Homebox.'
        )
    )
    parser.add_argument('--ollama-url', required=True, help='Explicit reachable Ollama base URL')
    parser.add_argument('--models', required=True, nargs='+', help='Existing Ollama model tags to compare')
    parser.add_argument(
        '--num-gpu',
        type=int,
        help='Ollama GPU layers for every request; use 0 for CPU-only, omit for server default'
    )
    args = parser.parse_args(argv)
    if args.num_gpu is not None and args.num_gpu < 0:
        parser.error('--num-gpu must be zero or greater')
    if len(set(args.models)) != len(args.models):
        parser.error('--models must not contain duplicate tags')

    try:
        email_data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        config = yaml.safe_load((ROOT / 'config' / 'config.yml').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        parser.error(str(error))

    results = []
    for model_name in args.models:
        print(f'Evaluating {model_name} serially...', file=sys.stderr)
        try:
            result = evaluate_one(
                model_name, email_data, config, args.ollama_url, args.num_gpu
            )
        except Exception as error:
            result = {
                'model': model_name,
                'requested_num_gpu': args.num_gpu,
                'status': 'request_failed',
                'error_type': type(error).__name__,
            }
        results.append(result)

    print(json.dumps({
        'fixture': str(FIXTURE.relative_to(ROOT)),
        'requested_num_gpu': args.num_gpu,
        'placement': 'cpu_only' if args.num_gpu == 0 else (
            'requested_gpu_layers' if args.num_gpu is not None else 'server_default'
        ),
        'execution': 'serial; Ollama keep_alive defaults are unchanged',
        'results': results,
    }, indent=2))
    return 0 if all(result['status'] == 'extracted' for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
