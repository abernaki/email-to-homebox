#!/bin/bash
# Test runner script for email-to-homebox

set -e

echo "=========================================="
echo "Email-to-Homebox Test Suite"
echo "=========================================="
echo ""

# Check if pytest is installed
if ! python -m pytest --version &> /dev/null; then
    echo "pytest not found. Installing..."
    pip install pytest pytest-cov
fi

# Parse arguments
FAST_ONLY=false
COVERAGE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            FAST_ONLY=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--fast] [--coverage]"
            echo "  --fast     Run only fast unit tests (skip MLX model loading)"
            echo "  --coverage Generate coverage report"
            exit 1
            ;;
    esac
done

# Build pytest command
CMD="python -m pytest tests/test_receipts.py"

if [ "$FAST_ONLY" = true ]; then
    echo "Running fast unit tests only..."
    CMD="$CMD -m unit"
else
    echo "Running all tests..."
fi

if [ "$COVERAGE" = true ]; then
    CMD="$CMD --cov=src --cov-report=term --cov-report=html"
fi

# Run tests
echo ""
echo "Running: $CMD"
echo ""
$CMD

# Show results
if [ "$COVERAGE" = true ]; then
    echo ""
    echo "Coverage report generated in htmlcov/index.html"
fi

echo ""
echo "=========================================="
echo "Tests completed!"
echo "=========================================="
