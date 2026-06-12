# ============================================================
# Multi-stage Dockerfile — DevSecOps Pipeline Demo
# ============================================================
# TẠI SAO multi-stage: tách build dependencies (pip, gcc) khỏi runtime
# → image nhỏ hơn, ít CVE hơn, Trivy scan sạch hơn

# === Stage 1: BUILD ===
# python:3.13-slim thay vì python:3.13 — giảm ~600MB attack surface
FROM python:3.13-slim AS builder

WORKDIR /app
COPY requirements.txt .

# --no-cache-dir: không lưu pip cache trong image → giảm size
# --prefix=/install: cài vào thư mục riêng để COPY sang stage 2 sạch sẽ
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# === Stage 2: RUNTIME ===
FROM python:3.13-slim

# Metadata OCI — traceability khi inspect image
LABEL maintainer="dokhacduc29" \
      version="1.0" \
      description="DevSecOps Pipeline Demo - Day 10+16" \
      org.opencontainers.image.source="https://github.com/dokhacduc29/blackduck-pipeline"

# Non-root user — best practice
# TẠI SAO: nếu container bị exploit, attacker chỉ có quyền appuser, không phải root
# Trivy cũng flag "running as root" là misconfiguration
RUN useradd --create-home --shell /bin/bash appuser

# Cài curl cho HEALTHCHECK
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# COPY dependencies từ builder — chỉ lấy packages đã cài, không mang pip/cache
COPY --from=builder /install /usr/local

# COPY app code
COPY app.py .

# Biến môi trường — truyền version từ CI/CD pipeline
ENV APP_VERSION=dev

# Chuyển sang non-root TRƯỚC EXPOSE và CMD
USER appuser

EXPOSE 5000

# HEALTHCHECK — Docker Compose dùng để verify container healthy
# curl -f: fail silently (exit code 22) nếu HTTP error
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# gunicorn thay flask dev server — production-ready
# --workers 2: 2 worker processes, đủ cho demo
# --bind 0.0.0.0: listen tất cả interfaces
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
