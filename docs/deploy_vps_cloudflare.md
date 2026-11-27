# Hướng dẫn Triển khai Public 24/7 (VPS Linux Free + Docker + Cloudflare DNS/Proxy)

Tài liệu này hướng dẫn đưa toàn bộ hệ thống **AxisTech ISO ERP (`erp-platform` + `axisstream-bridge`)** lên VPS Linux chạy 24/7 với chi phí hosting **0đ**, tên miền riêng, HTTPS chuẩn ISO 27001 và bảo vệ cổng quản trị qua Cloudflare.

---

## Kiến trúc Mạng Public

```text
Internet / Thiết bị khác
   │ HTTPS (443) + WAF + DDoS Protection
   ▼
Cloudflare DNS + Proxy (Orange Cloud)
   │ Full (Strict) TLS
   ▼
Caddy Reverse Proxy (:80 / :443, SSE flush_interval -1)
   │ Docker internal bridge network (agtech_internal)
   ▼
erp-platform (:8080 nội bộ) ──► axisstream-bridge (:8001 nội bộ, KHÔNG mở port ra ngoài)
   │                                │
   ▼                                ▼
/data/erp_state.json (AES-GCM)   /data/bridge_state.db (SQLite + AEAD Outbox)
```

---

## Bước 1 · Tạo VPS Linux Free chạy 24/7

Chọn **1 trong 2** nhà cung cấp có gói **Always Free** trọn đời:

1. **Oracle Cloud Always Free (Khuyến nghị)**:
   - Tạo VM **Ubuntu 22.04 / 24.04**, shape `VM.Standard.A1.Flex` (Ampere ARM, miễn phí tới 4 OCPU / 24 GB RAM) hoặc `VM.Standard.E2.1.Micro`.
   - Trong **Virtual Cloud Network (VCN) -> Security List**, thêm **Ingress Rules** mở TCP port **`80`** và **`443`** từ `0.0.0.0/0` (giữ `22` để SSH).
   - Trên Oracle Ubuntu firewall mặc định (`iptables`), `deploy/setup_vps.sh` hoặc lệnh `ufw` cần đảm bảo cho phép port `80`/`443`.
2. **Google Cloud Always Free (`e2-micro`)**:
   - Region thuộc nhóm Always Free (`us-west1`, `us-central1`, `us-east1`), OS Ubuntu LTS, 30 GB Standard Persistent Disk, tích chọn **Allow HTTP traffic** & **Allow HTTPS traffic**.
   - Script `deploy/setup_vps.sh` tự tạo thêm **2 GB Swap** để build Docker mượt trên máy 1 GB RAM.

---

## Bước 2 · Tạo Domain Free & Trỏ Cloudflare DNS/Proxy

1. **Lấy Domain miễn phí (hoặc mua domain riêng)**:
   - Miễn phí: dùng **DigitalPlat FreeDomain** (`dash.domain.digitalplat.org`, cấp subdomain `.dpdns.org` / `.xx.kg` hỗ trợ nối nameserver trực tiếp về Cloudflare) hoặc các domain `.vn`/`.com` giá rẻ.
2. **Thêm Domain vào Cloudflare (Gói Free)**:
   - Đăng nhập Cloudflare Dashboard -> **Add a Site** -> nhập domain của bạn -> chọn gói **Free**.
   - Trỏ Nameserver ở nhà đăng ký domain sang 2 NS mà Cloudflare cung cấp.
3. **Tạo DNS Record trỏ về VPS**:
   - Vào **DNS -> Records -> Add record**:
     - **Type**: `A`
     - **Name**: `@` (hoặc subdomain như `agtech`, `erp`)
     - **IPv4 address**: IP Public của VPS Linux
     - **Proxy status**: **Proxied** (Đám mây cam)
