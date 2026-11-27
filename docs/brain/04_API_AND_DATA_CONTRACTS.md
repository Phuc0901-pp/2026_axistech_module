# 04 · API & Data Contracts (Python Bridge + Golang ISO ERP)

## 1. Python Bridge Endpoints (`127.0.0.1:8001`)

Toàn bộ route `/api/v1/*` yêu cầu header `X-API-Key` xác thực constant-time (`hmac.compare_digest`) và validate tham số đường dẫn chống SSRF (`validate_safe_path_segment`).

| Method & Path | Mô tả |
|---|---|
| `GET /health/live` | Liveness probe (`200 OK`) |
| `GET /health/ready` | Readiness kiểm tra SQLite, Circuit Breaker, `projects_cached`, `last_error` |
| `GET /metrics` | Thống kê `mode`, `sync_count`, `last_sync_utc`, trạng thái Circuit Breaker |
| `GET /api/v1/security/posture` | Tình trạng mã hóa Outbox (`encryption_at_rest`, `encryption_algorithm`), `tls_strict_host_suffix`, `auth_mode` & Circuit Breaker |
| `GET /api/v1/projects` | Danh sách Workspace/Project AxisTech HQ |
| `GET /api/v1/projects/{project_id}/devices` | Danh sách thiết bị cảm biến đã chuẩn hóa |
| `GET /api/v1/projects/{project_id}/telemetry?device_id=` | Snapshot mới nhất (`LIVE`, `NO_DATA`, `OFFLINE`) kèm readings + metadata |
| `GET /api/v1/projects/{project_id}/telemetry/history?device_id=&hours=24` | Chuỗi lịch sử từ SQLite `telemetry_history` (`hours=1..720`, fallback bản ghi gần nhất) |
| `GET /api/v1/projects/{project_id}/fields` | Thửa ruộng GeoJSON Polygon chuẩn RFC 7946 |
| `GET /api/v1/projects/{project_id}/assets` | Tài sản thiết bị vật lý (Water Tank, Tractor, Cultivator...) |
| `GET /api/v1/projects/{project_id}/alerts/policies` | Chính sách cảnh báo đang hoạt động |
| `GET /api/v1/projects/{project_id}/alerts/history` | Lịch sử cảnh báo thiết bị |
| `GET /api/v1/projects/{project_id}/providers` | Danh sách Weather Provider gắn vào project |
| `GET /api/v1/projects/{project_id}/exchange/tokens` | Token API Exchange |
| `GET /api/v1/projects/{project_id}/exchange/weather` | Bảng thời tiết 17 cột `tbncorp.weather` (hoặc fallback từ live snapshot) |
| `GET /api/v1/projects/{project_id}/forecast` | Gói dự báo MET Norway + Jane's Weather (`ProjectForecastBundle`) |
| `POST /api/v1/sync/trigger` | Kích hoạt một chu kỳ `sync_all()` tức thì |
| `GET /api/v1/stream` | Luồng Server-Sent Events (`telemetry_update`, `sync_complete`) |

Mọi lỗi đều trả về chuẩn **RFC 9457 (`application/problem+json`)** gồm `{type, title, status, detail, correlation_id}`, không rò rỉ stack trace.

---

## 2. Golang ISO ERP Endpoints (`127.0.0.1:8088`)

