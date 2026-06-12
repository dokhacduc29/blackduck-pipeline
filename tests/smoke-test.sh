#!/bin/bash
# smoke-test.sh — Verify image hoạt động đúng trước khi deploy
set -euo pipefail

IMAGE="${1:?Usage: smoke-test.sh <image:tag>}"

echo "=== Smoke Test: $IMAGE ==="
PASS=0
FAIL=0

run_check() {
    local description="$1"
    local command="$2"
    echo -n "[CHECK] $description... "
    if eval "$command" > /dev/null 2>&1; then
        echo "PASS"
        ((PASS++))
    else
        echo "FAIL"
        ((FAIL++))
    fi
}

# Chạy container background
CID=$(docker run -d --rm -p 5555:5000 "$IMAGE")
sleep 3  # Đợi gunicorn start

# ---- Checks ----
run_check "Container is running" "docker inspect $CID --format='{{.State.Running}}' | grep true"
run_check "Health endpoint returns 200" "curl -sf http://localhost:5555/health"
run_check "Health response has status=ok" "curl -sf http://localhost:5555/health | grep -q ok"
run_check "Root endpoint returns 200" "curl -sf http://localhost:5555/"
run_check "Non-root user" "docker exec $CID id | grep -v 'uid=0'"
run_check "Python available" "docker exec $CID python3 --version"

# Cleanup
docker stop "$CID" > /dev/null 2>&1 || true

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && echo "[FAIL] Smoke test failed" && exit 1
echo "[PASS] All checks passed"