4. **Cấu hình SSL/TLS chuẩn**:
   - Vào **SSL/TLS -> Overview** -> chọn **Full (Strict)** (Caddy trên VPS tự xin chứng chỉ Let's Encrypt hợp lệ cho kết nối End-to-End).
   - Kiểm tra **Network -> gRPC / WebSockets / HTTP/3** bật bình thường (SSE `/api/erp/v1/events` chạy trực tiếp qua HTTP/1.1 & HTTP/2 nhờ `flush_interval -1` trong `deploy/Caddyfile`).

---

## Bước 3 · Cài đặt & Chạy Docker trên VPS Linux

SSH vào VPS Linux và chạy tuần tự:

```bash
git clone https://github.com/Phuc0901-pp/2026_axistech_module.git
cd 2026_axistech_module/axisstream_erp_platform
bash deploy/setup_vps.sh
```

Mở file `.env.prod` vừa được tạo (đã tự sinh khóa `AES-256-GCM`, `AEAD` và API key ngẫu nhiên) để điền domain + tài khoản AxisStream thực tế:

```bash
nano .env.prod
```

Cập nhật các dòng sau:
- `PUBLIC_DOMAIN=agtech.yourdomain.com` *(khớp đúng record DNS ở Bước 2)*
- `AXISSTREAM_AXISSTREAM_USERNAME=...`
- `AXISSTREAM_AXISSTREAM_PASSWORD=...`
- `AXISSTREAM_AXISSTREAM_EXCHANGE_TOKEN=...`

Khởi chạy stack 24/7:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Kiểm tra trạng thái các container:

```bash
docker compose -f docker-compose.prod.yml ps
curl -s https://agtech.yourdomain.com/health/live
```

> **Tùy chọn Cloudflare Tunnel (Không cần mở port 80/443 trên VPS)**:  
> Tạo Tunnel trong **Cloudflare Zero Trust -> Networks -> Tunnels**, thêm Public Hostname trỏ thẳng `https://agtech.yourdomain.com` -> Service `http://erp-platform:8080`, dán token vào `CLOUDFLARE_TUNNEL_TOKEN` trong `.env.prod`, rồi chạy:  
> `docker compose -f docker-compose.prod.yml --env-file .env.prod --profile tunnel up -d --build`

---

## Bước 4 · Phân quyền Public Module vs Bảo vệ Trang Quản trị (ISO 27001)

Trong **Cloudflare Zero Trust -> Access -> Applications** (gói Free hỗ trợ tới **50 user**):

1. **Giữ Public cho đối tác / nhúng Iframe / REST API tích hợp**:
   - Không khóa đường dẫn:
     - `/tbsgagtech/v1/modules/*` (Trang ISO độc lập chỉ hiện 1 thiết bị / 1 điểm dự báo)
     - `/api/tbsgagtech/v1/modules/*` (REST API mã hóa AES-256-GCM token `dev_...` / `fcp_...`)
     - `/js/*`, `/css/*`, `/vendor/*`, `/favicon.svg`
2. **Bảo vệ trang Quản trị & Audit nội bộ**:
   - Tạo **Self-hosted Application** cho domain `agtech.yourdomain.com` với Path cụ thể:
     - `/tbsgagtech/v1/overview`, `/tbsgagtech/v1/telemetry`, `/tbsgagtech/v1/forecast`, `/tbsgagtech/v1/fields`, `/tbsgagtech/v1/assets`, `/tbsgagtech/v1/incidents`, `/tbsgagtech/v1/compliance/*`
     - Hoặc bảo vệ gốc `/` kèm chính sách **Bypass** riêng cho `/tbsgagtech/v1/modules/*`, `/api/tbsgagtech/v1/modules/*`, `/js/*`, `/css/*`, `/vendor/*`, `/favicon.svg` và **Allow (One-time PIN / Email)** cho danh sách email quản trị viên của bạn.
3. **Bảo vệ lệnh ghi `POST` (`ERP_REQUIRE_API_KEY=true`)**:
   - Trên production, `docker-compose.prod.yml` mặc định bật `ERP_REQUIRE_API_KEY=true`; mọi request `POST` tới `/api/erp/v1/*` bắt buộc phải kèm header `X-API-Key: <ERP_API_KEY>`.
