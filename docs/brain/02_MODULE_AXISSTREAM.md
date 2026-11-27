# 02 · AxisTech Module (`AxisStream HQ` · `*.axisstream.co`)

## 1. Endpoints Upstream & Vai trò

| Host HTTPS | Vai trò | Adapter Client |
|---|---|---|
| `https://v2.api.axisstream.co` | Login cookie, Projects, Devices, Fields (GeoJSON), Assets, Providers, Alert Policies, Alert History, Exchange Tokens | `v2_client.py`, `alert_client.py` |
| `https://data.api.axisstream.co` | Batch Telemetry (`/device/{org}/batch`), Per-Device Telemetry (`/device/{org}/{source}/{externalId}/device`), Weather Exchange (`/exchange/{org}/weather`) | `telemetry_client.py`, `alert_client.py` |
| `https://provider.api.axisstream.co` | Dự báo thời tiết MET Norway (`/metnorway/forecast/...`) và Jane's Weather (`/janes_weather/forecast/...`) | `forecast_client.py` |

Mọi URL bắt buộc dùng `https://` và kiểm tra hậu tố host `.axisstream.co` ở cả cấu hình lẫn HTTP redirect.

---

## 2. Cơ chế Xác thực Kép (Dual Auth)

- **Cookie Session (`CookieSessionAuthenticator`)**:
  - Đăng nhập qua `POST https://v2.api.axisstream.co/api/account/login` với payload `{email, password, rememberMe: false}`.
  - Dùng `asyncio.Lock` + biến `generation` đảm bảo chỉ 1 yêu cầu đăng nhập lại được thực hiện khi nhiều API song song gặp HTTP `401`.
  - Nếu tài khoản bật `twoFactorAuth`, trả ngay `AuthenticationError` tường minh thay vì treo.
- **API Exchange Scoped Token (`ApiExchangeTokenAuthenticator`)**:
  - Khi `AXISSTREAM_AUTH_MODE` là `"dual"` hoặc `"exchange_token"` và có `AXISSTREAM_EXCHANGE_TOKEN`, `LiveAxisStreamProvider` tạo `ResilientHttpClient` riêng gắn header `X-API-Key` chuyên phục vụ `AxisStreamExchangeClient`, kèm cảnh báo trước khi token hết hạn 30 ngày (`valid_until`).

---

## 3. Đặc thù Dữ liệu & Anti-Corruption Layer (ACL)

1. **Batch-to-Device Fallback (`LiveAxisStreamProvider.fetch_batch_telemetry`)**:
   - Gửi yêu cầu gộp `{"items": [...]}` tới `/device/{org}/batch`.
   - Nếu batch lỗi hoặc trả rỗng, tự động lặp từng thiết bị gọi endpoint lẻ `/device/{org}/{source}/{ext_id}/device` và đóng gói thiết bị lỗi vào `PartialError` (không đánh sập các thiết bị còn lại).
2. **Chặn dữ liệu rác Epoch 1970 (`NO_DATA` Guard)**:
   - Một số cảm biến mực nước (`waterlevel`) trả về timestamp sentinel `1970-01-01T00:00:00Z` hoặc `recentData` rỗng. ACL chuyển timestamp đó về `None` và gắn trạng thái chuẩn `NO_DATA`.
3. **Chuẩn hóa khóa & hướng gió (`WeatherTelemetryMapper`)**:
   - Hợp nhất `camelCase` và `snake_case` (`atmosPressure` ↔ `atmos_pressure`, `dewPoint` ↔ `dew_point`, `deltaT` ↔ `delta_t`, `solarRadiation` ↔ `solar_radiation`, `uvIndex` ↔ `uv_index`, `rainfallLast24hrs`).
   - Hướng gió dạng chuỗi 16 hướng (`"N"`, `"NNE"`, `"S"`, `"WSW"`, ...) được quy đổi sang độ `0.0° .. 337.5°`.
4. **API Exchange 17 cột (`tbncorp.weather`) + Derived Fallback**:
   - Bảng chuẩn 17 cột: `code`, `time`, `temperature_avg`, `humidity_avg`, `deltat_avg`, `dewpoint_avg`, `atmos_pressure_avg`, `msl_pressure`, `rainfall`, `rainfall_total`, `wind_speed_avg`, `wind_speed_min`, `wind_speed_max`, `wind_dir_deg_avg`, `wind_dir_var_avg`, `solar_rad_avg`, `uv_index_avg`.
   - Nếu API Exchange lỗi hoặc chưa kích hoạt token trên project, `LiveAxisStreamProvider.fetch_weather_exchange` tự dựng 1 dòng `WeatherExchangeRow` từ snapshot live mới nhất của Weather Station.
5. **Weather Forecast (MET Norway & Jane's Weather)**:
   - Tự dò `provider_id` từ danh sách Providers của project (fallback sang `DEFAULT_METNORWAY_PROVIDER_ID`).
   - Map vị trí (`location`), dự báo tổng quan (`days[]`) và từng giờ (`steps[]`), xử lý HTTP 404 từ Jane's Weather thành trạng thái `DISCONNECTED` an toàn.
6. **Smart Default Workspace**:
   - Go ERP `GetDashboard("")` tự động ưu tiên chọn Workspace/Project AxisTech đầu tiên có thiết bị đang hoạt động làm Workspace mặc định để bảng điều hành luôn có dữ liệu ngay khi mở trang.
