#!/bin/bash

echo "============================================"
echo "  EPF E-Ink Add-on - Automated Test Suite"
echo "  ASPICE SWE.4 / SWE.5 Compliance"
echo "============================================"
echo ""

cd /app || exit 1

echo "Running pytest..."
echo ""

python3 -m pytest tests/ -v --tb=short --junitxml=/app/test-results.xml 2>&1 | tee /app/test-output.log

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "============================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ALL TESTS PASSED"
else
    echo "  SOME TESTS FAILED (exit code: $EXIT_CODE)"
fi
echo "============================================"

exit $EXIT_CODE
