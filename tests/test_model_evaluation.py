"""Local-only correctness tests for the synthetic Ollama comparison."""

import unittest

from run_model_evaluation import score_extraction


class ModelEvaluationTests(unittest.TestCase):
    def test_scores_expected_synthetic_receipt(self):
        result = score_extraction({
            'store': 'Example Shop',
            'order_id': '80421',
            'order_date': '2026-09-29T00:00:00Z',
            'total': 53.99,
            'items': [{'name': 'USB-C Travel Hub', 'price': 49.99, 'quantity': 1}],
        })

        self.assertTrue(result['all_fields_correct'])
        self.assertTrue(all(result['fields'].values()))

    def test_detects_wrong_price_and_item_name(self):
        result = score_extraction({
            'store': 'Example Shop',
            'order_id': '80421',
            'order_date': '2026-09-29',
            'total': 53.99,
            'items': [{'name': 'USB-C Hub', 'price': 39.99, 'quantity': 1}],
        })

        self.assertFalse(result['all_fields_correct'])
        self.assertFalse(result['fields']['item_name'])
        self.assertFalse(result['fields']['item_price'])


if __name__ == '__main__':
    unittest.main()
