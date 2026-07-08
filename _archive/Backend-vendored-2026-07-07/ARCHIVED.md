# ARCHIVED — bản Backend vendored (2026-07-07)

Thư mục này là **bản copy CŨ** của app `Project_AI_trend_agent`, từng được nhúng
trực tiếp vào repo pipeline. Đã ngừng dùng từ 2026-07-07.

## Vì sao archive
Pipeline chuyển sang pattern **scanner → target**: workflow `_build`/`_test`/`_sast`/
`_gitleaks` giờ **checkout `Project_AI_trend_agent` tại pin ref** rồi build/scan từ đó,
thay vì build bản copy nằm trong repo này. Xem [docs/ADR-002](../../docs/ADR-002-vendored-vs-checkout-target.md).

Bản copy này đã **stale**: chỉ có `telegram_agent.py` (Phase 6 cũ), thiếu Discord
publisher / prompts / evals của target hiện hành.

## Không xóa
Giữ lại theo no-delete rule của workspace để tham chiếu lịch sử. **Không build,
không scan, không import** từ đây — semgrep đã `--exclude _archive`.

Muốn xem code app mới nhất → đọc repo target tại pin trong `.github/workflows/ci-cd.yml`
(job `config` → `target_ref`).
