# AxisTech ISO Enterprise ERP Platform (`2026_axistech_module`)

Nền tảng ERP vận hành nông nghiệp & giám sát cảm biến thời gian thực **AxisTech (`AxisStream HQ`)**, được kiến trúc và kiểm thử theo chuẩn **ISO/IEC 42010 · ISO/IEC 27001 · ISO/IEC 25010 · ISO/IEC 29119** và giao diện điều hành **ISA-101**.

> **Bộ não kỹ thuật hợp nhất (Unified Brain)**: xem [BRAIN.md](BRAIN.md) để tra cứu kiến trúc, cơ chế mã hóa, hợp đồng API, ADRs và sổ tay vận hành.

---

## Kiến trúc 2 Service Chuẩn ISO

- **`services/axisstream-bridge` (Python 3.11+ · FastAPI · Pydantic v2 · SQLite WAL)**:
  - Kiến trúc Hexagonal + Anti-Corruption Layer (ACL) dành riêng cho **AxisTech (`*.axisstream.co`)**: tự động xử lý `batch -> per-device` fallback, Epoch `1970-01-01` -> `NO_DATA`, chuẩn hóa đơn vị ISO 80000, GeoJSON thửa ruộng, dự báo MET Norway & Jane's Weather, bảng Weather Exchange 17 cột (`tbncorp.weather`).
  - Dual Auth (`CookieSessionAuthenticator` + `ApiExchangeTokenAuthenticator`) với single-flight re-auth lock.
  - Mã hóa AEAD **`HKDF-SHA256-CTR-HMAC-SHA256` (`ENC:v1:`)** cho `outbox_events` trong SQLite WAL (`data/bridge_state.db`) cùng bảng lịch sử **`telemetry_history`** 24h+.
- **`services/erp-platform` (Go 1.23+ stdlib `net/http` · `embed.FS` · `log/slog` · `crypto/aes`)**:
  - Mã hóa dữ liệu lưu trữ trên đĩa bằng **`AES-256-GCM`** (`ERP_ENCRYPTION_KEY`), nhật ký kiểm toán **SHA-256 hash-chained** phát hiện giả mạo (`prev_hash -> entry_hash`), Rate Limiter trượt theo IP (`429 Too Many Requests`), tùy chọn khóa mutation `X-API-Key` constant-time, CSP + HSTS + Permissions-Policy.
  - Đồng bộ gia tăng REST + SSE, quản lý sự cố FSM (`OPEN -> ACKNOWLEDGED -> RESOLVED`), xuất CSV 17 cột RFC 4180.
  - Giao diện Enterprise ERP nhúng (**100% Lucide Icons**, 9 module nghiệp vụ, quy trình 3 bước **Workspace -> Device -> Split Component Graphs**, bản đồ Google Satellite và tab **Compliance & Security**).

---

## Khởi chạy nhanh (Windows)

### 1. Cấu hình tài khoản & khóa mã hóa (Zero-Secret Gitignored)
```powershell
Copy-Item .\init.example.js .\init.js
# Mở init.js điền thông tin tài khoản AxisStream HQ và khóa encryption_key
```

### 2. Chạy toàn bộ hệ thống Live (tự sinh khóa AEAD nếu chưa khai báo)
```powershell
cd d:\Project\2026_SATO\axisstream_erp_platform
powershell -ExecutionPolicy Bypass -File .\start_live.ps1
```

Truy cập **`http://127.0.0.1:8088/`** (cổng mặc định `8088` tránh xung đột Adminer `:8080`).

### 3. Chế độ Demo (không cần tài khoản upstream)
```powershell
# Terminal 1: Python Bridge (Demo Mode + Encrypted Outbox)
cd d:\Project\2026_SATO\axisstream_erp_platform\services\axisstream-bridge
$env:AXISSTREAM_MODE="demo"; $env:AXISSTREAM_INBOUND_API_KEY="dev-bridge-api-key-change-me"
$env:AXISSTREAM_ENCRYPTION_KEY="dev-demo-aead-encryption-key"; $env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m uvicorn axisstream_bridge.interfaces.api.app:app --host 127.0.0.1 --port 8001

# Terminal 2: Golang ISO ERP (AES-256-GCM Mode)
cd d:\Project\2026_SATO\axisstream_erp_platform\services\erp-platform
$env:ERP_PORT="8088"; $env:BRIDGE_API_KEY="dev-bridge-api-key-change-me"
$env:ERP_ENCRYPTION_KEY="dev-demo-aead-encryption-key"
.\erp-server.exe
```

---

## Kiểm thử tự động (133 Tests · ISO 29119 Traceable)

```powershell
# Python Bridge (73 tests: UT-001..UT-073)
cd d:\Project\2026_SATO\axisstream_erp_platform\services\axisstream-bridge
.\.venv\Scripts\python.exe -m pytest -q --cov=axisstream_bridge

# Golang ISO ERP (60 tests: G-UT-001..G-UT-060)
cd d:\Project\2026_SATO\axisstream_erp_platform\services\erp-platform
$env:GOCACHE="$PWD\.gocache"; $env:GOPATH="$PWD\.gopath"
go test -v -cover ./...
```

---

## Tài liệu trong Bộ não chung
- [Master Brain Hub](BRAIN.md)
- [01 · System Architecture](docs/brain/01_SYSTEM_ARCHITECTURE.md)
- [02 · AxisTech Module (`*.axisstream.co`)](docs/brain/02_MODULE_AXISSTREAM.md)
- [03 · Cybersecurity, Crypto & ISO 27001](docs/brain/03_SECURITY_AND_ENCRYPTION.md)
- [04 · API & Data Contracts](docs/brain/04_API_AND_DATA_CONTRACTS.md)
- [05 · Enterprise ERP UX & Real-Time Charts](docs/brain/05_DASHBOARD_UX_AND_CHARTS.md)
- [06 · Operations Runbook & ADRs](docs/brain/06_OPERATIONS_RUNBOOK_AND_DECISIONS.md)
- [ISO/IEC/IEEE 42010 Architecture](docs/iso_architecture_42010.md)
- [ISO/IEC 27001 Security Controls](docs/iso_security_27001.md)
- [ISO/IEC/IEEE 29119 Traceability Matrix](docs/traceability_matrix_29119.md)
