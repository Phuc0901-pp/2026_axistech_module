# ISO/IEC/IEEE 42010:2022 Architecture Description

> Xem thêm bản đồ chi tiết tại [BRAIN.md](../BRAIN.md), [01_SYSTEM_ARCHITECTURE.md](brain/01_SYSTEM_ARCHITECTURE.md) và [03_SECURITY_AND_ENCRYPTION.md](brain/03_SECURITY_AND_ENCRYPTION.md).

## 1. Stakeholders & Concerns
- **Enterprise AgTech Operations**: Real-time visibility into AxisTech (`AxisStream HQ`) field telemetry (`weather`, `soilprobe`, `waterlevel`, `waterflow`), geofenced farm boundaries on Google Satellite, 17-column exchange datasets, MET Norway / Jane's Weather forecasts, and ISO incident lifecycle (`OPEN -> ACKNOWLEDGED -> RESOLVED`).
- **Integration Engineering**: Isolate upstream API quirks (stringified numbers, epoch `1970-01-01` sentinels, `moist` vs `moisture`, partial batch failures) behind a strict Hexagonal Anti-Corruption Layer (`axisstream/`).
- **Cybersecurity & Compliance**: Zero hardcoded credentials (`init.js` gitignored and never served), strict HTTPS/TLS host-suffix whitelists, AES-256-GCM & HKDF-SHA256-CTR-HMAC-SHA256 at-rest encryption, tamper-evident SHA-256 hash-chained audit logs, per-IP rate limiting, strict CSP/HSTS, and redacted structured logs.

## 2. Architecture Viewpoints
1. **Context Viewpoint**: AxisTech Cloud (`*.axisstream.co`) -> Python `axisstream-bridge` (Hexagonal ACL + Encrypted Outbox + SQLite WAL `telemetry_history` + REST/SSE Gateway on `:8001`) -> Golang `erp-platform` (Encrypted State + Hash-Chained Audit + Security Middleware + Embedded Enterprise ERP UI on `:8088`).
2. **Layering Viewpoint (Hexagonal / Ports & Adapters)**:
   - `domain/` (`models.py`, `normalizers.py`, `ports.py`): Zero dependency on `httpx`, `fastapi`, or `sqlite3` (enforced by `UT-012`).
   - `application/` (`sync_service.py`, `live_provider.py`, `demo_provider.py`): Incremental cursor orchestration, SHA-256 deduplication, 24h device history hydration, SSE fan-out, fail-open enrichment consumer.
   - `infrastructure/` (`http/`, `auth/`, `axisstream/`, `security/`, `storage/`): Circuit Breaker (`CLOSED/OPEN/HALF_OPEN`), Token Bucket Rate Limiter, Single-Flight Cookie Re-Auth, AEAD FieldEncryptor (`crypto.py`), SQLite WAL state/history/outbox store.
   - `interfaces/` (`api/`): OpenAPI 3.1 REST + `/telemetry/history` + `/security/posture` + SSE + RFC 9457 Problem JSON + HMAC-SHA256 webhooks.
3. **Presentation Viewpoint (Embedded Enterprise ISO ERP)**:
   - Served directly from Go `//go:embed static` with offline `Leaflet` + `Lucide`, Google Satellite tiles (`mt0..mt3.google.com`), 3-step cascading workflow (`Workspace -> Device -> Split Component Graphs`), 24h history hydration, and `Compliance & Security` audit chain dashboard.
4. **ISO 8601 / ISO 80000 / RFC 7946 Data Canonicalization**:
   - All timestamps normalized to timezone-aware UTC (`1970-01-01` sentinels mapped to `None` / `NO_DATA`).
   - All units normalized via `UNIT_REGISTRY` (`°C`, `%`, `mm`, `hPa`, `km/h`, `W/m²`, `L`, `m`, `V`, `dBm`, `µS/cm`, `ppm`, `mg/kg`, `CSQ`, `pH`).
   - GeoJSON Polygons validated for WGS84 coordinate bounds and closed rings.
