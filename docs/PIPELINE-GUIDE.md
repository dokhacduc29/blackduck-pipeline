# CI/CD Pipeline Guide — AI Trend Agent

> Line-by-line giải thích toàn bộ pipeline, từ kiến trúc đến từng config.
> Day 11-16 deliverable.

---

## 1. Kiến trúc tổng quan

```
.github/workflows/
├── ci-cd.yml       ← Orchestrator: điều phối flow, không chứa logic
├── _build.yml      ← Reusable: build Docker image + push GHCR
├── _test.yml       ← Reusable: pytest + smoke test container
├── _scan.yml       ← Reusable: Trivy vulnerability scan + reports
└── _deploy.yml     ← Reusable: deploy to any environment
```

**Tại sao tách reusable workflow?**

- **DRY**: Deploy logic giống nhau cho dev/staging/prod → viết 1 lần, gọi 3 lần với params khác nhau.
- **Tái sử dụng**: Project khác cùng pattern (Docker + GHCR) chỉ cần copy `_build.yml` và đổi `image_name`.
- **Least privilege**: Mỗi workflow tự khai báo `permissions` tối thiểu. `_test.yml` chỉ cần `read`, không cần `write`.
- **Testable**: Có thể test từng workflow riêng lẻ bằng `workflow_dispatch`.

**Trade-off so với monolith pipeline:**

| | Monolith (1 file) | Reusable (5 files) |
|---|---|---|
| Đơn giản | ✅ Dễ đọc | ❌ Nhiều file, phải navigate |
| Tái sử dụng | ❌ Copy-paste | ✅ `uses: ./.github/workflows/_x.yml` |
| Permissions | ❌ Global cho tất cả jobs | ✅ Per-workflow least-privilege |
| Debug | ✅ Scroll 1 file | ❌ Phải mở đúng file |

---

## 2. Flow thực thi

```
push/PR to main
      │
      ▼
   [BUILD] ──────────────────────────┐
      │                              │
      ├──────────┐                   │
      ▼          ▼                   │
   [TEST]     [SCAN]    ← song song │
      │          │                   │
      └────┬─────┘                   │
           ▼                         │
      [DEPLOY-DEV] ← auto           │
           │                         │
           ▼                         │
      [DEPLOY-STAGING] ← auto, main only
           │
           ▼
      [DEPLOY-PROD] ← MANUAL APPROVAL
```

**Job dependencies (needs):**

- `test` needs `build` → cần image để smoke test
- `scan` needs `build` → cần image để scan CVE
- `deploy-dev` needs `[build, test, scan]` → chỉ deploy khi cả test + scan pass
- `deploy-staging` needs `[build, deploy-dev]` → dev phải pass trước
- `deploy-prod` needs `[build, deploy-staging]` → staging phải pass trước

**Tại sao test và scan song song?**

Cả 2 chỉ cần image từ build, không phụ thuộc nhau. Chạy song song tiết kiệm ~1-2 phút. Trade-off: tốn 2 runner slot cùng lúc (free plan có 20 concurrent jobs → không vấn đề).

---

## 3. Giải thích từng Reusable Workflow

### 3.1 _build.yml — Build & Push Image

**Inputs/Outputs:**

```yaml
inputs:
  image_name: "ghcr.io/user/app"   # Caller truyền vào
  dockerfile: "./Dockerfile"        # Mặc định root
  context: "."                       # Build context

outputs:
  image_tag: "abc1234"              # Commit SHA short — traceability
  image_digest: "sha256:..."        # Pin chính xác image
```

**Key decisions:**

- **Buildx**: Docker's next-gen builder. Hỗ trợ multi-platform (ARM64 nếu cần), advanced caching.
- **GHA cache** (`cache-from: type=gha`): Dùng GitHub Actions cache backend (~10GB free). Khi code không đổi, layer cache hit → build từ 2 phút xuống 10 giây.
- **`mode=max`**: Cache mọi intermediate layer, không chỉ final stage. Tốn cache space nhưng rebuild nhanh hơn nhiều.
- **metadata-action**: Auto-generate tags theo convention. `type=sha` = commit SHA (traceability), `latest` chỉ trên main.

### 3.2 _test.yml — Unit + Smoke Tests

**Key decisions:**

- **pip cache** (`actions/cache@v4`): Cache pip packages giữa các run. Key = hash của `requirements.txt` → invalidate khi deps thay đổi.
- **Smoke test**: Chạy container thật, verify bằng `python -c` (không dùng `sh -c` vì python:3.13-slim thiếu shell utils).

**Smoke test checks:**

1. Python 3.13 available
2. `main.py` exists tại đúng path
3. Production deps installed (httpx, dotenv, supabase)
4. Domain models importable
5. Non-root user (security)
6. Data directory writable

### 3.3 _scan.yml — Trivy Vulnerability Scan

**Key decisions:**

