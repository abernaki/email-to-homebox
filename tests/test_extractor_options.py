"""Mocked Ollama request tests; these never contact an Ollama server."""

import sys
import types
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType('requests')
    requests.Timeout = RuntimeError
    requests.exceptions = types.SimpleNamespace(RequestException=RuntimeError)
    requests.get = Mock()
    requests.post = Mock()
    sys.modules['requests'] = requests
    try:
        from receipt_extractor_mlx import ReceiptExtractor
    finally:
        del sys.modules['requests']
else:
    from receipt_extractor_mlx import ReceiptExtractor

import receipt_extractor_mlx


class OllamaRequestTests(unittest.TestCase):
    def test_cpu_only_override_is_sent_and_metrics_are_exposed(self):
        extractor = ReceiptExtractor.__new__(ReceiptExtractor)
        extractor.ollama_host = 'http://ollama.example.test'
        extractor.model_name = 'synthetic-test-model'
        extractor.temperature = 0.1
        extractor.max_tokens = 512
        extractor.last_response_metrics = {}
        response = Mock()
        response.json.return_value = {
            'message': {'content': '{"items": []}'},
            'total_duration': 1_000_000_000,
            'load_duration': 100_000_000,
            'prompt_eval_count': 25,
            'prompt_eval_duration': 200_000_000,
            'eval_count': 10,
            'eval_duration': 500_000_000,
        }

        with patch.object(receipt_extractor_mlx.http_requests, 'post', return_value=response) as post:
            result = extractor._generate_response(
                'system', 'extract', 'synthetic receipt', options={'num_gpu': 0}
            )

        self.assertEqual(result, '{"items": []}')
        self.assertEqual(
            post.call_args.kwargs['json']['options'],
            {'temperature': 0.1, 'num_predict': 512, 'num_gpu': 0},
        )
        self.assertNotIn('keep_alive', post.call_args.kwargs['json'])
        self.assertEqual(extractor.last_response_metrics['total_duration'], 1_000_000_000)
        self.assertEqual(extractor.last_response_metrics['eval_count'], 10)
        self.assertGreaterEqual(extractor.last_response_metrics['client_wall_seconds'], 0)


if __name__ == '__main__':
    unittest.main()
