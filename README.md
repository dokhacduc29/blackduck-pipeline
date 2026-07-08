# blackduck-pipeline

CI/CD + DevSecOps scanner cho app [`Project_AI_trend_agent`](https://github.com/dokhacduc29/Project_AI_trend_agent).

Repo này **không chứa code app**. Nó là pipeline: checkout app tại một commit pin
cứng, rồi build → test → scan secret (Gitleaks) → SAST (Semgrep) → scan image
(Trivy) → deploy đa môi trường. Xem [ADR-002](docs/ADR-002-vendored-vs-checkout-target.md)
để hiểu vì sao tách scanner khỏi target.

## Pattern: scanner → target

```
┌─────────────────────────┐         checkout @ pin ref        ┌──────────────────────────┐
│  blackduck-pipeline      │  ───────────────────────────────▶ │  Project_AI_trend_agent  │
│  (repo này — scanner)    │                                    │  (repo app — target)     │
│                          │                                    │                          │
│  • Dockerfile (hardened) │   build ./target với ./Dockerfile  │  • Backend/ (source)     │
│  • .github/workflows/    │  ◀───────────────────────────────  │  • requirements.txt      │
│  • rules/ (Semgrep)      │        source app → build/scan     │  • tests/                │
│  • .gitleaks.toml        │                                    │                          │
└─────────────────────────┘                                    └──────────────────────────┘
        giữ CONFIG bảo mật                                            giữ CODE app
        (không đụng target)                                          (không đụng pipeline)
```

- Pipeline **checkout target vào `./target`** rồi build image bằng Dockerfile
  hardened của repo này (`context: ./target`, `file: ./Dockerfile`).
- Bản `Backend/` copy cũ đã archive → [`_archive/`](_archive/). Không dùng nữa.

## Flow pipeline

```
config ──┬─▶ secrets-scan (Gitleaks: pipeline + target)  ──┐
         └─▶ sast (Semgrep: pipeline + target)            ─┴─▶ build ──┬─▶ test ──┐
                                                                        └─▶ scan ─┴─▶ deploy-dev
                                                                                        └─▶ deploy-staging (main)
                                                                                              └─▶ deploy-prod (approval)
```

| Stage | Workflow | Scan gì |
|---|---|---|
| Secret scan | `_gitleaks.yml` | git history + working tree của **cả** pipeline lẫn target |
| SAST | `_sast.yml` | Semgrep `auto` + custom SQLi rules trên pipeline + target |
| Build | `_build.yml` | build image từ source target @ pin |
| Test | `_test.yml` | pytest trên `target/Backend` + smoke test container |
| Scan image | `_scan.yml` | Trivy CVE gate (block CRITICAL) |
| Deploy | `_deploy.yml` | docker compose lên dev/staging/prod |

## Bump pin ref (đổi version app đem scan)

Pin nằm **một chỗ duy nhất** — job `config` trong
[`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml):

```yaml
target_ref=95537f42bd4e387a64036270e4ed9bb666511107   # sửa dòng này
```

Lấy SHA mới nhất của target:

```bash
git ls-remote https://github.com/dokhacduc29/Project_AI_trend_agent refs/heads/main
```

Đổi `target_ref` → commit → pipeline chạy lại với version mới. Không cần sửa file nào khác.

## Secrets cần cấu hình (GitHub → Settings → Secrets)

Deploy inject các secret sau (Phase 6 — Discord là publisher hiện hành, Telegram đã bỏ):

- `NEWS_API_KEY`, `GEMINI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `DISCORD_WEBHOOK_URL`
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`

## Local dev

```bash
pre-commit install                    # Gitleaks + Semgrep chạy trước mỗi commit
pre-commit run --all-files            # chạy thủ công
```

Xem thêm: [docs/PIPELINE-GUIDE.md](docs/PIPELINE-GUIDE.md) · [ADR-001](docs/ADR-001-pipeline-design.md) · [ADR-002](docs/ADR-002-vendored-vs-checkout-target.md)
