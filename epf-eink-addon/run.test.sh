#!/bin/bash

echo "============================================"
echo "  EPF E-Ink Add-on - Automated Test Suite"
echo "  ASPICE SWE.4 / SWE.5 Compliance"
echo "============================================"
echo ""

cd /app || exit 1

# Report path; CI mounts a host directory and points this at it (EPF_JUNIT_XML) so the
# junit report survives the `docker run --rm` container. The default keeps local runs
# exactly as documented (TESTSPEC: the suite runs with --junitxml).
JUNIT_XML="${EPF_JUNIT_XML:-/app/test-results.xml}"

echo "Running pytest..."
echo ""

python3 -m pytest tests/ -v --tb=short --junitxml="$JUNIT_XML" 2>&1 | tee /app/test-output.log

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