- **`ignore-unfixed: true`**: Chỉ block CVE đã có patch. CVE mà Debian upstream chưa release fix → không block pipeline. Lý do: em không thể fix perl-base CVE nếu Debian chưa patch.
- **3 output formats**: Table (human-readable trong logs), SARIF (GitHub Security tab), JSON (machine-readable archive).
- **`continue-on-error` cho SARIF upload**: Private repo free plan không có GitHub Advanced Security → step warning nhưng không fail pipeline.
- **`retention-days: 30`**: Giữ artifact 30 ngày cho audit trail. Trade-off: nhiều hơn tốn storage (500MB free), ít hơn mất traceability.

### 3.4 _deploy.yml — Deploy to Environment

**Key decisions:**

- **`environment` input**: Cùng 1 workflow deploy được dev, staging, prod. Caller chọn environment → GitHub apply đúng protection rules.
- **Explicit secrets**: `secrets: inherit` nguy hiểm (leak secrets không cần thiết). Thay vào đó, list từng secret cần dùng.
- **Health check verification**: Sau `docker compose up --wait`, kiểm tra lại `docker inspect` health status. Belt-and-suspenders approach.
- **Rollback**: `if: failure()` → tự động `docker compose down` nếu deploy fail. Không rollback về version cũ (cần state management phức tạp hơn), chỉ dọn sạch failed deployment.

---

## 4. Multi-Environment Strategy

| Environment | Trigger | Approval | Mục đích |
|---|---|---|---|
| **dev** | Mọi push/PR | Auto | Verify deploy logic works |
| **staging** | Push to main | Auto | Final verification trước prod |
| **production** | Push to main | **Manual** | Live deployment |

**Setup GitHub Environments:**

1. Repo → Settings → Environments → New environment
2. Tạo 3 environments: `dev`, `staging`, `production`
3. `production` → Required reviewers → thêm reviewer
4. `production` → Deployment branches → Restrict to `main`
5. Optional: Wait timer (VD: 5 phút) cho production

**Tại sao 3 environments thay vì 1?**

- **dev**: Catch deploy bugs sớm (VD: healthcheck config sai, missing env var).
- **staging**: Mirror production. Nếu staging pass → prod sẽ pass.
- **production**: Manual gate = last line of defense. Reviewer verify staging OK trước khi approve.

---

## 5. Security Hardening

### 5.1 Permissions (Least Privilege)

```yaml
# KHÔNG BAO GIỜ dùng:
permissions: write-all  # ← DANGEROUS: cho toàn quyền

# Thay vào đó — khai báo chính xác:
permissions:
  contents: read          # Chỉ đọc source code
  packages: write         # Push image (chỉ build cần)
  security-events: write  # Upload SARIF (chỉ scan cần)
```

Mỗi reusable workflow tự khai báo permissions tối thiểu. `_test.yml` chỉ cần `read` — nếu bị compromise, attacker không thể push image hay sửa code.

### 5.2 Secret Management

```yaml
# Secrets truyền EXPLICITLY — không dùng `secrets: inherit`
secrets:
  NEWS_API_KEY: ${{ secrets.NEWS_API_KEY }}
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

**Tại sao không `secrets: inherit`?**

`inherit` truyền TẤT CẢ secrets cho reusable workflow. Nếu `_test.yml` bị compromise (VD: malicious dependency), attacker có thể đọc secrets mà test không cần (VD: SUPABASE_KEY). Explicit = chỉ truyền cái cần dùng.

### 5.3 Concurrency Control

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Nếu push 2 lần liên tiếp: pipeline cũ bị cancel, chỉ pipeline mới chạy. Tránh race condition: 2 deploy cùng lúc → container restart liên tục.

---

## 6. Caching Strategy

| Cache | Mechanism | Invalidation | Savings |
|---|---|---|---|
| Docker layers | `type=gha` (GitHub Actions cache) | Dockerfile/code change | Build 2min → 10s |
| pip packages | `actions/cache@v4` | `requirements.txt` change | Install 25s → 3s |
| Trivy DB | Built-in trivy-action cache | Daily auto-update | Download 30s → 0s |

---

## 7. Troubleshooting

### Pipeline bị cancel giữa chừng
→ Kiểm tra concurrency: có push mới trong khi pipeline cũ chạy? `cancel-in-progress: true` sẽ kill pipeline cũ.

### Scan fail với CRITICAL CVE
→ Kiểm tra `ignore-unfixed`. Nếu CVE có fixed version → cần rebuild image với base image mới. Nếu chưa có fix → `ignore-unfixed: true` đã handle.

### Deploy fail healthcheck
→ Kiểm tra: container có crash không? (`docker compose logs`). Thường do thiếu env var hoặc API key invalid.

### SARIF upload fail "Resource not accessible"
→ Normal cho private repo free plan. `continue-on-error: true` đã handle. Upgrade GitHub plan hoặc chuyển public repo để dùng Security tab.

### Smoke test exit code 1 ngay check đầu tiên
→ Classic bash trap: `((VAR++))` return exit code 1 khi VAR=0. Dùng `VAR=$((VAR + 1))` thay thế.
