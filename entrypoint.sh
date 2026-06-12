#!/bin/bash
# entrypoint.sh — Gộp 3 bước scan pipeline vào 1 script
# TẠI SAO gộp: CI/CD job chạy 1 container = 1 unit of work.
# Tách 3 container riêng tốn overhead (pull image 3 lần, init 3 lần).
# Trade-off: debug khó hơn vì log lẫn nhau → giải quyết bằng prefix [STEP]

set -euo pipefail
# set -e: exit ngay khi có lệnh fail (không chạy tiếp khi scan lỗi)
# set -u: exit nếu dùng biến chưa khai báo (bắt typo)
# set -o pipefail: pipe fail nếu BẤT KỲ command nào trong pipe fail
#   Ví dụ: `cmd1 | cmd2` — không có pipefail, chỉ check exit code cmd2

echo "============================================"
echo "[INFO] BlackDuck Unified Scanner v3.0"
echo "[INFO] Started at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ---- Validate environment variables ----
# TẠI SAO validate trước: fail fast — báo lỗi rõ ràng thay vì
# chạy 10 phút scan rồi mới fail vì thiếu biến
REQUIRED_VARS=("BLACKDUCK_URL" "BLACKDUCK_TOKEN" "PROJECT_NAME")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "[ERROR] Missing required env var: $var"
        echo "[HINT] Set it in docker-compose.yml or CI/CD secrets"
        exit 1
    fi
done

# ---- Step 1: SCAN ----
echo ""
echo "[STEP 1/3] Running BlackDuck scan..."
# blackduck-scan: gọi Synopsys Detect để scan source code
# --project: tên project trên BlackDuck server
# --version: version string, dùng git SHA để traceable
blackduck-scan \
    --url "${BLACKDUCK_URL}" \
    --token "${BLACKDUCK_TOKEN}" \
    --project "${PROJECT_NAME}" \
    --version "${PROJECT_VERSION:-latest}" \
    2>&1 | tee /tmp/scan.log
# tee: vừa in ra stdout (CI/CD log) vừa lưu file (để upload artifact)

echo "[STEP 1/3] Scan completed."

# ---- Step 2: REPORT ----
echo ""
echo "[STEP 2/3] Generating vulnerability report..."
blackduck-report \
    --url "${BLACKDUCK_URL}" \
    --token "${BLACKDUCK_TOKEN}" \
    --project "${PROJECT_NAME}" \
    --version "${PROJECT_VERSION:-latest}" \
    --format json \
    --output /tmp/report.json \
    2>&1 | tee /tmp/report.log

echo "[STEP 2/3] Report saved to /tmp/report.json"

# ---- Step 3: PUSH to DefectDojo (optional) ----
# Chỉ push nếu DEFECTDOJO_URL được set — không bắt buộc
if [ -n "${DEFECTDOJO_URL:-}" ]; then
    echo ""
    echo "[STEP 3/3] Pushing results to DefectDojo..."
    blackduck-defectdojo \
        --url "${DEFECTDOJO_URL}" \
        --token "${DEFECTDOJO_TOKEN}" \
        --report /tmp/report.json \
        2>&1 | tee /tmp/dojo.log
    echo "[STEP 3/3] Push completed."
else
    echo ""
    echo "[STEP 3/3] SKIP — DEFECTDOJO_URL not set"
fi

echo ""
echo "============================================"
echo "[INFO] All steps completed at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
