# 06 · Operations Runbook, Troubleshooting & Decision Log (ADRs)

## 1. Cấu hình `init.js` & Ma trận Biến môi trường

### Mẫu `init.js` (Gitignored — đặt tại `axisstream_erp_platform/init.js`)
Sao chép từ [init.example.js](../../init.example.js):
- `axisstream`: `mode` (`live`/`demo`), `auth_mode` (`cookie`/`exchange_token`/`dual`), `email`, `password`.
- `security`: `encryption_key` (khóa chủ AEAD/AES-256-GCM), `require_api_key` (`false`/`true`), `rate_limit_rpm` (`300`).
- `erp`: `bridge_port` (`8001`), `erp_port` (`8088`), `sync_interval_sec` (`15`).

### Biến môi trường chính (`start_live.ps1` tự nạp từ `init.js` và dọn sau khi tắt)

| Service | Biến môi trường | Mặc định / Ghi chú |
|---|---|---|
| Bridge | `AXISSTREAM_MODE` / `AXISSTREAM_AUTH_MODE` | `demo` (hoặc `live` qua `start_live.ps1`) / `dual` |
| Bridge | `AXISSTREAM_EMAIL` / `AXISSTREAM_PASSWORD` / `AXISSTREAM_EXCHANGE_TOKEN` | Tài khoản AxisStream (`SecretStr`) |
| Bridge | `AXISSTREAM_ENCRYPTION_KEY` | Khóa mã hóa `outbox_events` (`HKDF-SHA256-CTR-HMAC-SHA256`) |
| Bridge | `AXISSTREAM_SQLITE_PATH` | `:memory:` (test) / `data/bridge_state.db` (`start_live.ps1`) |
| Bridge | `AXISSTREAM_INBOUND_API_KEY` | API key nội bộ bắt buộc giữa Go ERP ↔ Python Bridge |
| Go ERP | `ERP_PORT` / `BRIDGE_BASE_URL` / `BRIDGE_API_KEY` | `8080` (`8088` qua `start_live.ps1`) / `http://127.0.0.1:8001` |
| Go ERP | `ERP_ENCRYPTION_KEY` | Khóa `AES-256-GCM` mã hóa `erp_state.json` trên đĩa |
| Go ERP | `ERP_REQUIRE_API_KEY` / `ERP_API_KEY` | `false` (khi `true`, mọi `POST /api/*` bắt buộc header `X-API-Key`) |
| Go ERP | `ERP_RATE_LIMIT_RPM` | `300` (giới hạn request/phút/IP bằng sliding window) |
| Go ERP | `ERP_DATA_FILE_PATH` (hoặc `DATA_FILE_PATH`) / `SYNC_INTERVAL_SEC` | `data/erp_state.json` / `10`–`15` |

---

## 2. Xử lý Sự cố thường gặp trên Windows

1. **Port `8080` hiển thị trang Adminer thay vì AxisTech ISO ERP**:
   - Máy Windows có dịch vụ khác trên `:8080`. Luôn dùng port `8088` (`start_live.ps1` mặc định đặt `ErpPort = 8088`) -> truy cập `http://127.0.0.1:8088/`.
2. **`start_live.ps1 cannot be loaded because running scripts is disabled`**:
   - Chạy bằng: `powershell -ExecutionPolicy Bypass -File .\start_live.ps1`.
3. **Nâng cấp code frontend nhưng trình duyệt vẫn hiển thị bản cũ**:
   - Dừng `erp-server.exe`, build lại bằng `go build -o erp-server.exe ./cmd/erp-server` (vì UI nằm trong `//go:embed static`), sau đó nhấn `Ctrl+F5`.
4. **Lỗi `Access denied` cache Go khi chạy trong môi trường hạn chế**:
   - Đặt `$env:GOCACHE="$PWD\.gocache"` và `$env:GOPATH="$PWD\.gopath"` bên trong `services/erp-platform/`.
5. **PowerShell gọi `python` mở Microsoft Store**:
   - Luôn gọi trực tiếp virtualenv: `services\axisstream-bridge\.venv\Scripts\python.exe`.

---

## 3. Architecture Decision Records (ADRs)

| ID | Quyết định | Lý do & Hệ quả |
|---|---|---|
| **ADR-001** | Tách 2 service Python Bridge + Go ERP | Python xử lý nhanh auth/ACL nhiều ngoại lệ cloud AxisStream; Go cho binary gọn nhẹ, `net/http` bảo mật, SSE ổn định và nhúng sẵn Enterprise UI. |
| **ADR-002** | Chuẩn hóa AxisTech Single-Module ERP (`2026_axistech_module`) | Loại bỏ toàn bộ mã ngoại lai để tập trung toàn diện vào nghiệp vụ AxisTech, dễ kiểm soát chất lượng ISO 25010 / 29119. |
| **ADR-003** | `init.js` nằm ở root + gitignored + dọn biến env khi thoát | Tập trung cấu hình tiện vận hành trên Windows nhưng giữ **0 byte secret** trong Git, code, fixture test và HTML/JS tĩnh. |
| **ADR-004** | Bundle cục bộ Leaflet + Lucide, khóa CSP `script-src 'self'` | Vận hành ổn định không phụ thuộc CDN bên thứ ba, chỉ mở ngoại lệ `mt0..mt3.google.com` cho tile vệ tinh Google. |
| **ADR-005** | Tách mỗi đại lượng đo thành đồ thị thành phần riêng | Tránh bóp méo trục Y khi gộp `1010 hPa` cùng `2.5 UV`, giữ đủ 100% thành phần + 15 cột Exchange. |
| **ADR-006** | SQLite `telemetry_history` + hydrate 24h | Đảm bảo biểu đồ có đường cong thực ngay khi mở trang và không mất chuỗi lịch sử khi `F5`. |
| **ADR-007** | Mã hóa lưu trữ `AES-256-GCM` / `HKDF-SHA256-CTR-HMAC-SHA256` & Audit Chain SHA-256 | Bảo vệ dữ liệu lưu trữ trên đĩa khỏi truy cập trái phép và phát hiện ngay mọi hành vi chỉnh sửa nhật ký Audit (ISO 27001 A.8.15 & A.8.24). |
