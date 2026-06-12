# =====================================================================
# Dockerfile — AI Trend Agent v3.1
# Multi-stage build: tách build deps khỏi runtime → image nhỏ, ít CVE
# =====================================================================

# ── STAGE 1: Builder — cài dependencies vào /install ──
FROM python:3.13-slim AS builder

WORKDIR /install

# Copy requirements trước → tận dụng Docker layer cache
# Khi requirements không đổi, Docker skip layer này → build nhanh hơn
COPY Backend/requirements.txt .

# Chỉ cài production deps (bỏ pytest, streamlit, pandas — không cần trong prod)
# --no-cache-dir: không lưu pip cache vào image → giảm ~50MB
# --prefix=/install: cài vào thư mục riêng để COPY sạch sang stage 2
RUN pip install --no-cache-dir --prefix=/install \
    httpx==0.28.1 \
    python-dotenv==1.2.2 \
    google-generativeai \
    supabase==2.11.0 \
    python-telegram-bot==21.9

# ── STAGE 2: Runtime — chỉ chứa những gì cần chạy ──
FROM python:3.13-slim AS runtime

LABEL maintainer="dokhacduc29" \
      version="3.1.0" \
      description="AI Trend Agent - automated AI news pipeline" \
      org.opencontainers.image.source="https://github.com/dokhacduc29/blackduck-pipeline"

# Non-root user — nếu container bị exploit, attacker chỉ có quyền appuser
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup --no-create-home appuser

WORKDIR /app

# Copy packages từ builder (chỉ production deps, không có pytest/streamlit)
COPY --from=builder /install /usr/local

# Copy source code
COPY --chown=appuser:appgroup Backend/ .

# Thư mục data cho runtime output (CSV fallback, AI cache)
RUN mkdir -p /app/data && chown appuser:appgroup /app/data

# Environment: non-secret defaults
# Secrets (API keys) inject qua CI/CD secrets hoặc K8s Secret
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/ai_trend_agent.Domain:/app/ai_trend_agent.Application:/app/ai_trend_agent.Infrastructure \
    TOPIC="Artificial Intelligence"

USER appuser

# Healthcheck — verify main.py tồn tại + Python runtime OK
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/ai_trend_agent.WebApi/main.py') else 1)"

CMD ["python", "ai_trend_agent.WebApi/main.py"]
