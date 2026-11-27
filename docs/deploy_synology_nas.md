# Hướng dẫn Triển khai Public 24/7 trên NAS Synology (Docker + Domain Miễn phí)

Tài liệu này hướng dẫn chạy **AxisTech ISO ERP (`axistech_bridge` + `axistech_erp`)** 24/7 ngay trên **NAS Synology (DSM 7.2+)** với 2 lựa chọn domain miễn phí: **Cloudflare Tunnel** (không cần mở port router, vượt CGNAT) hoặc **DDNS miễn phí `*.synology.me`**.

---

## Yêu cầu trên NAS Synology
- Model Synology hỗ trợ **Container Manager** (các dòng `+` như DS220+, DS224+, DS723+, DS920+, DS923+...; khuyến nghị RAM >= 2 GB).
- Vào **Package Center** cài đặt:
  - **Container Manager** (hoặc *Docker* trên DSM 7.1 trở xuống).
  - *(Tùy chọn)* **Git Server** nếu muốn `git clone` trực tiếp qua SSH.

---

## Bước 1 · Đưa mã nguồn lên NAS & tạo file `.env.prod`

1. Mở **File Station** trên DSM -> vào thư mục `/docker` -> tạo thư mục **`axistech-erp`**.
2. Đưa thư mục `axisstream_erp_platform` vào `/volume1/docker/axistech-erp` (tải ZIP từ GitHub về giải nén vào đây hoặc SSH vào NAS rồi chạy `git clone https://github.com/Phuc0901-pp/2026_axistech_module.git`).
3. Tại `/volume1/docker/axistech-erp/axisstream_erp_platform`:
   - Copy file `deploy/.env.prod.example` thành **`.env.prod`**.
   - Điền thông tin thực tế:
     - `PUBLIC_DOMAIN`: domain bạn sẽ dùng (ví dụ `agtech.tenban.dpdns.org` hoặc `agtech.tenban.synology.me`).
     - `AXISSTREAM_AXISSTREAM_USERNAME`, `AXISSTREAM_AXISSTREAM_PASSWORD`, `AXISSTREAM_AXISSTREAM_EXCHANGE_TOKEN`.
     - Tạo chuỗi ngẫu nhiên dài >= 32 ký tự cho `AXISSTREAM_INBOUND_API_KEY`, `BRIDGE_API_KEY` (2 giá trị này **phải giống nhau**), `AXISSTREAM_WEBHOOK_SECRET`, `AXISSTREAM_ENCRYPTION_KEY`, `ERP_API_KEY`, `ERP_ENCRYPTION_KEY`.
     - *(Hoặc nếu đã bật SSH trên NAS, chỉ cần chạy `bash deploy/setup_vps.sh` để tự sinh toàn bộ key ngẫu nhiên vào `.env.prod`.)*

---

## Bước 2 · Khởi chạy Docker trên Synology

### Cách A · Qua giao diện DSM (Container Manager)
1. Mở **Container Manager -> Project -> Create**.
2. Đặt **Project Name**: `axistech-erp`.
3. Chọn **Path**: `/docker/axistech-erp/axisstream_erp_platform`.
4. Chọn **Use existing docker-compose.yml** -> chọn tệp **`docker-compose.synology.yml`** (nếu giao diện Container Manager chỉ nhận tên mặc định `docker-compose.yml`, hãy đổi tên hoặc copy `docker-compose.synology.yml` thành `docker-compose.yml`).
5. Bấm **Next** -> hoàn tất để NAS tự build 2 image (`axistech_bridge` + `axistech_erp`) và khởi động ngầm 24/7.

### Cách B · Qua SSH (Nhanh nhất, hỗ trợ sẵn Cloudflare Tunnel `--profile tunnel`)
```bash
cd /volume1/docker/axistech-erp/axisstream_erp_platform
# Nếu dùng DDNS Synology Reverse Proxy:
docker compose -f docker-compose.synology.yml --env-file .env.prod up -d --build

# Nếu dùng Cloudflare Tunnel (khuyến nghị):
docker compose -f docker-compose.synology.yml --env-file .env.prod --profile tunnel up -d --build
```

> Lưu ý bảo mật: `axistech_bridge` (`:8001`) **chỉ chạy nội bộ**, còn `axistech_erp` chỉ mở loopback **`127.0.0.1:8088`** để Reverse Proxy trên chính NAS gọi vào.

---

## Bước 3 · Chọn 1 trong 2 Cách Public Domain Miễn phí

