# Testing Guide

## Quick Start

Run all tests:
```bash
./run_tests.sh
```

Run only fast unit tests (no MLX model loading):
```bash
./run_tests.sh --fast
```

Run with coverage:
```bash
./run_tests.sh --coverage
```

## Test Results Summary

### ✅ Unit Tests (Fast)
- **test_extract_pre_tags**: Validates `<pre>` tag prioritization ✓
- **test_remove_noise_tags**: Ensures script/style removal ✓
- **test_multiple_pre_tags**: Tests multiple receipt sections ✓

**Run time**: ~2 seconds

### ✅ Receipt Type Tests (Slow - loads MLX model)
- **test_best_buy_receipt**: Non-multipart HTML extraction ✓
- **test_square_no_items_receipt**: No item breakdown handling ✓
- **test_zero_dollar_receipt**: $0.00 return/refund handling ✓

**Run time**: ~30 seconds (first run downloads model)

### ✅ Edge Case Tests
- **test_garbled_ocr_detection**: Detects poor OCR quality ✓
- **test_pdf_extraction_failed**: Handles missing PDF text ✓

## What We Fixed Today

### 1. Best Buy Receipt Extraction Bug 🐛 → ✅
**Problem**: Best Buy receipts were failing with `extraction_failed`

**Root Cause**: Non-multipart HTML emails were treated as plain text, so raw HTML was passed to the LLM

**Fix** (src/email_fetcher.py:261-279):
```python
# Check content type for non-multipart emails
if content_type == 'text/html':
    html_body = extract_text_from_html(payload)
```

**Result**: Receipt text in `<pre>` tags now extracted first, 95% confidence!

### 2. Better Failure Categorization 🏷️

Now distinguishes between:
- `extraction_failed` - LLM/parsing errors
- `no_items_found` - Valid receipts with no line items (Square, returns)
- `manual_review` - Failed PDF extraction, garbled OCR
- `low_confidence` - Successful but uncertain extraction

### 3. HTML Extraction Improvements 🔧

Added `extract_text_from_html()` function that:
- Prioritizes `<pre>` tags (where receipts often live)
- Removes script, style, meta tags
- Puts structured content first

## Test Coverage

### Receipt Formats Tested
| Format | Email Type | Extraction | Status |
|--------|-----------|------------|--------|
| Best Buy | Non-multipart HTML | `<pre>` tag | ✅ Working |
| Square | Multipart | No items | ✅ Expected |
| Nisolo | Plain text | $0 total | ✅ Expected |
| J.Crew, Allbirds | Multipart | Standard | ✅ Working |
| Container Store | Image OCR | Garbled | ✅ Detected |
| Portland Mattress | PDF | Failed | ✅ Detected |

## Running Specific Tests

```bash
# Only HTML extraction tests
pytest tests/test_receipts.py::TestHTMLExtraction -v

# Only receipt type tests
pytest tests/test_receipts.py::TestReceiptTypes -v

# Only edge cases
pytest tests/test_receipts.py::TestEdgeCases -v

# Tests matching a keyword
pytest tests/test_receipts.py -k "best_buy" -v
```

## CI/CD Integration

### GitHub Actions Workflow
See `tests/README.md` for full GitHub Actions example

### Test Markers
- `@pytest.mark.unit` - Fast tests, no external dependencies
- `@pytest.mark.slow` - Tests that load MLX model
- `@pytest.mark.integration` - Tests requiring email server
- `@pytest.mark.edge_case` - Error handling tests

Run specific markers:
```bash
pytest -m unit  # Only unit tests
pytest -m "not slow"  # Skip slow tests
```

## Next Steps

To add new test cases:

1. Add test method to appropriate class in `tests/test_receipts.py`
2. Use descriptive names: `test_<scenario>_<expected>`
3. Mark with appropriate pytest marker
4. Update this document

## Verification

Run your full processing and all issues should be resolved:
```bash
source venv/bin/activate
python run_once.py
```

Expected results:
- Best Buy receipts: **SUCCESS** (items extracted)
- Square receipts: **no_items_found** (expected)
- Nisolo $0 receipts: **no_items_found** (expected)
