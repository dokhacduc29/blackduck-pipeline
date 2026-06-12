# ============================================================
# Stage 1: EXTRACT — Lấy scan tools từ image blackduck gốc
# ============================================================
# TẠI SAO 2 stage: blackduck:latest = 4.5GB chứa mọi thứ (Synopsys Detect,
# Java, Python, scan tools). Mình CHỈ cần vài binary scan, không cần cả 4.5GB.
# Multi-stage build cho phép "cherry-pick" file cần thiết → image cuối nhỏ hơn 6x.
FROM ghcr.io/dokhacduc29/blackduck:latest AS extractor

# Không cần RUN gì ở stage này — chỉ dùng làm source để COPY

# ============================================================
# Stage 2: BUILD — Image chạy thật, base = blackduck-dojo
# ============================================================
# TẠI SAO blackduck-dojo làm base thay vì blackduck?
# - blackduck-dojo (331MB) đã có Python 3 + DefectDojo client
# - blackduck (4.5GB) có thừa nhiều thứ không cần
# - Trade-off: dojo thiếu Java → mình thêm vào (~200MB)
# - Kết quả: 700MB vs 4.5GB, giảm 85% attack surface
FROM ghcr.io/dokhacduc29/blackduck-dojo:latest

# ---- Metadata (OCI standard labels) ----
# TẠI SAO dùng LABEL: traceability — khi ai đó inspect image,
# biết ngay ai build, version nào, từ repo nào
LABEL maintainer="dokhacduc29" \
      version="3.0" \
      description="BlackDuck Unified Scanner - build+scan+report+push" \
      org.opencontainers.image.source="https://github.com/dokhacduc29/blackduck-pipeline"

# ---- Cài Java 17 (Synopsys Detect cần JRE) ----
# TẠI SAO Java 17 không phải 21: Synopsys Detect 9.x chỉ certify Java 11/17.
# TẠI SAO --no-install-recommends: giảm ~100MB package phụ không cần
# TẠI SAO rm -rf /var/lib/apt: xóa apt cache trong cùng RUN layer
#   → không tạo layer trung gian chứa cache → giảm image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless curl && \
    rm -rf /var/lib/apt/lists/*

# ---- Copy scan tools từ Stage 1 ----
# COPY --from=extractor: lấy file từ stage "extractor", không phải từ build context
# Chỉ copy đúng 3 binary cần thiết, không copy cả /opt
COPY --from=extractor /opt/blackduck/bin/blackduck-scan /usr/local/bin/blackduck-scan
COPY --from=extractor /opt/blackduck/bin/blackduck-report /usr/local/bin/blackduck-report

# ---- Copy entrypoint script ----
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# chmod +x: đảm bảo script executable,
# một số OS/git config có thể strip execute bit khi checkout
RUN chmod +x /usr/local/bin/entrypoint.sh

# ---- Health check ----
# Docker Compose và orchestrators dùng HEALTHCHECK để biết container sống hay chết
# CMD kiểm tra Java có chạy được không — nếu JRE corrupt, container = unhealthy
# --interval=30s: check mỗi 30 giây
# --timeout=5s: nếu check mất >5s → fail
# --retries=3: fail 3 lần liên tiếp → unhealthy
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD java -version 2>&1 || exit 1

# ---- Entrypoint ----
# ENTRYPOINT vs CMD:
# ENTRYPOINT = binary luôn chạy, CMD = default args có thể override
# Ở đây dùng ENTRYPOINT vì container này CHỈ làm 1 việc: scan
ENTRYPOINT ["entrypoint.sh"]
