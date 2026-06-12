# ADR-001: CI/CD Pipeline Design Decisions

**Date:** 2026-06-12
**Status:** Accepted
**Author:** dokhacduc29

## Context

Xây dựng CI/CD pipeline production-grade cho BlackDuck Unified Scanner image,
tích hợp Trivy vulnerability scan, deploy bằng Docker Compose.

---

## Decision 1: GHCR thay vì Artifact passing cho image sharing

**Chosen:** Push image lên GHCR, các job pull từ GHCR
**Rejected:** docker save → upload-artifact → download-artifact → docker load

| Tiêu chí | GHCR | Artifact |
|----------|------|----------|
| Speed (700MB image) | ~2 phút (layer dedup) | ~5 phút (full tar upload/download) |
| Storage | Miễn phí (public), 500MB/tháng (private) | 500MB/repo miễn phí |
| Layer caching | Có (chỉ push layer thay đổi) | Không (luôn full tar) |
| Dùng ngoài pipeline | Có (docker pull từ bất kỳ đâu) | Không (chỉ trong workflow) |
| Setup complexity | Cần login step mỗi job | Không cần login |

**Why:** Image 700MB, artifact upload/download tốn thời gian. GHCR có layer deduplication,
lần push thứ 2 chỉ push layer thay đổi (~50MB). Bonus: image trên registry, deploy server
nào cũng pull được.

## Decision 2: Block CRITICAL only, report HIGH

**Chosen:** exit-code 1 cho CRITICAL, report HIGH+MEDIUM
**Rejected:** Block cả HIGH, hoặc chỉ report không block

**Why:** Hầu hết base image Debian/Ubuntu có 30-60 HIGH CVE chưa có fix.
Block HIGH = pipeline gần như luôn fail = dev tắt scan = mất trust.
Block CRITICAL = cân bằng giữa security và velocity.
HIGH CVE vẫn track trong GitHub Security tab + DefectDojo.

## Decision 3: test và scan chạy song song

**Chosen:** Cả 2 `needs: build`, chạy parallel
**Rejected:** Sequential: build → test → scan → deploy

**Why:** test kiểm tra tools trong image (smoke test), scan kiểm tra CVE.
Hai job independent — output của test không ảnh hưởng scan.
Parallel giảm pipeline time 40-50%. Trade-off: tốn 2 runner slots đồng thời.

## Decision 4: Docker Compose deploy thay vì K8s

**Chosen:** Docker Compose trên runner
**Rejected:** kubectl apply lên minikube/EKS

**Why:** Scanner là one-shot job, không phải long-running service.
Docker Compose đủ cho single-host execution. K8s overkill cho use case này.
Day 20+ khi deploy web app lên production mới cần K8s.

## Decision 5: SARIF format cho Trivy report

**Chosen:** SARIF → upload GitHub Code Scanning
**Rejected:** JSON only → upload artifact

**Why:** SARIF là standard format cho static analysis. GitHub Code Scanning hiểu native —
hiển thị CVE trong Security tab, tạo alert, integrate với PR review.
JSON vẫn generate song song cho archive/DefectDojo integration.

## Decision 6: Multi-stage Dockerfile (2 stage)

**Chosen:** Stage 1 extract tools, Stage 2 base dojo + tools
**Rejected:** Single stage từ blackduck:latest (4.5GB)

**Why:** Final image 700MB vs 4.5GB. Giảm 85% attack surface.
Ít package = ít CVE = scan sạch hơn. Pull time giảm 6x.
Trade-off: Dockerfile phức tạp hơn, debug khó hơn khi tool path thay đổi.

## Decision 7: Concurrency control — cancel-in-progress

**Chosen:** Cancel pipeline cũ khi có push mới
**Rejected:** Để pipeline cũ chạy hết

**Why:** 2 push liên tiếp = pipeline cũ deploy version cũ SAU pipeline mới deploy version mới.
Race condition → production chạy code cũ. Cancel-in-progress đảm bảo chỉ
pipeline mới nhất chạy đến deploy.

## Decision 8: GITHUB_TOKEN thay vì PAT cho GHCR

**Chosen:** ${{ secrets.GITHUB_TOKEN }} (automatic)
**Rejected:** Personal Access Token stored as secret

**Why:** GITHUB_TOKEN tự sinh mỗi run, scoped đúng repo, tự expire.
PAT cần manage (rotate, revoke), nếu leak = attacker access mọi repo.
Trade-off: GITHUB_TOKEN chỉ access resources trong cùng repo/org.
Cross-org cần PAT, nhưng use case này không cần.
