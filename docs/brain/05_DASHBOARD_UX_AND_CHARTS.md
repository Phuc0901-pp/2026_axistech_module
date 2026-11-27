# 05 · Enterprise ERP UX, Pure Lucide & Component Real-Time Charts

## 1. Tài sản Giao diện Nhúng (`services/erp-platform/internal/api/static/`)

Go `router.go` nhúng toàn bộ giao diện bằng `//go:embed static` vào một file thực thi duy nhất (`erp-server.exe`), không cần Node.js hay CDN bên ngoài:

- `index.html` + `favicon.svg`: Khung SPA chuẩn Enterprise ERP gồm **9 phân hệ nghiệp vụ**, Slide-over Device Inspector Drawer và Quick Search (`Ctrl+K`).
- `vendor/leaflet.min.css`, `vendor/leaflet.min.js`: Leaflet `1.9.4` offline cho bản đồ Google Satellite.
- `vendor/lucide.min.js`: Lucide `v0.468.0` phục vụ **100% Pure Lucide Icons** toàn giao diện.
- `css/tokens.css`, `css/app.css`: Design tokens Dark/Light (chuẩn ISA-101 HMI & ISO 9241), quy trình ERP 3 bước, grid đồ thị thành phần (`.component-charts-grid`), badge trạng thái bảo mật.
- `js/icons.js`: `window.ERPIcons` ánh xạ `deviceName()`, `assetName()`, `vendorName()`, `iconHtml()`, `refresh()`.
- `js/map-engine.js`: `SatelliteMapEngine` hỗ trợ 4 lớp Google Tiles (`Satellite lyrs=s`, `Hybrid lyrs=y`, `Terrain lyrs=p`, `Roadmap lyrs=m`), lớp GeoJSON thửa ruộng, pin cảm biến Lucide nhấp nháy trạng thái (`LIVE` / `NO_DATA`).
- `js/charts.js`: Bộ vẽ Canvas HiDPI tương tác (`window.ERPCharts`):
  - `renderRealtimeSeries(canvas, tooltip, opts)`: Đa chuỗi, gradient area, tự scale trục Y, crosshair tooltip khi hover.
  - `renderComponentChartsGrid(containerEl, specs)`: Tạo card đồ thị độc lập cho từng thành phần (`Min / Max / N pts`, badge giá trị mới nhất, canvas riêng đúng đơn vị).
  - `renderForecastChart`, `renderExchangeChart`, `renderSoilDepthHtml`, `renderSoilNpkChart`.
- `js/inspector.js`: Slide-over Device Inspector Drawer (`ERPInspector.openDeviceDrawer`) và Quick Search (`Ctrl+K`).
- `js/app.js`: Controller điều phối dữ liệu, SSE listener và state chuỗi thời gian (`state.seriesHistory`).

---

## 2. Quy trình ERP 3 Bước trên Executive Overview (`#tab-overview`)

1. **Step 1 (`#vendorGrid`) — Organization & Workspace Selection**:
   - Liệt kê các Workspace AxisTech (`TANBAOCORP_Demo`, `TBSG`, ...) cùng số lượng thiết bị `LIVE`, tổng bản ghi và trạng thái cảnh báo.
2. **Step 2 (`#productList`) — Device / Sensor Catalog**:
   - Liệt kê các sản phẩm/thiết bị AxisTech trong Workspace (`Weather Station`, `Soil Probe`, `Water Level`, `Water Flow`), kèm trạng thái `LIVE` / `NO_DATA` và giá trị mới nhất.
3. **Step 3 (`#productDetailPanel`) — Real-Time Telemetry & Split Component Graphs**:
   - Hiển thị 100% KPI live, thanh lọc theo nhóm (`Thermal & Delta-T`, `Moisture & Rain`, `Wind & Pressure`, `Solar & UV`, `Soil Depth Profile`, `Hydrology & Flow`, `Power & Connectivity`) hoặc từng thành phần.
   - Lưới `#componentChartsGrid` tách mỗi đại lượng ra một đồ thị có trục Y riêng, cộng `#productRealtimeCanvas` cho chuỗi chính.

---

## 3. Phân hệ Nghiệp vụ ERP (9 Tabs) & Tab Compliance

- **Telemetry Streams (`#tab-telemetry`)**: Lưới đồ thị thành phần `#telemetryComponentCharts` cho toàn bộ Workspace kèm bảng snapshot chuẩn ISO 80000.
- **Weather Forecast (`#tab-forecast`)**: 6 đồ thị thành phần `#forecastComponentCharts` (Temp & Feels Like, Hourly Rain, Humidity, Wind Speed, Pressure, Cloud & UV) + Jane's Spray Window.
- **Weather Exchange (`#tab-exchange`)**: 15 đồ thị thành phần `#exchangeComponentCharts` phủ đủ các cột số của bảng 17 cột `tbncorp.weather` + xuất CSV RFC 4180.
- **Compliance & Security (`#tab-audit`)**:
  - Thẻ `#securityPostureGrid` & `#securityOverallBadge` hiển thị trạng thái thực từ `GET /api/erp/v1/security/status`: **At-Rest Encryption (`AES-256-GCM`)**, **Audit Chain (`SHA-256 VERIFIED / BROKEN`)**, **Rate Limit (`300 RPM`)**, **Mutation Guard (`X-API-Key`)**, **CSP & HSTS**.
  - Bảng Audit Trail hiển thị cột **`Chain Hash`** (`entry_hash` rút gọn + tooltip `prev_hash`) giúp kiểm toán viên xác minh tính toàn vẹn tức thì.
