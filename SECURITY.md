# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (main branch) | ✅ Active |
| < 1.0 | ❌ End of life |

## Reporting a Vulnerability

**Không mở public Issue cho lỗ hổng bảo mật.**

Nếu bạn phát hiện lỗ hổng bảo mật trong project này, vui lòng báo cáo qua một trong hai cách:

### Cách 1 — GitHub Private Vulnerability Reporting (Khuyên dùng)
1. Vào tab **Security** của repo này
2. Click **"Report a vulnerability"**
3. Điền thông tin chi tiết theo form

### Cách 2 — Email trực tiếp
Gửi email mô tả lỗ hổng tới maintainer qua GitHub profile:
[github.com/dokhacduc29](https://github.com/dokhacduc29)

---

## Thông tin cần cung cấp khi báo cáo

Để xử lý nhanh nhất, vui lòng bao gồm:

- **Mô tả lỗ hổng**: Loại lỗ hổng (XSS, injection, secret exposure, v.v.)
- **Bước tái hiện**: Các bước cụ thể để reproduce
- **Tác động ước tính**: Dữ liệu/hệ thống nào có thể bị ảnh hưởng
- **Phiên bản**: Commit SHA hoặc branch đang bị ảnh hưởng
- **Bằng chứng (nếu có)**: Screenshot, log, PoC code

---

## Thời gian phản hồi

| Mốc | Thời gian |
|-----|-----------|
| Xác nhận nhận báo cáo | Trong vòng **48 giờ** |
| Đánh giá mức độ nghiêm trọng | Trong vòng **7 ngày** |
| Phát hành bản vá (nếu hợp lệ) | Trong vòng **30 ngày** |

---

## Phạm vi (Scope)

### Trong phạm vi
- Source code Python trong thư mục `Backend/`
- GitHub Actions workflows trong `.github/workflows/`
- Cấu hình Docker (`Dockerfile`, `docker-compose.yml`)
- Lộ secret/credential trong code hoặc git history

### Ngoài phạm vi
- Lỗ hổng thuộc về third-party dependencies (báo cáo trực tiếp cho upstream)
- Lỗ hổng trong GitHub Actions runner infrastructure
- Social engineering

---

## Chính sách công bố (Disclosure Policy)

Project này theo **Responsible Disclosure**:

1. Báo cáo được tiếp nhận và xác nhận
2. Lỗ hổng được phân tích và vá
3. Bản vá được release
4. Credit được ghi nhận trong release notes (nếu người báo cáo đồng ý)

---

## Security Best Practices trong project này

- **Secrets**: Tất cả API key/token được inject qua GitHub Actions Secrets — không hardcode
- **Container**: Non-root user (`appuser`) trong Docker image
- **Dependency scanning**: Trivy quét CVE trong CI/CD pipeline
- **Secret scanning**: Gitleaks chặn commit lộ secret trước khi build
- **Least privilege**: GitHub Actions dùng `permissions` tối thiểu theo từng job
