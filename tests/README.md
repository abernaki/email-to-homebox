# Email-to-Homebox Test Suite

This test suite validates receipt extraction across different email formats and edge cases.

## Test Categories

### 1. HTML Extraction Tests (`TestHTMLExtraction`)
Tests the core HTML-to-text extraction functionality:
- **test_extract_pre_tags**: Validates that `<pre>` tags (containing receipt text) are prioritized
- **test_remove_noise_tags**: Ensures script, style, and meta tags are removed
- **test_multiple_pre_tags**: Tests handling of multiple receipt sections

### 2. Receipt Type Tests (`TestReceiptTypes`)
Tests real-world receipt formats:
- **test_best_buy_receipt**: Non-multipart HTML with embedded receipt in `<pre>` tag
- **test_square_no_items_receipt**: Square/vendor receipts with no item breakdown
- **test_zero_dollar_receipt**: Returns/refunds with $0.00 total (Nisolo case)

### 3. Email Body Extraction Tests (`TestEmailBodyExtraction`)
Tests email parsing logic:
- Multipart vs non-multipart emails
- HTML vs plain text selection
- Content type detection

### 4. Edge Cases (`TestEdgeCases`)
Tests error handling:
- **test_garbled_ocr_detection**: Detects and flags poor OCR quality
- **test_pdf_extraction_failed**: Handles failed PDF extraction

## Running Tests

### Install pytest
```bash
pip install pytest pytest-cov
```

### Run all tests
```bash
pytest tests/test_receipts.py -v
```

### Run specific test class
```bash
pytest tests/test_receipts.py::TestHTMLExtraction -v
```

### Run with coverage
```bash
pytest tests/test_receipts.py --cov=src --cov-report=html
```

### Run in CI/CD
```bash
pytest tests/test_receipts.py --junitxml=test-results.xml
```

## Test Data

### Receipt Types Covered

| Type | Example | Expected Result | Notes |
|------|---------|-----------------|-------|
| Best Buy | HTML with `<pre>` receipt | Items extracted | Non-multipart HTML email |
| Square | "Custom Amount × 1" | `no_items_found` | No product breakdown |
| Nisolo | $0.00 total | `no_items_found` | Return/refund |
| Garbled OCR | Random characters | `manual_review` | >15% noise ratio |
| Failed PDF | PDF attachment, no text | `manual_review` | PDF extraction failed |

## Adding New Tests

1. Create a new test method in the appropriate test class
2. Use descriptive names: `test_<scenario>_<expected_result>`
3. Add docstrings explaining the test case
4. Update this README with the new test

### Example:
```python
def test_new_receipt_format(self, extractor):
    """Test receipts from NewStore with embedded images"""
    email_data = {
        'subject': 'NewStore Receipt',
        'body': '...'
    }

    result = extractor.extract(email_data)

    assert result is not None
    assert len(result['items']) > 0
```

## CI Integration

### GitHub Actions Example
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov

    - name: Run tests
      run: pytest tests/test_receipts.py --junitxml=test-results.xml --cov=src

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Known Issues

1. **MLX Model Loading**: Tests that use `ReceiptExtractor` will download the model on first run (~4GB)
2. **Test Isolation**: Some tests share the same MLX model instance for performance
3. **Email Fetching**: Live email tests require valid IMAP credentials in `.env`

## Future Improvements

- [ ] Mock MLX model for faster unit tests
- [ ] Add fixture files for common receipt types
- [ ] Test image extraction functionality
- [ ] Add performance benchmarks
- [ ] Test concurrent processing
