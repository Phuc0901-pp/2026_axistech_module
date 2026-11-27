# 03 · Cybersecurity, Cryptography & ISO/IEC 27001 Architecture

> Tài liệu chuẩn bảo mật & mã hóa cho **AxisTech ISO ERP Platform** (`2026_axistech_module`).

---

## 1. Chiến lược Phòng thủ theo Chiều sâu (Defense-in-Depth)

Hệ thống áp dụng kiểm soát bảo mật xuyên suốt **5 lớp** từ upstream cloud tới giao diện người dùng:

1. **Lớp Mạng & Transport (ISO 27001 A.8.20 / A.8.26)**:
   - Bắt buộc `https://` cho toàn bộ upstream `*.axisstream.co`, kiểm tra hậu tố host ở cả cấu hình lẫn HTTP `302` redirect.
   - Chặn Path Traversal & SSRF tại gateway (`validate_safe_path_segment`).
   - Áp đặt đầy đủ security headers trên cả Python Bridge và Go ERP:
     - `X-Content-Type-Options: nosniff`
     - `X-Frame-Options: DENY`
     - `Referrer-Policy: no-referrer`
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
     - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
     - CSP nghiêm ngặt: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://mt0.google.com https://mt1.google.com https://mt2.google.com https://mt3.google.com`.

2. **Lớp Xác thực & Chống Lạm dụng (ISO 27001 A.8.5)**:
   - **Dual Auth Upstream**: `CookieSessionAuthenticator` (`Single-Flight Re-Auth Lock` chống bão `401`) và `ApiExchangeTokenAuthenticator` (theo dõi ngày hết hạn `valid_until`).
   - **Service-to-Service Auth**: Constant-time `hmac.compare_digest` kiểm tra `X-API-Key` ở mọi route `/api/v1/*` của Bridge.
   - **Mutation Guard (`ERP_REQUIRE_API_KEY`)**: Khi bật, mọi request thay đổi trạng thái (`POST /api/erp/v1/incidents/*`, `POST /api/erp/v1/sync/now`) bắt buộc gửi header `X-API-Key` khớp `subtle.ConstantTimeCompare`.
   - **Per-IP Sliding-Window Rate Limiter (`ERP_RATE_LIMIT_RPM`)**: Giới hạn mặc định `300 req/min/IP` trên toàn bộ API ERP, trả `HTTP 429 Too Many Requests` (`Retry-After: 60`) theo RFC 9457 khi vượt ngưỡng.

3. **Lớp Mã hóa Dữ liệu Lưu trữ (Encryption at Rest — ISO 27001 A.8.24)**:
   - **Python SQLite Outbox (`FieldEncryptor`, `infrastructure/security/crypto.py`)**:
     - Khi cấu hình `AXISSTREAM_ENCRYPTION_KEY`, mọi `payload_json` trong bảng `outbox_events` được mã hóa AEAD **`HKDF-SHA256-CTR-HMAC-SHA256`** với tiền tố phiên bản **`ENC:v1:`** + `salt(16B) || nonce(16B) || ciphertext || hmac_sha256(32B)`.
     - Sửa 1 byte bất kỳ trên đĩa hoặc dùng sai khóa đều bị từ chối với `SecurityViolationError`.
   - **Golang ERP State (`AESCipher`, `internal/security/crypto.go`)**:
     - Khi cấu hình `ERP_ENCRYPTION_KEY`, toàn bộ snapshot `data/erp_state.json` được ghi nguyên tử (temp + rename) dưới dạng **Encrypted JSON Envelope** (`"algorithm": "AES-256-GCM"`, cipher `AES-256-GCM`, nonce 12 byte ngẫu nhiên từ `crypto/rand`, dẫn xuất khóa 256-bit bằng `SHA-256`).
     - Hỗ trợ đọc backward-compatible các file JSON chưa mã hóa cũ để nâng cấp an toàn, sau đó tự mã hóa lại ở lần ghi tiếp theo.

4. **Nhật ký Kiểm toán Chống Giả mạo (Tamper-Evident Hash-Chained Audit Log — ISO 27001 A.8.15)**:
   - Mỗi `AuditEntry` lưu thêm **`prev_hash`** (chuỗi SHA-256 hex của bản ghi liền trước, bắt đầu từ `"GENESIS"`) và **`entry_hash`** tính qua `ComputeAuditHash(prevHash, entry)`.
   - Hàm `VerifyAuditChain(entries)` xác minh lại toàn bộ chuỗi từ đầu; nếu bất kỳ dòng log lịch sử nào bị sửa tay trên file/bộ nhớ, hệ thống phát hiện chuỗi bị gãy ngay trên tab **Compliance & Security** (`#tab-audit`) và endpoint `GET /api/erp/v1/security/status`.

5. **Zero-Secret Hygiene & Log Redaction**:
   - Không lưu mật khẩu/token thật trong source, test, `.env.example`, `init.example.js`, hay `.md` (`UT-050`).
   - `init.js` nằm ở `.gitignore`, không nằm trong `embed.FS` `static/`, và các biến env nhạy cảm (`AXISSTREAM_PASSWORD`, `AXISSTREAM_ENCRYPTION_KEY`, `ERP_ENCRYPTION_KEY`) được `start_live.ps1` dọn sạch trong `finally {}`.
   - Log JSON (`JsonFormatter` ở Python & `log/slog` ở Go) tự động che `[REDACTED]` mọi khóa `password`, `token`, `cookie`, `authorization`, `api_key`, `encryption_key`.

---

## 2. API Quan sát Tình trạng Bảo mật

- **Python Bridge**: `GET /api/v1/security/posture` (yêu cầu `X-API-Key`) → trả về `encryption_at_rest`, `encryption_algorithm`, `tls_strict_host_suffix`, `auth_mode`, `read_only_sync`, `rate_limit_rps`, `circuit_breaker_state`.
- **Golang ISO ERP**: `GET /api/erp/v1/security/status` → trả về `encryption_at_rest`, `encryption_algorithm`, `audit_chain_verified`, `audit_entries`, `rate_limit_rpm`, `api_key_guard_enabled`, `read_only_cloud_sync`, `csp_policy`.
