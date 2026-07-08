# ADR-002: Vendored copy vs Checkout target repo

**Date:** 2026-07-07
**Status:** Accepted
**Author:** dokhacduc29

## Context

Repo `blackduck-pipeline` là **scanner/CI-CD** cho app `Project_AI_trend_agent`
(repo riêng, public). Trước đây pipeline nhúng một **bản copy** của app trong
`Backend/` rồi build + scan chính bản copy đó.

Bản copy này trôi khỏi app thật (stale): còn `telegram_agent.py` Phase 6 cũ,
thiếu Discord publisher / prompts / evals. Pipeline vì thế build + scan **sai thứ
lẽ ra phải ship** — anti-pattern. Câu hỏi: pipeline nên scan cái gì, và lấy code
app từ đâu?

---

## Decision: Checkout target repo tại pin ref, xoá bản vendored

**Chosen:** Pipeline **checkout `Project_AI_trend_agent` tại một commit SHA pin cứng**
(`job config` trong `ci-cd.yml`) vào `./target`, build + test + SAST + secret-scan
từ đó. Bản `Backend/` copy chuyển sang `_archive/`.

**Rejected A — giữ bản vendored (A-tối giản):** vi phạm rule *single source of truth*;
copy luôn trôi khỏi app thật; scan ra kết quả không phản ánh cái đang chạy.

**Rejected B — git submodule:** submodule cũng pin được commit nhưng thêm ma sát
(`git submodule update`, checkout 2 tầng, dev hay quên init). Reusable workflow
`actions/checkout` với `repository:` + `ref:` cho cùng tính reproducible mà nhẹ hơn.

**Rejected C — pip editable install target:** Black Duck / Trivy / Semgrep scan
*source + manifest*, không import Python module → giải quyết vấn đề không tồn tại.

| Tiêu chí | Checkout + pin | Vendored copy | Submodule |
|---|---|---|---|
| Single source of truth | ✅ | ❌ (2 bản) | ✅ |
| Reproducible scan | ✅ (pin SHA) | ⚠️ (drift) | ✅ |
| Không đụng repo target | ✅ | ✅ | ✅ |
| Ma sát dev | Thấp | Thấp | Cao |
| Bump version | Sửa 1 dòng `target_ref` | Copy tay | `git submodule update` |

**Why pin bằng SHA (không phải `main`):** scan reproducible — không trôi khi app
repo commit tiếp. Demo ổn định, audit trail rõ. Bump = sửa **duy nhất** `target_ref`
trong `job config` của `ci-cd.yml`.

**Why Dockerfile ở lại repo pipeline (không dùng Dockerfile của target):**
hardening (multi-stage, non-root, curated deps — Week 5) là concern của repo
DevSecOps. `docker/build-push-action` cho `context: ./target` + `file: ./Dockerfile`
tách rời → build source app bằng Dockerfile hardened mà không đụng target.

---

## Consequences

- **Positive:** scan đúng code sẽ ship; single source; bump 1 dòng; target repo
  giữ nguyên (public, không bị pollute bởi config CI/CD của scanner).
- **Negative:** mỗi lần app repo có thay đổi muốn scan → phải bump `target_ref` thủ
  công (đánh đổi có chủ đích để đổi lấy reproducibility).
- **Follow-up:** khi CVE trên bản pin đã vá ở app repo → bump pin, chạy lại pipeline,
  so sánh Trivy/Semgrep trước–sau.

## Pin hiện tại

```
target_repo: dokhacduc29/Project_AI_trend_agent
target_ref:  95537f42bd4e387a64036270e4ed9bb666511107   # main HEAD @ 2026-07-07
```
