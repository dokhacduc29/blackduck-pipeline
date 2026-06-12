#!/bin/bash
# smoke-test.sh — Verify image chứa đủ tools cần thiết
# TẠI SAO smoke test: nếu Java bị thiếu hoặc binary corrupt,
# phát hiện ở stage TEST thay vì khi deploy production.
# "Smoke test" = bật máy lên xem có bốc khói không, không test deep logic.

set -euo pipefail

IMAGE="${1:?Usage: smoke-test.sh <image:tag>}"

echo "=== Smoke Test: $IMAGE ==="
PASS=0
FAIL=0

# Hàm helper — chạy command trong container, check exit code
run_check() {
    local description="$1"
    local command="$2"

    echo -n "[CHECK] $description... "
    if docker run --rm --entrypoint="" "$IMAGE" sh -c "$command" > /dev/null 2>&1; then
        echo "PASS"
        ((PASS++))
    else
        echo "FAIL"
        ((FAIL++))
    fi
}

# ---- Checks ----
# Mỗi check verify 1 component critical
run_check "Java 17 installed" "java -version 2>&1 | grep -q '17'"
run_check "blackduck-scan binary exists" "which blackduck-scan"
run_check "blackduck-report binary exists" "which blackduck-report"
run_check "Python 3 available" "python3 --version"
run_check "curl available (for health checks)" "curl --version"
run_check "entrypoint.sh executable" "test -x /usr/local/bin/entrypoint.sh"
run_check "Non-root user can run" "id | grep -v 'uid=0'"
# Check cuối: verify entrypoint ít nhất print usage khi thiếu env vars
run_check "Entrypoint fails fast without env" \
    "! /usr/local/bin/entrypoint.sh 2>&1 | grep -q 'Missing required'"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

# Exit 1 nếu có bất kỳ check nào fail → pipeline stage TEST sẽ fail
if [ "$FAIL" -gt 0 ]; then
    echo "[FAIL] Smoke test failed — do NOT proceed to deploy"
    exit 1
fi
echo "[PASS] All checks passed"
