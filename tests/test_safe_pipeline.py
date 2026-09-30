"""Synthetic pipeline tests using fake extraction and Homebox implementations."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))

from app import main as app_main
from app import handle_receipt_result
from app import process_receipt
from run_dry_run import build_preview
from homebox_errors import PartialEntityUpdateError
from unittest.mock import patch


class FakeExtractor:
    def __init__(self, receipt_data):
        self.receipt_data = receipt_data

    def extract(self, email):
        if not email['body'].startswith('EXAMPLE SHOP'):
            raise AssertionError('Expected the synthetic receipt fixture')
        return self.receipt_data


class FakeHomebox:
    def __init__(self):
        self.created_items = []

    def get_location_id_by_name(self, name):
        if name != 'Test Location':
            raise AssertionError(f'Unexpected location: {name}')
        return 'synthetic-location-id'

    def create_item(self, item_data):
        self.created_items.append(item_data)
        return {'id': 'synthetic-item-id'}


class PartialWriteHomebox(FakeHomebox):
    def __init__(self):
        super().__init__()
        self.create_attempts = []

    def create_item(self, item_data):
        self.create_attempts.append(item_data)
        raise PartialEntityUpdateError('synthetic-partial-entity')


class SafePipelineTests(unittest.TestCase):
    def setUp(self):
        self.email_data = json.loads(
            (ROOT / 'tests' / 'fixtures' / 'synthetic_receipt.json').read_text(encoding='utf-8')
        )
        self.receipt_data = {
            'items': [{
                'name': 'USB-C Travel Hub™',
                'price': 49.99,
                'quantity': 1,
                'category': 'electronics',
                'description': '7-port travel hub',
                'manufacturer': 'Example Brand',
                'model_number': 'HUB-7',
            }],
            'store': 'Example Shop',
            'order_date': '2026-09-29',
            'total': 53.99,
            'order_id': '80421',
            'confidence': 0.95,
        }
        self.config = {
            'ai': {},
            'homebox': {
                'default_location': 'Test Location',
                'category_map': {'electronics': 'Electronics'},
                'notes_template': 'Purchased from {store} on {date}. Order: {order_id}',
            },
            'processing': {
                'min_confidence': 0.7,
                'skip_consumables': False,
                'skip_non_physical': False,
                'save_processed': False,
                'enable_image_search': False,
                'label_ai_images': False,
            },
        }

    def test_preview_maps_synthetic_receipt_without_homebox(self):
        result = build_preview(
            self.email_data,
            FakeExtractor(self.receipt_data),
            self.config,
            'DRY_RUN_LOCATION_ID',
        )

        self.assertEqual(result['status'], 'ready_for_review')
        self.assertEqual(result['mapped_items'], [{
            'name': 'USB-C Travel Hub',
            'description': '7-port travel hub\n\nPurchased from Example Shop on 2026-09-29. Order: 80421',
            'quantity': 1,
            'locationId': 'DRY_RUN_LOCATION_ID',
            'purchasePrice': 49.99,
            'purchaseFrom': 'Example Shop',
            'purchaseTime': '2026-09-29',
            'manufacturer': 'Example Brand',
            'modelNumber': 'HUB-7',
        }])

    def test_pipeline_uses_fake_homebox(self):
        fake_homebox = FakeHomebox()

        result = process_receipt(
            self.email_data,
            FakeExtractor(self.receipt_data),
            fake_homebox,
            self.config,
        )

        self.assertEqual(result, {'status': 'success', 'items_added': 1})
        self.assertEqual(fake_homebox.created_items, [{
            'name': 'USB-C Travel Hub',
            'description': '7-port travel hub\n\nPurchased from Example Shop on 2026-09-29. Order: 80421',
            'quantity': 1,
            'locationId': 'synthetic-location-id',
            'purchasePrice': 49.99,
            'purchaseFrom': 'Example Shop',
            'purchaseTime': '2026-09-29',
            'manufacturer': 'Example Brand',
            'modelNumber': 'HUB-7',
        }])

    def test_daemon_requires_explicit_live_opt_in(self):
        with self.assertRaises(SystemExit) as result:
            app_main([])
        self.assertEqual(result.exception.code, 2)

    def test_partial_homebox_write_is_failed_and_saved_for_manual_review(self):
        homebox = PartialWriteHomebox()
        receipt_data = dict(self.receipt_data)
        receipt_data['items'] = self.receipt_data['items'] + [{
            'name': 'Second Synthetic Item',
            'price': 5.00,
            'quantity': 1,
            'category': 'electronics',
        }]
        with patch('app.save_failed_receipt') as save_failed:
            result = process_receipt(
                self.email_data,
                FakeExtractor(receipt_data),
                homebox,
                self.config,
            )

        self.assertEqual(result, {
            'status': 'partial_write',
            'reason': 'purchase_update_failed',
            'entity_id': 'synthetic-partial-entity',
        })
        save_failed.assert_called_once_with(
            self.email_data,
            'partial_homebox_write',
            receipt_data,
        )
        self.assertEqual(len(homebox.create_attempts), 1)

    def test_partial_write_routes_to_manual_review_folder(self):
        class FakeEmailFetcher:
            def __init__(self):
                self.moved = []

            def move_to_folder(self, uid, folder):
                self.moved.append((uid, folder))

        fetcher = FakeEmailFetcher()
        email_data = dict(self.email_data, uid=42)
        result = handle_receipt_result(
            {'status': 'partial_write', 'reason': 'purchase_update_failed'},
            email_data,
            fetcher,
            {'email': {'move_to_folder_on_low_confidence': 'Receipts/Manual Review'}},
        )

        self.assertEqual(result, {'moved_to': 'Receipts/Manual Review'})
        self.assertEqual(fetcher.moved, [(42, 'Receipts/Manual Review')])


if __name__ == '__main__':
    unittest.main()