| Method & Path | Mô tả |
|---|---|
| `GET /` | Embedded Enterprise ERP SPA (`//go:embed static`) |
| `GET /health/live`, `GET /health/ready` | Probes kiểm tra sức khỏe ERP và trạng thái kết nối Bridge |
| `GET /api/erp/v1/security/status` | Tình trạng bảo mật (`encryption_at_rest`, `encryption_algorithm`, `audit_chain_verified`, `audit_entries`, `rate_limit_rpm`, `api_key_guard_enabled`, `csp_policy`) |
| `GET /api/erp/v1/dashboard?project_id=` | KPI tổng hợp, Smart Default Workspace, `snapshots`, `devices`, `forecast`, `security` posture |
| `GET /api/erp/v1/projects` | Danh sách Workspace/Project đang lưu trong Store |
| `GET /api/erp/v1/devices?project_id=` | Thiết bị theo Workspace |
| `GET /api/erp/v1/telemetry?project_id=&device_id=` | Snapshot + readings gần nhất |
| `GET /api/erp/v1/telemetry/history?project_id=&device_id=&hours=24` | Proxy đọc lịch sử 24h từ Bridge (tự fallback `store.GetReadings` khi offline) |
| `GET /api/erp/v1/fields?project_id=` | Địa điểm & GeoJSON polygons |
| `GET /api/erp/v1/assets?project_id=` | Tài sản vật lý |
| `GET /api/erp/v1/alerts/policies?project_id=` | Chính sách cảnh báo |
| `GET /api/erp/v1/alerts/history?project_id=` | Lịch sử cảnh báo |
| `GET /api/erp/v1/forecast?project_id=` | Dữ liệu dự báo thời tiết |
| `GET /api/erp/v1/incidents?project_id=&status=` | Danh sách Incident ERP (`OPEN`, `ACKNOWLEDGED`, `RESOLVED`) |
| `POST /api/erp/v1/incidents/{id}/{acknowledge|resolve}` | Chuyển trạng thái FSM (bảo vệ bởi `ERP_REQUIRE_API_KEY` nếu bật) và nối Hash-Chained Audit Log |
| `GET /api/erp/v1/exchange/weather?project_id=` | Bảng dữ liệu Exchange 17 cột |
| `GET /api/erp/v1/exchange/weather/export.csv?project_id=` | Xuất CSV 17 cột chuẩn RFC 4180 |
| `GET /api/erp/v1/audit?limit=` | Nhật ký Audit ISO 27001 kèm `prev_hash` và `entry_hash` SHA-256 |
| `POST /api/erp/v1/sync/now` | Ép ERP + Bridge đồng bộ ngay |
| `GET /api/erp/v1/events` | SSE live stream (`connected`, `sync_update`, `incident_update`, `heartbeat`) |
| `GET /api/tbsgagtech/v1/modules/catalog` | Khám phá các module Device (`dev_...`) & Forecast Point (`fcp_...`) kèm `ui_url`, `embed_url`, `api_url` |
| `GET /api/tbsgagtech/v1/modules/devices/{dev_token}` | REST API độc lập kéo 1 module Device sang hệ thống ngoài (`power_state`, `geolocation`, bảng 10/trang, đồ thị) |
| `GET /api/tbsgagtech/v1/modules/forecast/{fcp_token}` | REST API độc lập kéo 1 module Forecast điểm sang hệ thống ngoài (`location`, `table` 10/trang, `chart`) |
| `GET /tbsgagtech/v1/*` | Đường dẫn SPA chuẩn ISO (`/tbsgagtech/v1/overview`, `/modules/devices/dev_...`, `/modules/forecast/fcp_...`) |

---

## 3. Lược đồ SQLite (`data/bridge_state.db`)

1. **`sync_cursors(scope_key PRIMARY KEY, cursor_utc, updated_at)`**: Con trỏ đồng bộ tăng dần theo từng Workspace.
2. **`dedup_keys(dedup_hash PRIMARY KEY, created_at)`**: Khóa băm `SHA-256(org|device_id|metric|depth_level|timestamp_utc)` chống ghi trùng bản ghi.
3. **`outbox_events(event_id PRIMARY KEY, event_type, payload_json, status, retry_count, last_error, created_at, updated_at)`**: Hàng đợi outbox (`PENDING`, `DELIVERED`, `DEAD_LETTER`); `payload_json` tự động mã hóa **`ENC:v1:`** khi bật `AXISSTREAM_ENCRYPTION_KEY`.
4. **`telemetry_history(project_id, device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc)`**:
   - `PRIMARY KEY (device_id, metric, depth_level, timestamp_utc)`
   - Index `idx_tel_hist_proj_dev_ts(project_id, device_id, timestamp_utc)`
   - Phục hồi đường cong đồ thị 24h khi refresh (`F5`) hoặc khởi động lại.
