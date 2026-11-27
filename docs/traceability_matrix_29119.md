# ISO/IEC/IEEE 29119 Traceability Matrix (`Requirement <-> Ticket <-> Unit Test`)

| Requirement | Prompt / Ticket | Test ID | Verification Scope |
|---|---|---|---|
| REQ-SEC-01: HTTPS & Host Whitelist | AXS-P1-T2 | UT-001 | Reject HTTP downgrade & non-AxisStream hosts |
| REQ-SEC-02: SecretStr Isolation | AXS-P1-T2 | UT-002 | Mask secrets in `repr()` and `str()` |
| REQ-SEC-03: Log Secret/PII Redaction | AXS-P1-T3 | UT-003 | Redact passwords, cookies, Bearer tokens in JSON logs |
| REQ-OBS-01: Correlation ID Context | AXS-P1-T3 | UT-004 | Generate & propagate UUIDv4 `correlation_id` |
| REQ-ERR-01: Domain Error Taxonomy | AXS-P1-T4 | UT-005 | Map retryability, HTTP hints, and redact `details` |
| REQ-ISO-01: Mixed Date -> UTC ISO 8601 | AXS-P2-T2 | UT-006 | Parse ISO-8601, US short date, and locale AM/PM |
| REQ-ISO-02: Epoch Sentinel Guard | AXS-P2-T2 | UT-007 | Map `1970-01-01` & blank dates to `None` (`NO_DATA`) |
| REQ-ISO-03: Numeric String Parsing | AXS-P2-T3 | UT-008 | Parse `"0.00"`, `"-92"`, reject `NaN`/`Infinity` |
| REQ-ISO-04: ISO 80000 Unit Registry | AXS-P2-T3 | UT-009 | Normalize `degC`, `kph`, `W/m2`, `VIC` |
| REQ-GEO-01: GeoJSON Boundary Check | AXS-P2-T4 | UT-010 | Validate WGS84 bounds & closed polygon rings |
| REQ-DOM-01: Immutable TZ-Aware Models | AXS-P2-T1 | UT-011 | Enforce frozen models & aware UTC timestamps |
| REQ-ARC-01: Hexagonal Layer Guard | AXS-P2-T1 | UT-012 | AST check: zero infra imports inside `domain/` |
| REQ-REL-01: Circuit Breaker FSM | AXS-P3-T1 | UT-013 | Verify `CLOSED -> OPEN -> HALF_OPEN -> CLOSED` |
| REQ-REL-02: Token Bucket Rate Limit | AXS-P3-T2 | UT-014 | Deterministic burst & refill rate limiting |
| REQ-REL-03: Retry + Jitter + Retry-After | AXS-P3-T3 | UT-015 | Retry 503/429 with `Retry-After`; skip 404 |
| REQ-SEC-04: Single-Flight Re-Auth | AXS-P3-T4 | UT-016 | 10 concurrent 401s trigger exactly 1 `login()` |
| REQ-SEC-05: Anti-401-Loop Guard | AXS-P3-T3 | UT-017 | Stop after 1 failed re-auth attempt |
| REQ-SEC-06: TLS & Redirect Whitelist | AXS-P3-T3 | UT-018 | Block HTTP & cross-domain 302 redirects |
| REQ-SEC-07: Exchange Token Expiry | AXS-P3-T4 | UT-019 | Warn before expiry & block expired tokens |
| REQ-SEC-08: Error Log Non-Leakage | AXS-P3-T3 | UT-020 | Verify cookie never appears in HTTP error logs |
| REQ-ACL-01: Project & RBAC Mapping | AXS-P4-T3 | UT-021 | Map `TANBAOCORP_Demo` & `TBSG` org schemas |
| REQ-ACL-02: Device Inventory Mapping | AXS-P4-T3 | UT-022 | Map all 4 sensor devices & coordinates |
| REQ-ACL-03: Field GeoJSON Mapping | AXS-P4-T3 | UT-023 | Map `TRUONG TON FARM` polygon & empty `TBSG` sites |
| REQ-ACL-04: Asset Registry Mapping | AXS-P4-T3 | UT-024 | Map `Water Tank` & `Cultivator` optional fields |
| REQ-ACL-05: Exchange Schema Mapping | AXS-P4-T3 | UT-025 | Map `TBSG` token & 17 `tbncorp.weather` columns |
| REQ-ACL-06: Safe Auto-Pagination | AXS-P4-T2 | UT-026 | Empty, multi-page, and `max_pages` cap |
| REQ-ACL-07: Schema Drift Guard | AXS-P4-T3 | UT-027 | Warn on extra keys; raise `SchemaDriftError` on missing PK |
| REQ-TEL-01: WaterFlow Mapper | AXS-P5-T2 | UT-028 | Map `79DA26E0` string metrics & signal dBm |
| REQ-TEL-02: SoilProbe Multi-Depth | AXS-P5-T2 | UT-029 | Reconcile `moist` -> `moisture` across depths 1..3 |
| REQ-TEL-03: WaterLevel Empty/Epoch | AXS-P5-T2 | UT-030 | Classify `20001DC4` empty payload as `NO_DATA` |
| REQ-TEL-04: Weather + Derived Fallback | AXS-P5-T2 | UT-031 | Map 12 metrics; tolerate 404/500 on `eto`/`indices` |
| REQ-TEL-05: Batch Partial Isolation | AXS-P5-T3 | UT-032 | Preserve 200 snapshots while isolating 404/500 items |
| REQ-TEL-06: Date Range Chunking | AXS-P5-T3 | UT-033 | Split multi-month ranges & reject `start > end` |
| REQ-TEL-07: Timezone Query -> UTC | AXS-P5-T1 | UT-034 | Send `localTimeZone`, emit UTC readings |
| REQ-TEL-08: Generic Sensor Fallback | AXS-P5-T2 | UT-035 | Handle unknown `sourceCode` without crashing |
| REQ-ALR-01: Alert Policies & Templates | AXS-P6-T1 | UT-036 | Map `Strong wind alert` & 8 template operators |
| REQ-SYN-01: SHA-256 Deduplication | AXS-P6-T2 | UT-037 | Ignore duplicate `(org, device, metric, ts)` |
| REQ-SYN-02: Rollback-Safe Cursor | AXS-P6-T3 | UT-038 | Do not advance watermark if upstream sync fails |
| REQ-SYN-03: Outbox & Dead-Letter Queue | AXS-P6-T2 | UT-039 | Transition `PENDING -> DELIVERED / DEAD_LETTER` |
| REQ-SYN-04: SQLite Restart Persistence | AXS-P6-T2 | UT-040 | Retain cursors & pending outbox across reopen |
| REQ-ALR-02: Empty History Tolerance | AXS-P6-T1 | UT-041 | Safely handle empty response body from alert log |
| REQ-API-01: Inbound X-API-Key Guard | AXS-P7-T2 | UT-042 | Constant-time API key check returning RFC 9457 401 |
| REQ-API-02: Gateway REST Contracts | AXS-P7-T1 | UT-043 | Verify devices, telemetry, fields, assets, alerts, exchange |
| REQ-API-03: Health & Readiness Probes | AXS-P7-T1 | UT-044 | `/health/ready` returns 503 when Circuit Breaker `OPEN` |
| REQ-API-04: RFC 9457 Problem JSON | AXS-P7-T1 | UT-045 | Map domain errors to Problem JSON without stack traces |
| REQ-API-05: Outbound Webhook HMAC | AXS-P7-T3 | UT-046 | Sign & verify `X-Signature-256` payload integrity |
| REQ-API-06: Metrics & Sync Trigger | AXS-P7-T1 | UT-047 | Trigger sync and inspect counters via `/metrics` |
| REQ-API-07: Fail-Open Consumer | AXS-P7-T4 | UT-048 | Enrich external record without blocking on outage |
| REQ-QA-01: Full E2E Mocked Pipeline | AXS-P8-T1 | UT-049 | End-to-end sync over `respx`-mocked AxisStream APIs |
| REQ-QA-02: Static Secret Scan | AXS-P8-T2 | UT-050 | Verify zero real credentials exist in repository |
| REQ-QA-03: SSRF / Path Traversal Guard | AXS-P8-T2 | UT-051 | Block `..`, `/`, `@` in path segments |
| REQ-QA-04: 15,000-Row SLA Benchmark | AXS-P8-T3 | UT-052 | Map 15,000 `tbncorp.weather` rows under SLA |
| REQ-QA-05: OpenAPI 3.1 Verification | AXS-P8-T4 | UT-053 | Validate generated OpenAPI schema & paths |
| REQ-QA-06: ISO 29119 Matrix Check | AXS-P8-T4 | UT-054 | Verify all 82 test IDs exist in matrix |
| REQ-ERP-01: Go Config ENV Loading | ERP-P1-T1 | G-UT-001 | Load `ERP_*` / `BRIDGE_*` env config defaults & overrides |
| REQ-ERP-02: Go Config Validation | ERP-P1-T1 | G-UT-002 | Reject invalid bridge URL or port range |
| REQ-ERP-03: Go Config Secret Masking | ERP-P1-T1 | G-UT-003 | `Config.String()` masks `BridgeAPIKey` & `ERPAPIKey` |
| REQ-ERP-04: Go JSON Slog Output | ERP-P1-T2 | G-UT-004 | Emit valid JSON log lines with ISO timestamps |
| REQ-ERP-05: Go ISO 27001 Log Redact | ERP-P1-T2 | G-UT-005 | Redact `password`, `api_key`, `cookie`, `token` attributes |
| REQ-ERP-06: Bridge Client Auth Headers | ERP-P2-T1 | G-UT-006 | Send `X-API-Key` and `X-Correlation-ID` to Python bridge |
| REQ-ERP-07: Bridge Client Retry 503 | ERP-P2-T1 | G-UT-007 | Retry transient 503 and recover on 200 |
| REQ-ERP-08: Bridge Client No-Retry 404 | ERP-P2-T1 | G-UT-008 | Do not retry 4xx errors & trip Circuit Breaker on 5xx |
| REQ-ERP-09: Bridge SSE Stream Parser | ERP-P2-T1 | G-UT-009 | Parse live SSE `event:` + `data:` frames from bridge |
| REQ-ERP-10: Telemetry Deduplication | ERP-P3-T1 | G-UT-010 | Deduplicate readings by `(device_id, metric, timestamp)` |
| REQ-ERP-11: Thread-Safe Store Concurrency | ERP-P3-T1 | G-UT-011 | Parallel reads/writes without race or panic |
| REQ-ERP-12: Incident Status Preservation | ERP-P3-T1 | G-UT-012 | Upsert alerts without resetting `ACKNOWLEDGED`/`RESOLVED` |
| REQ-ERP-13: Immutable Audit Log | ERP-P3-T1 | G-UT-013 | Append-only audit trail preserves chronological entries |
| REQ-ERP-14: Atomic File Persistence | ERP-P3-T1 | G-UT-014 | Save & reload store across restart via atomic rename |
| REQ-ERP-15: Executive KPI Aggregation | ERP-P4-T1 | G-UT-015 | Compute `LIVE`/`NO_DATA`, incidents, weather summary |
| REQ-ERP-16: Incident Ack/Resolve FSM | ERP-P4-T1 | G-UT-016 | Enforce `OPEN -> ACKNOWLEDGED -> RESOLVED` transitions |
| REQ-ERP-17: Weather CSV RFC 4180 Export | ERP-P4-T1 | G-UT-017 | Export all 17 `tbncorp.weather` columns to CSV |
| REQ-ERP-18: SyncWorker Partial Tolerance | ERP-P4-T2 | G-UT-018 | Continue syncing other projects if one project errors |
| REQ-ERP-19: SyncWorker SSE Broadcast | ERP-P4-T2 | G-UT-019 | Broadcast `sync_update` to SSE Hub after sync |
| REQ-ERP-20: SSE Multi-Client Fan-Out | ERP-P5-T1 | G-UT-020 | Deliver events to multiple concurrent SSE subscribers |
| REQ-ERP-21: SSE Unsubscribe Cleanup | ERP-P5-T1 | G-UT-021 | Remove subscriber channels cleanly on disconnect |
| REQ-ERP-22: SSE Slow-Consumer Drop | ERP-P5-T1 | G-UT-022 | Drop slow client buffer without blocking broadcaster |
| REQ-ERP-23: ERP REST Query Endpoints | ERP-P6-T1 | G-UT-023 | Serve `/dashboard`, `/devices`, `/telemetry`, `/fields`, `/assets` |
| REQ-ERP-24: Incident Workflow API + Audit | ERP-P6-T1 | G-UT-024 | Acknowledge/resolve via HTTP POST & record audit entry |
| REQ-ERP-25: ISO 27001 Security Headers | ERP-P6-T2 | G-UT-025 | Enforce `X-Frame-Options: DENY`, `nosniff`, CSP |
| REQ-ERP-26: RFC 9457 Error Responses | ERP-P6-T2 | G-UT-026 | Return `application/problem+json` on invalid state/input |
| REQ-ERP-27: Embedded ISO Dashboard UI | ERP-P6-T3 | G-UT-027 | Serve embedded `index.html`, `styles.css`, `app.js` |
| REQ-ERP-28: ERP Health & Ready Probes | ERP-P6-T1 | G-UT-028 | Expose `/health/live` and `/health/ready` |
| REQ-LIVE-01: AxisStream Cookie Login | AXS-P9-T1 | UT-055 | `POST /api/account/login` cookie extraction without secret leak |
| REQ-LIVE-02: Batch `items[]` Contract | AXS-P9-T2 | UT-056 | Send exact `{"items": [...]}` to `data.api.axisstream.co` |
| REQ-LIVE-03: Weather CamelCase + Rain24h | AXS-P9-T2 | UT-057 | Parse `atmosPressure`, `windDirection="S"`, `rainfallLast24hrs` |
| REQ-LIVE-04: Live Alert History List | AXS-P9-T3 | UT-058 | Parse `title`, `alertPolicy.name`, `notificationLogCount.logCount` |
| REQ-FC-01: MET Norway 7-Day & Steps | AXS-P9-T4 | UT-059 | Map MET Norway `location`, 7 `days[]`, and `steps[]` |
| REQ-FC-02: Jane's Weather & Spray | AXS-P9-T4 | UT-060 | Map `spray.windows[]` and handle 404 as `DISCONNECTED` |
| REQ-LIVE-05: Live Mode Wiring & Route | AXS-P9-T5 | UT-061 | Select `LiveAxisStreamProvider` & serve `/forecast` |
| REQ-LIVE-06: Live Provider E2E Sync | AXS-P9-T5 | UT-062 | Sync projects, telemetry, exchange & forecast end-to-end |
| REQ-ERP-29: Go Forecast Bridge Client | ERP-P7-T1 | G-UT-029 | Fetch & decode `ProjectForecastBundle` from Python bridge |
| REQ-ERP-30: Go Forecast Persistence | ERP-P7-T1 | G-UT-030 | Persist & reload forecast bundle across restart |
| REQ-ERP-31: Go Forecast Dashboard Sync | ERP-P7-T2 | G-UT-031 | Populate `DashboardSummary.Forecast` on `SyncOnce` |
| REQ-ERP-32: Go Forecast API & UI Tab | ERP-P7-T3 | G-UT-032 | Serve `/api/erp/v1/forecast` and `#tab-forecast` UI |
| REQ-UI-01: Google Satellite CSP Security | ERP-P8-T1 | G-UT-033 | Whitelist `mt0..mt3.google.com` tiles with strict `script-src 'self'` |
| REQ-UI-02: Local Vendor & Modular Embed | ERP-P8-T1 | G-UT-034 | Serve embedded Leaflet, Lucide, Map Engine, Charts & Inspector |
| REQ-UI-03: Satellite Map Data Contracts | ERP-P8-T2 | G-UT-035 | Verify `/dashboard` & `/fields` supply map polygons & coordinates |
| REQ-UI-04: Device Inspector Data APIs | ERP-P8-T3 | G-UT-036 | Verify `/telemetry?device_id=` & `/alerts/history` for Drawer |
| REQ-UI-05: ISA-101 Command UI Wiring | ERP-P8-T4 | G-UT-037 | Verify Satellite containers, Drawer, Ctrl+K Search & Lucide UI |
| REQ-SEC-09: AEAD FieldEncryptor & Tamper Reject | AXS-SEC-T1 | UT-063 | `HKDF-SHA256-CTR-HMAC-SHA256` (`ENC:v1:`) roundtrip, wrong-key & tamper rejection |
| REQ-SEC-10: Encrypted SQLite Outbox At Rest | AXS-SEC-T2 | UT-064 | Persist `outbox_events.payload_json` as ciphertext; verify unreadable without key |
| REQ-P0-01: SQLite Telemetry History & Route | AXS-SEC-T3 | UT-065 | Persist canonical telemetry & expose `/api/v1/projects/{id}/telemetry/history` |
| REQ-SEC-11: Security Posture & HSTS Headers | AXS-SEC-T4 | UT-066 | Expose `/api/v1/security/posture` + `Strict-Transport-Security` & `Permissions-Policy` |
| REQ-REL-04: LiveProvider Fallback Resilience | AXS-SEC-T5 | UT-067 | Verify batch->per-device fallback, degraded endpoints, derived exchange & forecasts |
| REQ-LIVE-07: Dual Cookie + Exchange Token Auth | AXS-SEC-T6 | UT-068 | Wire dual cookie session and scoped exchange token `X-API-Key` client |
| REQ-ISO-05: AxisTech Scope & Secret Masking | AXS-SEC-T7 | UT-069 | Assert zero removed legacy vendor refs in code/UI/docs & masked `SecretStr` |
| REQ-SYN-05: Persistent SQLite 24h History | AXS-SEC-T8 | UT-070 | Persist `telemetry_history` cleanly across SQLite reopen |
| REQ-SEC-12: Go AES-256-GCM File Envelope | ERP-SEC-T1 | G-UT-038 | Encrypt/decrypt state with `AES-256-GCM`, reject wrong key & tampered bytes |
| REQ-SEC-13: SHA-256 Tamper-Evident Audit Chain | ERP-SEC-T2 | G-UT-039 | Link `AuditEntry` via `prev_hash -> entry_hash` and detect forged details |
| REQ-SEC-14: Encrypted Store & Security Status API | ERP-SEC-T3 | G-UT-040 | Persist encrypted `erp_state.json` & expose `/api/erp/v1/security/status` |
| REQ-UI-06: Pure Lucide AxisTech ERP Workflow | ERP-SEC-T4 | G-UT-041 | Verify 100% Lucide icons (zero chibi/removed legacy) & 3-step ERP cascading UI |
| REQ-UI-07: API Module Device, Split Graphs & Favicon | ERP-SEC-T5 | G-UT-042 | HiDPI `renderRealtimeSeries`, `#tab-api-module` (no `#tab-exchange`), security grid & `/favicon.svg` |
| REQ-P0-04: Go BridgeClient History Proxy | ERP-P11-T1 | G-UT-043 | `FetchTelemetryHistory` calls bridge `/telemetry/history` with query |
| REQ-P0-03: ERP Telemetry History Proxy | ERP-SEC-T7 | G-UT-044 | Serve `/api/erp/v1/telemetry/history` & hydrate UI split graphs across `F5` |
| REQ-SEC-15: Per-IP Rate Limit & API Key Guard | ERP-SEC-T6 | G-UT-045 | Enforce constant-time `X-API-Key` on `POST` mutations (`401`) & sliding-window `429` |
| REQ-FC-03: MET Norway WGS84 Location Extract | AXS-API-T1 | UT-071 | Extract forecast `location.{name, latitude, longitude, elevation, time_zone}` within WGS84 bounds |
| REQ-UI-08: API Module 1 Data + 1 Graph (10/page) | ERP-API-T1 | G-UT-046 | Verify `Devices` & `Forecast` modes, `API_MODULE_PAGE_SIZE = 10` & single-scale paired view |
| REQ-GEO-02: Forecast Geolocation Map & Guard | ERP-API-T2 | G-UT-047 | Verify `renderForecastLocation`, `forecastGroup` & `resolveForecastLocation` WGS84 guard |
| REQ-API-08: Forecast & Device Coords API | ERP-API-T3 | G-UT-048 | Verify `/api/erp/v1/forecast` & `/devices` serve live target coordinates for map pin |
| REQ-SEC-16: AES-256-GCM Opaque Module Tokens | TBSG-API-T1 | G-UT-049 | Encode/decode deterministic `dev_...`/`fcp_...` tokens; reject wrong-key & tampering |
| REQ-API-09: Portable `tbsgagtech` Module REST APIs | TBSG-API-T2 | G-UT-050 | Serve `/api/tbsgagtech/v1/modules/{catalog,devices/,forecast/}` & RFC 9457 400 bad token |
| REQ-UI-09: ISO Deep-Link SPA Routing (`/tbsgagtech/v1/*`) | TBSG-API-T3 | G-UT-051 | Serve full ERP SPA on `/tbsgagtech/v1/overview` & isolated module on `/modules/...` |
| REQ-UI-10: Standalone ISO Page Strips ERP Chrome | TBSG-ISO-T1 | G-UT-052 | Serve `module-view.html` without sidebar, topbar, project switcher, or audit tabs |
| REQ-SEC-17: Isolated Client Least-Privilege & AutoSync | TBSG-ISO-T2 | G-UT-053 | Verify `module-view.js` only calls `/modules/`, listens to SSE `sync_update` + 15s poll |
| REQ-API-10: Device Module `available_metrics` & Filter | TBSG-ISO-T3 | G-UT-054 | Return `available_metrics`, `power_state`, GPS, `page_size=10` & single-metric chart |
| REQ-SEC-18: Standalone Token Isolation & Admin Routes | TBSG-ISO-T4 | G-UT-055 | Reject forged `fcp_` tokens (`400`) while keeping admin `/tbsgagtech/v1/*` intact |
| REQ-UI-11: Vietnamese Metric & Tooltip Standardization | TBSG-ISO-T5 | G-UT-056 | Standardize all device & point-forecast labels + tooltips (`getMetricMeta`) across ISO module & ERP UI |
