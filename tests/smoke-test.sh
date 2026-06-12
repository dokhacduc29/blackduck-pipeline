#!/bin/bash
# smoke-test.sh — Verify AI Trend Agent image hoạt động
set -euo pipefail

IMAGE="${1:?Usage: smoke-test.sh <image:tag>}"

echo "=== Smoke Test: $IMAGE ==="
PASS=0
FAIL=0

run_check() {
    local desc="$1"
    local cmd="$2"
    echo -n "[CHECK] $desc... "
    if docker run --rm --entrypoint="" "$IMAGE" sh -c "$cmd" > /dev/null 2>&1; then
        echo "PASS"
        ((PASS++))
    else
        echo "FAIL"
        ((FAIL++))
    fi
}

# ---- Checks ----
run_check "Python 3.13 available" "python --version 2>&1 | grep '3.13'"
run_check "main.py exists" "test -f /app/ai_trend_agent.WebApi/main.py"
run_check "httpx installed" "python -c 'import httpx'"
run_check "dotenv installed" "python -c 'import dotenv'"
run_check "Non-root user" "id | grep -v 'uid=0'"
run_check "Data dir writable" "touch /app/data/test && rm /app/data/test"
run_check "PYTHONPATH set" "python -c 'from models import Article'"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && echo "[FAIL] Smoke test failed" && exit 1
echo "[PASS] All checks passed"