### Phương án 3A · Cloudflare Tunnel + Domain Miễn phí (Khuyến nghị — KHÔNG cần mở port Modem)
Phù hợp mọi đường truyền internet nhà/văn phòng (kể cả Viettel/VNPT/FPT bị CGNAT không có IP tĩnh).

1. Tạo domain miễn phí (như `.dpdns.org` trên DigitalPlat FreeDomain) hoặc dùng domain riêng -> thêm vào **Cloudflare (gói Free)**.
2. Vào **Cloudflare Zero Trust -> Networks -> Tunnels -> Create a tunnel**:
   - Chọn **Cloudflared** -> đặt tên (ví dụ `synology-axistech`).
   - Sao chép **Tunnel Token** dán vào dòng `CLOUDFLARE_TUNNEL_TOKEN=...` trong `.env.prod`.
   - Trong tab **Public Hostname -> Add a public hostname**:
     - **Hostname**: `agtech.domaincuaban.dpdns.org`
     - **Service Type**: `HTTP` · **URL**: `erp-platform:8080`
3. Chạy lại bằng SSH lệnh `--profile tunnel` ở Bước 2 (hoặc xóa dòng `profiles: ["tunnel"]` khỏi `docker-compose.synology.yml` nếu khởi động qua Container Manager GUI).
4. **Phân quyền ISO 27001 trong Cloudflare Access (Free 50 user)**:
   - Bảo vệ toàn bộ `/tbsgagtech/v1/overview`, `/tbsgagtech/v1/compliance/*` bằng OTP Email.
   - Đặt quy tắc **Bypass** cho `/tbsgagtech/v1/modules/*`, `/api/tbsgagtech/v1/modules/*`, `/js/*`, `/css/*`, `/vendor/*`, `/favicon.svg` để chia sẻ link/API thiết bị public cho đối tác.

### Phương án 3B · DDNS Miễn phí `*.synology.me` + Reverse Proxy có sẵn trên DSM
Áp dụng nếu đường truyền internet của bạn **có IPv4 Public (không bị CGNAT)** và truy cập được modem để mở port `443`:

1. **Tạo tên miền miễn phí của Synology**:
   - Vào **Control Panel -> External Access -> DDNS -> Add**.
   - Service provider: **Synology** · Hostname: `tencongty.synology.me` · Đăng nhập tài khoản Synology của bạn -> bấm **OK**.
2. **Mở Port trên Modem / Router**:
   - Port Forwarding **TCP `80`** và **TCP `443`** về IP nội bộ của NAS Synology.
3. **Cấp chứng chỉ HTTPS Let's Encrypt miễn phí**:
   - Vào **Control Panel -> Security -> Certificate -> Add -> Add a new certificate -> Get a certificate from Let's Encrypt**.
   - Domain name: `tencongty.synology.me` -> hoàn tất.
   - Sau đó vào **Settings** gán chứng chỉ vừa tạo cho reverse proxy rule bên dưới.
4. **Cấu hình Reverse Proxy nối vào Container (`127.0.0.1:8088`)**:
   - Vào **Control Panel -> Login Portal -> Advanced -> Reverse Proxy -> Create**:
     - **Reverse Proxy Name**: `AxisTech ISO ERP`
     - **Source**: Protocol `HTTPS` · Hostname `tencongty.synology.me` · Port `443` *(tích Enable HSTS)*
     - **Destination**: Protocol `HTTP` · Hostname `127.0.0.1` · Port `8088`
   - Chuyển sang tab **Custom Header -> Create -> WebSocket** (tự thêm header `Upgrade` & `Connection` giúp luồng **SSE real-time** `/api/erp/v1/events` không bị ngắt kết nối) -> bấm **Save**.

---

## Bước 4 · Kiểm tra & Sao lưu 24/7 trên NAS
1. Kiểm tra healthcheck: truy cập `https://<domain-cua-ban>/health/live` (trả về `200 OK`).
2. Kiểm tra dữ liệu đã đồng bộ: mở trang chính, bấm biểu tượng thu gọn Sidebar `#417` và kiểm tra tab **API Module Device** -> copy link `/tbsgagtech/v1/modules/devices/dev_...` mở trên mạng 4G điện thoại.
3. **Sao lưu tự động (Hyper Backup)**: Sao lưu định kỳ 2 Docker volume (`synology_bridge_data`, `synology_erp_data`) và file `.env.prod` sang NAS/Cloud dự phòng (lưu ý: nếu mất `.env.prod`, token AES-256-GCM và dữ liệu mã hóa cũ sẽ không giải mã được).
