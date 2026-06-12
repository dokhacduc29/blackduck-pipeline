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
    if docker run --rm "$IMAGE" python -c "$cmd" > /dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

# ---- Checks ----
# Dùng python -c thay vì sh -c — python:3.13-slim có thể thiếu shell utils
run_check "Python 3.13 available" "import sys; assert sys.version_info[:2] == (3, 13)"
run_check "main.py exists" "import os; assert os.path.exists('/app/ai_trend_agent.WebApi/main.py')"
run_check "httpx installed" "import httpx"
run_check "dotenv installed" "import dotenv"
run_check "supabase installed" "import supabase"
run_check "models importable" "from models import Article"
run_check "Non-root user" "import os; assert os.getuid() != 0"
run_check "Data dir writable" "open('/app/data/_test','w').close(); import os; os.remove('/app/data/_test')"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && echo "[FAIL] Smoke test failed" && exit 1
echo "[PASS] All checks passed"
