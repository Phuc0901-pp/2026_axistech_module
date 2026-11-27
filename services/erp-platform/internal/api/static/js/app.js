/* AxisTech ISO ERP Main Application Controller (Pure Lucide + Enterprise 3-Step Flow + Security Posture) */
(() => {
  const MAX_SERIES_POINTS = 48;
  const PAGE_SIZE = 20;
  const API_MODULE_PAGE_SIZE = 10;
  const TAB_ROUTES = {
    overview: "/tbsgagtech/v1/overview",
    telemetry: "/tbsgagtech/v1/telemetry",
    forecast: "/tbsgagtech/v1/forecast",
    fields: "/tbsgagtech/v1/fields",
    assets: "/tbsgagtech/v1/assets",
    "api-module": "/tbsgagtech/v1/modules",
    incidents: "/tbsgagtech/v1/incidents",
    audit: "/tbsgagtech/v1/compliance/audit",
  };

  const state = {
    projectId: "",
    selectedDeviceId: "",
    selectedMetricFilter: "ALL",
    activeTab: "overview",
    routeApplied: false,
    auditPage: 1,
    alertHistoryPage: 1,
    apiModuleMode: "devices",
    apiModuleDeviceId: "",
    apiModuleMetric: "",
    apiModuleForecastMetric: "temperature",
    apiModulePage: 1,
    moduleCatalog: { devices: [], forecasts: [] },
    theme: localStorage.getItem("axs_theme") || "dark",
    dash: null,
    security: null,
    fields: [],
    assets: [],
    policies: [],
    alertHistory: [],
    incidents: [],
    exchangeRows: [],
    exchangeTokens: [],
    forecast: null,
    audit: [],
    seriesHistory: {}, // { deviceId: { seriesKey: [{ t, v, label, unit }] } }
  };

  document.documentElement.dataset.theme = state.theme;
  const $ = (id) => document.getElementById(id);

  const api = async (path, opts) => {
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };

  function badge(status) {
    const s = String(status || "").toUpperCase();
    if (["LIVE", "ACTIVE", "RESOLVED", "CONNECTED", "DELIVERED"].includes(s)) return `<span class="badge badge-ok">${s}</span>`;
    if (["ACKNOWLEDGED", "PAUSED", "LATE", "DISCONNECTED", "PENDING"].includes(s)) return `<span class="badge badge-warn">${s}</span>`;
    if (["OPEN", "OFFLINE", "HIGH", "CRITICAL", "FAILED"].includes(s)) return `<span class="badge badge-danger">${s}</span>`;
    if (s === "NO_DATA") return `<span class="badge badge-muted">NO_DATA</span>`;
    return `<span class="badge badge-info">${s || "N/A"}</span>`;
  }

  function getDevicePowerState(dev, snap) {
    const devActive = dev ? dev.active !== false : true;
    const snapStatus = String(snap?.status || "UNKNOWN").toUpperCase();
    const rawTs = snap?.latest_timestamp_utc || snap?.readings?.[0]?.timestamp_utc || "";
    const tsMs = rawTs ? Date.parse(rawTs) : NaN;
    const intervalMatch = String(snap?.metadata?.reading_interval || "").match(/(\d+)/);
    const intervalMins = intervalMatch ? Number(intervalMatch[1]) : 15;
    const staleMs = Math.max(6 * 3600 * 1000, intervalMins * 6 * 60 * 1000);
    const ageMs = isFinite(tsMs) ? Date.now() - tsMs : Infinity;
    const isFresh = isFinite(tsMs) && ageMs <= staleMs;
    const isOn = devActive && snapStatus === "LIVE" && isFresh;

    let reason = "No Signal";
    if (!devActive) reason = "Disabled";
    else if (snapStatus === "OFFLINE") reason = "Offline";
    else if (!isFinite(tsMs) || snapStatus === "NO_DATA") reason = "No Signal";
    else if (!isFresh) {
      const hoursAgo = Math.max(1, Math.round(ageMs / 3600000));
      reason = hoursAgo >= 24 ? `Offline ${Math.round(hoursAgo / 24)}d ago` : `Offline ${hoursAgo}h ago`;
    } else reason = "Active";

    return { isOn, label: isOn ? "ON" : "OFF", reason };
  }
  window.getDevicePowerState = getDevicePowerState;

  function powerBadge(dev, snap) {
    const p = getDevicePowerState(dev, snap);
    const ic = window.ERPIcons ? window.ERPIcons.iconHtml(p.isOn ? "power" : "power-off", 12) : "";
    return `<span class="power-pill ${p.isOn ? "on" : "off"}" title="Power: ${p.label} (${p.reason})"><span class="power-dot"></span>${ic}<span>${p.label}</span><small style="opacity:0.8;font-weight:500;">· ${p.reason}</small></span>`;
  }

  function renderTablePagination(pagerEl, totalItems, currentPage, pageSize, onPageChange) {
    if (!pagerEl) return 1;
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    const safePage = Math.min(Math.max(1, currentPage), totalPages);
    if (!totalItems) {
      pagerEl.innerHTML = `<span class="kpi-sub">0 records (20 records/page)</span>`;
      return 1;
    }
    const startIdx = (safePage - 1) * pageSize + 1;
    const endIdx = Math.min(totalItems, safePage * pageSize);

    let pageButtons = "";
    const winStart = Math.max(1, safePage - 2);
    const winEnd = Math.min(totalPages, safePage + 2);
    for (let p = winStart; p <= winEnd; p++) {
      pageButtons += `<button type="button" class="page-btn ${p === safePage ? "active" : ""}" data-page="${p}">${p}</button>`;
    }

    pagerEl.innerHTML = `
      <span class="tabular-nums">Showing <strong>${startIdx}-${endIdx}</strong> of <strong>${totalItems}</strong> records (${pageSize}/page)</span>
      <div class="page-controls">
        <button type="button" class="page-btn" data-page="${safePage - 1}" ${safePage <= 1 ? "disabled" : ""}>Prev</button>
        ${pageButtons}
        <button type="button" class="page-btn" data-page="${safePage + 1}" ${safePage >= totalPages ? "disabled" : ""}>Next</button>
      </div>
    `;
    pagerEl.querySelectorAll(".page-btn[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextPage = Number(btn.dataset.page);
        if (nextPage >= 1 && nextPage <= totalPages && nextPage !== safePage) {
          onPageChange(nextPage);
        }
      });
    });
    return safePage;
  }

  function weatherLucideIcon(symbol = "") {
    const s = String(symbol || "").toLowerCase();
    if (s.includes("thunder")) return "cloud-lightning";
    if (s.includes("rain") || s.includes("sleet")) return "cloud-rain";
    if (s.includes("snow")) return "snowflake";
    if (s.includes("fog")) return "cloud-fog";
    if (s.includes("clear") || s.includes("fair")) return "sun";
    if (s.includes("partly")) return "cloud-sun";
    if (s.includes("cloud")) return "cloud";
    return "cloud-sun";
  }

  function formatWorkspaceLabel(p) {
    return `${p.name} (${p.organisation?.schema_name || "tbncorp"})`;
  }

  function pushSeriesPoint(deviceId, key, label, unit, timeLabel, value) {
    const num = Number(value);
    if (!deviceId || !isFinite(num)) return;
    if (!state.seriesHistory[deviceId]) state.seriesHistory[deviceId] = {};
    if (!state.seriesHistory[deviceId][key]) state.seriesHistory[deviceId][key] = [];
    const buf = state.seriesHistory[deviceId][key];
    const tStr = String(timeLabel || new Date().toISOString().slice(11, 19));
    const prev = buf[buf.length - 1];
    if (prev && prev.t === tStr && Math.abs(prev.v - num) < 1e-6) return;
    buf.push({ t: tStr, v: num, label, unit: unit || "" });
    if (buf.length > MAX_SERIES_POINTS) buf.shift();
  }

  const EXCHANGE_COLUMN_SPECS = [
    { col: "temperature_avg", key: "temperature", title: "Nhiệt độ không khí", unit: "°C", icon: "thermometer-sun", cat: "thermal", color: "#38bdf8" },
    { col: "dewpoint_avg", key: "dew_point", title: "Điểm sương", unit: "°C", icon: "thermometer", cat: "thermal", color: "#a78bfa" },
    { col: "deltat_avg", key: "delta_t", title: "Chỉ số Delta-T (Bốc hơi)", unit: "°C", icon: "droplets", cat: "thermal", color: "#fb7185" },
    { col: "humidity_avg", key: "humidity", title: "Độ ẩm tương đối", unit: "%", icon: "droplet", cat: "moisture", color: "#22c55e" },
    { col: "rainfall", key: "rainfall", title: "Lượng mưa (1 giờ)", unit: "mm", icon: "cloud-rain", cat: "moisture", color: "#38bdf8" },
    { col: "rainfall_total", key: "rainfall_total", title: "Lượng mưa tích lũy", unit: "mm", icon: "cloud-rain-wind", cat: "moisture", color: "#14b8a6" },
    { col: "atmos_pressure_avg", key: "atmos_pressure", title: "Áp suất khí quyển", unit: "hPa", icon: "gauge", cat: "wind_pressure", color: "#60a5fa" },
    { col: "msl_pressure", key: "msl_pressure", title: "Áp suất mực nước biển", unit: "hPa", icon: "gauge", cat: "wind_pressure", color: "#818cf8" },
    { col: "wind_speed_avg", key: "wind_speed", title: "Tốc độ gió TB", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#f59e0b" },
    { col: "wind_speed_min", key: "wind_speed_min", title: "Tốc độ gió nhỏ nhất", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#38bdf8" },
    { col: "wind_speed_max", key: "wind_speed_max", title: "Tốc độ gió lớn nhất", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#ef4444" },
    { col: "wind_dir_deg_avg", key: "wind_direction", title: "Hướng gió", unit: "°", icon: "compass", cat: "wind_pressure", color: "#14b8a6" },
    { col: "wind_dir_var_avg", key: "wind_dir_var", title: "Độ biến thiên hướng gió", unit: "°", icon: "compass", cat: "wind_pressure", color: "#a78bfa" },
    { col: "solar_rad_avg", key: "solar_radiation", title: "Bức xạ mặt trời", unit: "W/m²", icon: "sun", cat: "solar", color: "#facc15" },
    { col: "uv_index_avg", key: "uv_index", title: "Chỉ số UV", unit: "UV", icon: "sun-medium", cat: "solar", color: "#fb923c" },
  ];

  const CATEGORY_LABELS = {
    ALL: "Tất cả thông số",
    thermal: "Nhiệt độ & Delta-T",
    moisture: "Độ ẩm & Lượng mưa",
    wind_pressure: "Gió & Áp suất",
    solar: "Bức xạ & UV",
    soil: "Nhiệt độ / pH / EC đất",
    nutrients: "Dinh dưỡng NPK đất",
    power: "Nguồn pin & Sóng 4G",
    other: "Thông số khác",
  };

  const DEPTH_METRIC_META = {
    temperature: { title: "Nhiệt độ đất (3 độ sâu)", unit: "°C", icon: "thermometer", cat: "soil" },
    moisture: { title: "Độ ẩm đất (3 độ sâu)", unit: "%", icon: "droplets", cat: "soil" },
    ph: { title: "Độ pH đất (3 độ sâu)", unit: "pH", icon: "flask-conical", cat: "soil" },
    ec: { title: "Độ dẫn điện EC (3 độ sâu)", unit: "µS/cm", icon: "zap", cat: "soil" },
    salinity: { title: "Độ mặn đất (3 độ sâu)", unit: "ppm", icon: "waves", cat: "soil" },
    nitrogen: { title: "Đạm N (3 độ sâu)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
    phosphorus: { title: "Lân P (3 độ sâu)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
    potassium: { title: "Kali K (3 độ sâu)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
  };

  const SINGLE_METRIC_META = Object.fromEntries([
    ...EXCHANGE_COLUMN_SPECS.map((s) => [s.key, { title: s.title, unit: s.unit, icon: s.icon, cat: s.cat, color: s.color }]),
    ["rainfall_last_24hrs", { title: "Lượng mưa 24 giờ qua", unit: "mm", icon: "cloud-rain-wind", cat: "moisture", color: "#0284c7" }],
    ["wind_gust", { title: "Gió giật", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#fb7185" }],
    ["apparent_temperature_avg", { title: "Nhiệt độ cảm nhận", unit: "°C", icon: "thermometer-sun", cat: "thermal", color: "#f59e0b" }],
    ["feels_like", { title: "Nhiệt độ cảm nhận", unit: "°C", icon: "thermometer-sun", cat: "thermal", color: "#f59e0b" }],
    ["pressure", { title: "Áp suất khí quyển", unit: "hPa", icon: "gauge", cat: "wind_pressure", color: "#60a5fa" }],
    ["vapour_pressure_deficit", { title: "Thâm hụt áp suất hơi (VPD)", unit: "kPa", icon: "cloud-fog", cat: "moisture", color: "#a78bfa" }],
    ["vapour_pressure", { title: "Áp suất hơi bão hòa", unit: "kPa", icon: "cloud-fog", cat: "moisture", color: "#38bdf8" }],
    ["battery_voltage", { title: "Điện áp pin", unit: "V", icon: "battery-charging", cat: "power", color: "#22c55e" }],
    ["solar_voltage", { title: "Điện áp pin mặt trời", unit: "V", icon: "sun", cat: "power", color: "#facc15" }],
    ["battery_pct", { title: "Mức pin", unit: "%", icon: "battery", cat: "power", color: "#22c55e" }],
    ["signal_strength_dbm", { title: "Cường độ tín hiệu (RSSI)", unit: "dBm", icon: "signal", cat: "power", color: "#38bdf8" }],
    ["signal_dbm", { title: "Cường độ tín hiệu (RSSI)", unit: "dBm", icon: "signal", cat: "power", color: "#38bdf8" }],
    ["csq", { title: "Chất lượng sóng 4G (CSQ)", unit: "csq", icon: "radio-tower", cat: "power", color: "#a78bfa" }],
    ["water_volume", { title: "Lưu lượng nước", unit: "L", icon: "droplets", cat: "moisture", color: "#38bdf8" }],
    ["cumulative_water", { title: "Tổng lượng nước tích lũy", unit: "L", icon: "waves", cat: "moisture", color: "#14b8a6" }],
    ["water_level", { title: "Mực nước", unit: "m", icon: "waves", cat: "moisture", color: "#38bdf8" }],
  ]);

  function recordDeviceSnapshotSeries(snap, exchangeRows = []) {
    if (!snap || !snap.device_id) return;
    const nowTag = new Date().toISOString().slice(11, 19);
    const baseTime = snap.latest_timestamp_utc ? String(snap.latest_timestamp_utc).slice(11, 19) || nowTag : nowTag;

    // Seed ALL 15 numeric Weather Exchange columns when buffer is not yet populated with historical rows
    const existingBuf = state.seriesHistory[snap.device_id];
    const needsExchangeSeed = snap.source_code === "weather" && Array.isArray(exchangeRows) && exchangeRows.length > 0 &&
      (!existingBuf || (existingBuf.atmos_pressure?.length || 0) <= 1);
    if (needsExchangeSeed) {
      const ordered = [...exchangeRows].reverse().slice(-32);
      ordered.forEach((row) => {
        const t = String(row.time || "").slice(11, 16) || nowTag;
        EXCHANGE_COLUMN_SPECS.forEach((sp) => {
          if (row[sp.col] != null) pushSeriesPoint(snap.device_id, sp.key, sp.title, sp.unit, t, row[sp.col]);
        });
      });
    }

    // Record ALL snapshot readings cleanly (AxisTech weather/soil/water/gateway metrics + power)
    const sampleTime = state.seriesHistory[snap.device_id] ? nowTag : baseTime;
    (snap.readings || []).forEach((r) => {
      if (r.value == null) return;
      const key = r.depth_level ? `${r.metric}_d${r.depth_level}` : r.metric;
      const lbl = window.ERPIcons.getMetricMeta(r.metric, r.depth_level).label;
      pushSeriesPoint(snap.device_id, key, lbl, r.unit || "", sampleTime, r.value);
    });
    if (snap.metadata?.battery_level != null) {
      pushSeriesPoint(snap.device_id, "battery_pct", "Battery Charge", "%", sampleTime, snap.metadata.battery_level);
    }
    if (snap.metadata?.signal_strength_dbm != null) {
      pushSeriesPoint(snap.device_id, "signal_dbm", "Signal Strength RSSI", "dBm", sampleTime, snap.metadata.signal_strength_dbm);
    }
  }

  function ingestHistoryReadings(readings = []) {
    (readings || []).forEach((r) => {
      if (!r || !r.device_id || r.value == null) return;
      const key = r.depth_level ? `${r.metric}_d${r.depth_level}` : r.metric;
      const lbl = r.depth_level
        ? `${r.metric} ${r.depth_level * 10}cm`
        : (SINGLE_METRIC_META[r.metric]?.title || r.metric);
      const rawTs = String(r.timestamp_utc || "");
      const timeLabel = rawTs.length >= 16 ? rawTs.slice(5, 16).replace("T", " ") : rawTs;
      pushSeriesPoint(r.device_id, key, lbl, r.unit || "", timeLabel, r.value);
    });
  }

  function openInspectorForDevice(deviceId) {
    const allDevs = state.dash?.devices || [];
    const allSnaps = state.dash?.snapshots || [];
    const device = allDevs.find((x) => x.id === deviceId || x.external_id === deviceId);
    if (!device) return;
    const snapshot = allSnaps.find((s) => s.device_id === device.id);
    window.ERPInspector.openDeviceDrawer(document, {
      device,
      snapshot,
      alerts: state.alertHistory,
      onLocate: (lat, lon) => {
        switchTab("fields");
        setTimeout(() => fullMap.focusCoordinate(lat, lon), 120);
      },
    });
  }

  const overviewMap = new window.SatelliteMapEngine("overviewMap", "overviewCoords", {
    onInspectDevice: openInspectorForDevice,
  });
  const fullMap = new window.SatelliteMapEngine("fullMap", "fullCoords", {
    onInspectDevice: openInspectorForDevice,
  });
  const apiModuleMap = new window.SatelliteMapEngine("apiModuleMap", "apiModuleCoords", {
    onInspectDevice: openInspectorForDevice,
  });

  function resolveCurrentModuleShare() {
    const isDevices = state.apiModuleMode !== "forecast";
    if (isDevices) {
      const hit = (state.moduleCatalog?.devices || []).find((x) => x.device_id === state.apiModuleDeviceId && (!state.projectId || x.project_id === state.projectId))
        || (state.moduleCatalog?.devices || []).find((x) => x.device_id === state.apiModuleDeviceId);
      if (hit) {
        const mQ = state.apiModuleMetric ? `?metric=${encodeURIComponent(state.apiModuleMetric)}&page=${state.apiModulePage}&page_size=${API_MODULE_PAGE_SIZE}` : `?page=${state.apiModulePage}&page_size=${API_MODULE_PAGE_SIZE}`;
        return { apiUrl: hit.api_url + mQ, pageUrl: hit.ui_url, embedUrl: hit.embed_url };
      }
      return { apiUrl: "/api/tbsgagtech/v1/modules/catalog", pageUrl: "/tbsgagtech/v1/modules", embedUrl: "/tbsgagtech/v1/modules?embed=1" };
    }
    const fHit = (state.moduleCatalog?.forecasts || []).find((x) => x.project_id === state.projectId) || (state.moduleCatalog?.forecasts || [])[0];
    if (fHit) {
      const fQ = `?metric=${encodeURIComponent(state.apiModuleForecastMetric || "temperature")}&page=${state.apiModulePage}&page_size=${API_MODULE_PAGE_SIZE}`;
      return { apiUrl: fHit.api_url + fQ, pageUrl: fHit.ui_url, embedUrl: fHit.embed_url };
    }
    return { apiUrl: "/api/tbsgagtech/v1/modules/catalog", pageUrl: "/tbsgagtech/v1/modules", embedUrl: "/tbsgagtech/v1/modules?embed=1" };
  }

  function syncBrowserUrl(tabName, opts = {}) {
    const isEmbed = new URLSearchParams(window.location.search).get("embed") === "1";
    document.body.classList.toggle("embed-mode", isEmbed);
    let path = TAB_ROUTES[tabName] || "/tbsgagtech/v1/overview";
    if (tabName === "api-module") {
      path = resolveCurrentModuleShare().pageUrl || "/tbsgagtech/v1/modules";
    }
    const nextUrl = path + (isEmbed ? "?embed=1" : "");
    if ((window.location.pathname + window.location.search) !== nextUrl) {
      if (opts.replace) window.history.replaceState({ tab: tabName }, "", nextUrl);
      else if (!opts.skipPush) window.history.pushState({ tab: tabName }, "", nextUrl);
    }
  }

  function applyRouteFromLocation() {
    const params = new URLSearchParams(window.location.search);
    document.body.classList.toggle("embed-mode", params.get("embed") === "1");
    const path = window.location.pathname || "/";
    if (path === "/" || path === "") return;

    const devMatch = path.match(/^\/tbsgagtech\/v1\/modules\/devices\/([^/]+)/);
    if (devMatch) {
      const tok = decodeURIComponent(devMatch[1]);
      const hit = (state.moduleCatalog?.devices || []).find((d) => d.token === tok);
      state.apiModuleMode = "devices";
      if (hit) {
        if (hit.project_id && hit.project_id !== state.projectId) {
          state.projectId = hit.project_id;
        }
        state.apiModuleDeviceId = hit.device_id;
      }
      switchTab("api-module", { skipPush: true });
      return;
    }

    const fcMatch = path.match(/^\/tbsgagtech\/v1\/modules\/forecast\/([^/]+)/);
    if (fcMatch) {
      const tok = decodeURIComponent(fcMatch[1]);
      const hit = (state.moduleCatalog?.forecasts || []).find((f) => f.token === tok);
      state.apiModuleMode = "forecast";
      if (hit && hit.project_id) state.projectId = hit.project_id;
      switchTab("api-module", { skipPush: true });
      return;
    }

    const matchedTab = Object.entries(TAB_ROUTES).find(([, route]) => path.startsWith(route))?.[0];
    if (matchedTab) switchTab(matchedTab, { skipPush: true });
  }

  function switchTab(tabName, opts = {}) {
    state.activeTab = tabName;
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
    if (window.U417Sidebar) window.U417Sidebar.setActive(tabName);
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
    syncBrowserUrl(tabName, opts);
    if (tabName === "overview") {
      overviewMap.invalidateSize();
      setTimeout(() => renderCascadingStep3(), 40);
    }
    if (tabName === "fields") fullMap.invalidateSize();
    if (tabName === "forecast" && state.forecast) {
      setTimeout(() => renderForecast(state.forecast), 40);
    }
    if (tabName === "telemetry") {
      setTimeout(() => renderTelemetryTrendChart(), 40);
    }
    if (tabName === "api-module") {
      apiModuleMap.invalidateSize();
      setTimeout(() => renderApiModuleDevice(), 40);
    }
  }

  function getActiveWorkspaceContext() {
    const actProj = (state.dash?.projects || []).find((p) => p.id === state.projectId);
    return {
      vendorName: actProj?.organisation?.name || "AxisTech Enterprise",
      projectName: actProj?.name || state.projectId || "Workspace",
      devices: state.dash?.devices || [],
      snapshots: state.dash?.snapshots || [],
      alerts: state.alertHistory || [],
    };
  }

  function renderCascadingWorkflow(d) {
    const projects = d.projects || [];
    const activeCtx = getActiveWorkspaceContext();
    const products = activeCtx.devices || [];

    if (!products.some((p) => p.id === state.selectedDeviceId)) {
      const preferred = products.find((p) => {
        const s = (activeCtx.snapshots || []).find((sn) => sn.device_id === p.id);
        return s && s.status === "LIVE";
      });
      state.selectedDeviceId = preferred?.id || products[0]?.id || "";
      state.selectedMetricFilter = "ALL";
    }

    const activeProd = products.find((p) => p.id === state.selectedDeviceId);
    $("cascadeBreadcrumb").innerHTML = `
      ${window.ERPIcons.iconHtml("git-branch", 15)}
      <span>ERP Flow:</span>
      <strong>1. ${activeCtx.projectName}</strong>
      <span>&rarr;</span>
      <strong>2. ${products.length} Device(s)</strong>
      <span>&rarr;</span>
      <strong>3. ${activeProd ? `${activeProd.name} (${activeProd.external_id})` : "Select a device"}</strong>
    `;

    // STEP 1: WORKSPACE CARDS
    $("vendorGrid").innerHTML = projects.map((proj) => {
      const isSelected = proj.id === state.projectId;
      return `<div class="vendor-card ${isSelected ? "active" : ""}" data-proj-card="${proj.id}">
        <div class="vendor-head">
          <div class="vendor-title">
            <div class="icon-avatar" style="width:38px;height:38px;">${window.ERPIcons.vendorIconHtml(proj.id, 19)}</div>
            <div>
              <div>${proj.name}</div>
              <div class="kpi-sub">${proj.organisation?.name || "AxisTech"} · Schema: ${proj.organisation?.schema_name || "tbncorp"}</div>
            </div>
          </div>
          ${badge(isSelected ? "ACTIVE" : (proj.role || "CONNECTED"))}
        </div>
        <div class="kpi-sub tabular-nums">${isSelected ? `${products.length} device(s) · ${d.live_devices} LIVE · ${d.total_fields} field(s)` : "Click workspace to inspect devices"}</div>
      </div>`;
    }).join("") || `<div class="kpi-sub">No AxisTech workspaces synced from Bridge yet.</div>`;

    $("vendorGrid").querySelectorAll(".vendor-card[data-proj-card]").forEach((card) => {
      card.addEventListener("click", async () => {
        const pId = card.dataset.projCard;
        if (pId && pId !== state.projectId) {
          state.projectId = pId;
          state.selectedDeviceId = "";
          state.selectedMetricFilter = "ALL";
          await refreshAll();
        }
      });
    });

    // STEP 2: DEVICE LIST FOR SELECTED WORKSPACE
    const snapMap = Object.fromEntries((activeCtx.snapshots || []).map((s) => [s.device_id, s]));
    $("productCountBadge").textContent = `${products.length} device(s)`;
    $("productList").innerHTML = products.map((dev) => {
      const snap = snapMap[dev.id] || { status: "UNKNOWN", readings: [] };
      const isSelected = dev.id === state.selectedDeviceId;
      const topMetrics = (snap.readings || []).slice(0, 3)
        .map((r) => `<span class="badge badge-info tabular-nums">${r.metric}${r.depth_level ? ` D${r.depth_level}` : ""}: ${r.value ?? "-"} ${r.unit || ""}</span>`)
        .join("");

      return `<div class="product-card ${isSelected ? "active" : ""}" data-product-id="${dev.id}">
        <div class="sensor-card-head">
          <div class="sensor-title-wrap">
            <div class="icon-avatar" style="width:40px;height:40px;">${window.ERPIcons.deviceIconHtml(dev.source_code, 20)}</div>
            <div>
              <strong>${dev.name}</strong>
              <div class="mono" style="color:var(--muted)">${dev.external_id} · ${dev.source_code}</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            ${powerBadge(dev, snap)}
            ${badge(snap.status)}
          </div>
        </div>
        <div style="display:flex;gap:5px;flex-wrap:wrap;">${topMetrics || '<span class="kpi-sub">Click to view diagnostics &amp; real-time graph</span>'}</div>
      </div>`;
    }).join("") || `<div class="kpi-sub">No products found in ${activeCtx.projectName}. Click a populated project pill in Step 1.</div>`;

    $("productList").querySelectorAll(".product-card").forEach((card) => {
      card.addEventListener("click", () => {
        state.selectedDeviceId = card.dataset.productId;
        state.selectedMetricFilter = "ALL";
        rerenderAllViews();
      });
    });

    // STEP 3: SELECTED PRODUCT LIVE DATA & REAL-TIME GRAPH
    renderCascadingStep3();
  }

  function buildComponentChartSpecs(dev, devBuf = {}) {
    const specs = [];
    const consumed = new Set();
    const depthColors = { 1: "#38bdf8", 2: "#22c55e", 3: "#f59e0b" };

    // 1. Group 3-depth soil channels by base agronomic parameter (Temp, Moisture, pH, EC, Salinity, N, P, K)
    Object.keys(devBuf).forEach((k) => {
      const m = k.match(/^(.+)_d([123])$/);
      if (!m) return;
      const base = m[1];
      if (consumed.has(`depth:${base}`)) return;
      consumed.add(`depth:${base}`);
      const meta = DEPTH_METRIC_META[base] || { title: `${base} (By Depth)`, unit: devBuf[k]?.[0]?.unit || "", icon: "layers", cat: "soil" };
      const series = [1, 2, 3]
        .filter((d) => devBuf[`${base}_d${d}`]?.length)
        .map((d) => {
          consumed.add(`${base}_d${d}`);
          return {
            label: `${d * 10} cm`,
            unit: meta.unit || devBuf[`${base}_d${d}`][0]?.unit || "",
            color: depthColors[d],
            points: devBuf[`${base}_d${d}`],
          };
        });
      if (series.length) specs.push({ id: `depth_${base}`, ...meta, series });
    });

    // 2. Group compatible same-unit speed bounds (Wind Speed Avg / Min / Max / Gust)
    const windKeys = ["wind_speed", "wind_speed_min", "wind_speed_max", "wind_gust"].filter((k) => devBuf[k]?.length);
    if (windKeys.length > 1) {
      const wColors = { wind_speed: "#f59e0b", wind_speed_min: "#38bdf8", wind_speed_max: "#ef4444", wind_gust: "#fb7185" };
      specs.push({
        id: "wind_speed_bundle",
        title: "Tốc độ gió (TB / Nhỏ nhất / Lớn nhất / Gió giật)",
        unit: "km/h",
        icon: "wind",
        cat: "wind_pressure",
        series: windKeys.map((k) => {
          consumed.add(k);
          return {
            label: SINGLE_METRIC_META[k]?.title || window.ERPIcons.getMetricMeta(k).label,
            unit: "km/h",
            color: wColors[k],
            points: devBuf[k],
          };
        }),
      });
    }

    // 3. Group compatible same-unit DC voltage channels (Battery V & Solar Panel V)
    const voltKeys = ["battery_voltage", "solar_voltage"].filter((k) => devBuf[k]?.length);
    if (voltKeys.length > 1) {
      specs.push({
        id: "voltage_bundle",
        title: "Điện áp pin & Tấm sạc mặt trời",
        unit: "V",
        icon: "battery-charging",
        cat: "power",
        series: voltKeys.map((k) => {
          consumed.add(k);
          return {
            label: SINGLE_METRIC_META[k]?.title || window.ERPIcons.getMetricMeta(k).label,
            unit: "V",
            color: SINGLE_METRIC_META[k]?.color || "#22c55e",
            points: devBuf[k],
          };
        }),
      });
    }

    // 4. Every remaining component gets its own independent single-scale chart card
    const remainingKeys = Object.keys(devBuf).filter((k) => !consumed.has(k) && devBuf[k]?.length);
    remainingKeys.forEach((k) => {
      const mm = window.ERPIcons.getMetricMeta(k);
      const meta = SINGLE_METRIC_META[k] || {
        title: mm.label || devBuf[k][0]?.label || k,
        unit: devBuf[k][0]?.unit || "",
        icon: "activity",
        cat: "other",
        color: "#38bdf8",
      };
      specs.push({
        id: `cmp_${k}`,
        title: meta.title,
        unit: meta.unit || devBuf[k][0]?.unit || "",
        icon: meta.icon,
        cat: meta.cat,
        series: [{ label: meta.title, unit: meta.unit || devBuf[k][0]?.unit || "", color: meta.color || "#38bdf8", points: devBuf[k] }],
      });
    });

    return specs;
  }

  function renderCascadingStep3() {
    const activeCtx = getActiveWorkspaceContext();
    const products = activeCtx.devices || [];
    const dev = products.find((p) => p.id === state.selectedDeviceId);
    const snap = (activeCtx.snapshots || []).find((s) => s.device_id === dev?.id);

    if (!dev) {
      $("detailTitle").textContent = "Select a product in Step 2 to inspect live data & real-time graphs";
      $("detailMetaHeader").innerHTML = `<div class="kpi-sub">Waiting for product selection...</div>`;
      $("detailKpiMetrics").innerHTML = "";
      $("productMetricPills").innerHTML = "";
      $("componentChartsGrid").innerHTML = "";
      $("detailSoilProfile").style.display = "none";
      $("detailAlertsBox").innerHTML = "";
      window.ERPCharts.renderRealtimeSeries($("productRealtimeCanvas"), $("productRealtimeTooltip"), { series: [] });
      return;
    }

    $("detailTitle").textContent = `${dev.name} (${dev.external_id}) — All Split Component Graphs & Live Telemetry`;
    $("detailInspectBtn").onclick = () => openInspectorForDevice(dev.id);

    const status = snap?.status || "UNKNOWN";
    const meta = snap?.metadata || {};
    const readings = snap?.readings || [];
    const rssiHtml = meta.signal_strength_dbm != null
      ? `${window.ERPInspector.rssiBarsHtml(meta.signal_strength_dbm)} ${meta.signal_strength_dbm} dBm`
      : "-";

    $("detailMetaHeader").innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <div class="icon-avatar" style="width:48px;height:48px;">${window.ERPIcons.deviceIconHtml(dev.source_code, 24)}</div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <strong style="font-size:1.05rem;">${dev.name}</strong>
              ${powerBadge(dev, snap)}
              ${badge(status)}
              <span class="badge badge-info">${dev.source_code}</span>
              <span class="badge badge-ok tabular-nums">${readings.length} channels</span>
            </div>
            <div class="mono" style="color:var(--muted)">
              Vendor: ${activeCtx.vendorName} · ID: ${dev.external_id} · Battery: ${meta.battery_level != null ? meta.battery_level + "%" : "-"} · Signal: ${rssiHtml} · UTC: ${snap?.latest_timestamp_utc || "NO_DATA"}
            </div>
          </div>
        </div>
      </div>
    `;

    // Render ALL live metrics (zero truncation)
    $("detailKpiMetrics").innerHTML = readings.map((r) => {
      const mm = window.ERPIcons.getMetricMeta(r.metric, r.depth_level);
      return `
      <div class="metric-box" title="${mm.tooltip}">
        <div class="metric-name">${mm.label}</div>
        <div class="metric-val tabular-nums">${r.value ?? "-"} <small>${r.unit || ""}</small></div>
      </div>
    `;
    }).join("") || `<div class="kpi-sub">Chưa có thông số đo hoạt động (NO_DATA / Epoch sentinel).</div>`;

    // Build ALL component chart specs and category filter pills
    const devBuf = state.seriesHistory[dev.id] || {};
    const allSpecs = buildComponentChartSpecs(dev, devBuf);
    const categoriesPresent = [...new Set(allSpecs.map((s) => s.cat))];
    const pills = [{ key: "ALL", label: `Tất cả (${allSpecs.length})`, tooltip: "Hiển thị toàn bộ thông số" }]
      .concat(categoriesPresent.map((cat) => ({
        key: `CAT:${cat}`,
        label: `${CATEGORY_LABELS[cat] || cat} (${allSpecs.filter((s) => s.cat === cat).length})`,
        tooltip: CATEGORY_LABELS[cat] || cat,
      })))
      .concat(allSpecs.map((s) => {
        const rawMetricKey = s.id.startsWith("cmp_") ? s.id.slice(4) : s.id;
        const mm = window.ERPIcons.getMetricMeta(rawMetricKey);
        return { key: `SPEC:${s.id}`, label: s.title, tooltip: mm.tooltip || s.title };
      }));

    $("productMetricPills").innerHTML = pills.map((p) => `
      <button type="button" class="metric-pill ${state.selectedMetricFilter === p.key ? "active" : ""}" data-metric-key="${p.key}" title="${p.tooltip}">${p.label}</button>
    `).join("");

    $("productMetricPills").querySelectorAll(".metric-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedMetricFilter = btn.dataset.metricKey;
        renderCascadingStep3();
      });
    });

    let visibleSpecs = allSpecs;
    if (state.selectedMetricFilter.startsWith("CAT:")) {
      const cat = state.selectedMetricFilter.slice(4);
      visibleSpecs = allSpecs.filter((s) => s.cat === cat);
    } else if (state.selectedMetricFilter.startsWith("SPEC:")) {
      const id = state.selectedMetricFilter.slice(5);
      visibleSpecs = allSpecs.filter((s) => s.id === id);
    }

    window.ERPCharts.renderComponentChartsGrid($("componentChartsGrid"), visibleSpecs);

    // Pinned single-scale primary component graph (matches first visible component so Y-axis stays accurate)
    const primarySpec = visibleSpecs[0] || allSpecs[0];
    window.ERPCharts.renderRealtimeSeries($("productRealtimeCanvas"), $("productRealtimeTooltip"), {
      series: primarySpec ? primarySpec.series : [],
      emptyText: `Awaiting telemetry readings for ${dev.name} (${dev.external_id})...`,
    });

    if (dev.source_code === "soilprobe") {
      $("detailSoilProfile").style.display = "block";
      $("detailSoilProfile").innerHTML = `
        <h4 style="font-size:0.86rem;margin-bottom:8px;">3-Depth Rootzone Soil Profile (10 / 20 / 30 cm)</h4>
        ${window.ERPCharts.renderSoilDepthHtml(readings)}
      `;
    } else {
      $("detailSoilProfile").style.display = "none";
      $("detailSoilProfile").innerHTML = "";
    }

    const devAlerts = (activeCtx.alerts || []).filter((a) =>
      a.device_name === dev.name || String(a.device_name || "").includes(dev.external_id)
    ).slice(0, 5);
    $("detailAlertsBox").innerHTML = devAlerts.map((a) => `
      <div class="stack-item">
        <div><strong>${a.policy_name || "Alert"}</strong> · <span class="kpi-sub">${a.rule_description}</span></div>
        <span class="tabular-nums kpi-sub">${a.triggered_at_utc || ""}</span>
      </div>
    `).join("");
  }

  function renderTelemetryTrendChart() {
    const devs = state.dash?.devices || [];
    const primaryDev = devs.find((d) => d.source_code === "weather") || devs[0];
    const devBuf = (primaryDev && state.seriesHistory[primaryDev.id]) || {};
    const specs = [];
    devs.forEach((dev) => {
      const buf = state.seriesHistory[dev.id];
      if (!buf) return;
      buildComponentChartSpecs(dev, buf).forEach((sp) => {
        specs.push({ ...sp, title: `${dev.name}: ${sp.title}` });
      });
    });

    const firstKey = Object.keys(devBuf)[0];
    window.ERPCharts.renderRealtimeSeries($("trendCanvas"), $("trendTooltip"), {
      series: firstKey ? [{ label: devBuf[firstKey][0]?.label || firstKey, unit: devBuf[firstKey][0]?.unit || "", points: devBuf[firstKey] }] : [],
      emptyText: "Waiting for real-time station telemetry series...",
    });
    window.ERPCharts.renderComponentChartsGrid($("telemetryComponentCharts"), specs);
  }

  function renderOverview(d) {
    $("syncMeta").textContent = `Syncs: ${d.sync_status.sync_count || 0} | Bridge: ${d.sync_status.bridge_health}`;
    if (window.U417Sidebar) window.U417Sidebar.setIncidentCount(Number(d.open_incidents || 0));
    const banner = $("errorBanner");
    if (d.sync_status && d.sync_status.last_error) {
      banner.textContent = `Sync Diagnostic: ${d.sync_status.last_error}`;
      banner.style.display = "block";
    } else if (!(d.projects || []).length) {
      banner.textContent = "No projects loaded from Bridge yet. Click Sync Now or verify Bridge service.";
      banner.style.display = "block";
    } else {
      banner.style.display = "none";
    }

    const sec = state.security || d.security || {};
    const encLabel = sec.encryption_at_rest ? sec.encryption_algorithm : "Standby";
    const snapMap = Object.fromEntries((d.snapshots || []).map((s) => [s.device_id, s]));
    const onCount = (d.devices || []).filter((dev) => getDevicePowerState(dev, snapMap[dev.id]).isOn).length;
    const offCount = Math.max(0, (d.devices || []).length - onCount);
    const kpis = [
      ["AxisTech IoT Fleet", d.total_devices, `${onCount} ON · ${offCount} OFF (${d.live_devices} LIVE)`, "cpu"],
      ["Open Incidents", d.open_incidents, `${d.acknowledged_incidents} Acknowledged · ${d.active_policies} Policies`, "bell-ring"],
      ["Fields & Assets", d.total_fields, `${d.total_assets} Assets · ${d.providers?.length || 0} Providers`, "satellite"],
      ["ISO 27001 Security", sec.audit_chain_verified !== false ? "VERIFIED" : "ALERT", `Crypto: ${encLabel}`, "shield-check"],
    ];
    $("kpiGrid").innerHTML = kpis.map(([lbl, val, sub, icon]) => `
      <div class="kpi-card">
        <div>
          <div class="kpi-label">${lbl}</div>
          <div class="kpi-value tabular-nums">${val}</div>
          <div class="kpi-sub">${sub}</div>
        </div>
        <div class="kpi-icon"><i data-lucide="${icon}"></i></div>
      </div>
    `).join("");

    renderCascadingWorkflow(d);

    const w = d.latest_weather || {};
    const keys = Object.keys(w);
    $("weatherOverview").innerHTML = keys.length
      ? keys.map((k) => {
          const mm = window.ERPIcons.getMetricMeta(k);
          return `<div class="metric-box" title="${mm.tooltip}"><div class="metric-name">${mm.label}</div><div class="metric-val tabular-nums">${Number(w[k]).toFixed(2)}</div></div>`;
        }).join("")
      : `<div class="kpi-sub">Chưa có dữ liệu thời tiết trực tiếp trong dự án này.</div>`;

    $("isoGrid").innerHTML = Object.entries(d.iso_compliance || {}).map(([k, v]) => `
      <div class="iso-row"><strong>${k}</strong><span class="badge badge-ok">${v}</span></div>
    `).join("");

    $("overviewDevicesBody").innerHTML = (d.devices || []).map((dev) => {
      const s = snapMap[dev.id] || {};
      const batt = s.metadata?.battery_level != null ? `${s.metadata.battery_level}%` : "-";
      const sig = s.metadata?.signal_strength_dbm != null
        ? `${window.ERPInspector.rssiBarsHtml(s.metadata.signal_strength_dbm)} ${s.metadata.signal_strength_dbm} dBm`
        : "-";
      const ts = s.latest_timestamp_utc || "NO_DATA";
      return `<tr class="clickable-row" data-device-id="${dev.id}">
        <td><div style="display:flex;align-items:center;gap:9px;"><span class="icon-avatar" style="width:32px;height:32px;">${window.ERPIcons.deviceIconHtml(dev.source_code, 16)}</span><strong>${dev.name}</strong></div></td>
        <td><code>${dev.external_id}</code></td><td>${dev.source_code}</td><td>${dev.comm_type || "-"}</td>
        <td>${powerBadge(dev, s)}</td><td>${badge(s.status || "UNKNOWN")}</td>
        <td class="tabular-nums">${batt} / ${sig}</td><td class="tabular-nums">${ts}</td>
      </tr>`;
    }).join("") || '<tr><td colspan="8">No devices in selected project</td></tr>';

    $("overviewDevicesBody").querySelectorAll("tr[data-device-id]").forEach((tr) => {
      tr.addEventListener("click", () => openInspectorForDevice(tr.dataset.deviceId));
    });
  }

  function renderTelemetry(d) {
    const devMap = Object.fromEntries((d.devices || []).map((dev) => [dev.id, dev]));
    $("telemetryCards").innerHTML = (d.snapshots || []).map((s) => {
      const dev = devMap[s.device_id] || { name: s.external_id, source_code: s.source_code };
      const soilHtml = s.source_code === "soilprobe" ? window.ERPCharts.renderSoilDepthHtml(s.readings) : "";
      const metricsHtml = soilHtml || `<div class="metric-grid">
        ${(s.readings || []).map((r) => {
          const mm = window.ERPIcons.getMetricMeta(r.metric, r.depth_level);
          return `
          <div class="metric-box" title="${mm.tooltip}">
            <div class="metric-name">${mm.label}</div>
            <div class="metric-val tabular-nums">${r.value ?? "-"} <small>${r.unit || ""}</small></div>
          </div>
        `;
        }).join("") || '<div class="kpi-sub">Chưa có dữ liệu đo (Epoch 1970 / NO_DATA guarded)</div>'}
      </div>`;

      return `<div class="sensor-card" data-device-id="${s.device_id}">
        <div class="sensor-card-head">
          <div class="sensor-title-wrap">
            <div class="icon-avatar">${window.ERPIcons.deviceIconHtml(s.source_code, 22)}</div>
            <div><strong>${dev.name}</strong><div class="mono" style="color:var(--muted)">${s.external_id} · ${s.source_code}</div></div>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            ${powerBadge(dev, s)}
            ${badge(s.status)}
          </div>
        </div>
        ${metricsHtml}
      </div>`;
    }).join("") || '<div class="kpi-sub">No sensor telemetry snapshots in this project.</div>';

    $("telemetryCards").querySelectorAll(".sensor-card[data-device-id]").forEach((card) => {
      card.addEventListener("click", () => openInspectorForDevice(card.dataset.deviceId));
    });
    renderTelemetryTrendChart();
  }

  function renderForecast(bundle) {
    const met = bundle?.met_norway || { status: "DISCONNECTED", days: [], steps: [] };
    const janes = bundle?.janes_weather || { status: "DISCONNECTED", spray_windows: [], spray_hours: [] };
    const f = (v, suffix = "") => (v == null ? "-" : `${Number(v).toFixed(1)}${suffix}`);

    $("metStatusBadge").className = `badge ${met.status === "CONNECTED" ? "badge-ok" : "badge-warn"}`;
    $("metStatusBadge").textContent = met.status;
    $("metLocationMeta").textContent = met.location
      ? `${met.location.name || "Project Location"} · TZ: ${met.location.time_zone || "UTC"} · Updated: ${met.updated_at_utc || "-"}`
      : "No MET Norway forecast location metadata";

    const steps = met.steps || [];
    const cur = steps[met.current_step_index || 0] || steps[0];
    $("metCurrentGrid").innerHTML = cur
      ? [
          ["Nhiệt độ không khí", "Nhiệt độ môi trường không khí", f(cur.temperature, " °C")],
          ["Nhiệt độ cảm nhận", "Nhiệt độ cảm nhận thực tế", f(cur.feels_like, " °C")],
          ["Độ ẩm tương đối", "Độ ẩm không khí tương đối", f(cur.humidity, " %")],
          ["Áp suất khí quyển", "Áp suất khí quyển tại trạm", f(cur.pressure, " hPa")],
          ["Tốc độ gió TB", "Tốc độ gió trung bình", f(cur.wind_speed, " km/h")],
          ["Lượng mưa (1h / 6h)", "Lượng mưa dự báo trong 1 giờ và 6 giờ", `${f(cur.precipitation_1h)} / ${f(cur.precipitation_6h, " mm")}`],
          ["Chỉ số UV", "Chỉ số tia cực tím (UV)", f(cur.uv_index)],
          ["Độ che phủ mây", "Tỷ lệ mây che phủ bầu trời", f(cur.cloud_cover, " %")],
        ].map(([n, tip, v]) => `<div class="metric-box" title="${tip}"><div class="metric-name">${n}</div><div class="metric-val tabular-nums">${v}</div></div>`).join("")
      : `<div class="kpi-sub">Chưa có dữ liệu bước dự báo hiện tại</div>`;

    $("forecastDaysGrid").innerHTML = (met.days || []).map((d) => `
      <div class="forecast-day-card">
        <div class="forecast-day-date">${d.date}</div>
        ${window.ERPIcons.weatherSymbolHtml(d.symbol, 28)}
        <div class="forecast-day-temps tabular-nums">${f(d.temperature_max, "°")} / ${f(d.temperature_min, "°")}</div>
        <div class="kpi-sub tabular-nums">Rain: ${f(d.precipitation, " mm")}</div>
        ${window.ERPIcons.weatherSymbolBadgeHtml(d.symbol)}
      </div>
    `).join("") || `<div class="kpi-sub">No forecast days available</div>`;

    $("forecastStepsBody").innerHTML = steps.slice(0, 24).map((s) => `
      <tr class="tabular-nums">
        <td>${s.time_utc}</td><td>${f(s.temperature)}</td><td>${f(s.feels_like)}</td><td>${f(s.humidity)}</td>
        <td>${f(s.pressure)}</td><td>${f(s.wind_speed)}</td><td>${f(s.precipitation_1h)}</td>
        <td>${f(s.cloud_cover)}</td><td>${f(s.uv_index)}</td><td>${window.ERPIcons.weatherSymbolBadgeHtml(s.symbol)}</td>
      </tr>
    `).join("") || '<tr><td colspan="10">No hourly forecast steps</td></tr>';

    window.ERPCharts.renderForecastChart($("forecastCanvas"), $("forecastTooltip"), steps);

    const fcSteps = steps.slice(0, 24);
    const curSymbolHtml = cur ? window.ERPIcons.weatherSymbolBadgeHtml(cur.symbol) : "";
    if ($("forecastSymbolStrip")) {
      $("forecastSymbolStrip").innerHTML = fcSteps.slice(0, 10).map((s) => {
        const hhmm = s.time_local
          ? `${String(s.time_local).slice(11, 16)}`
          : `${String(s.time_utc || "").slice(11, 16) || "-"} UTC`;
        const symMeta = window.ERPIcons.getWeatherSymbolMeta(s.symbol);
        return `<div class="forecast-hour-chip" style="border-top:2px solid ${symMeta.color};">
          <div class="forecast-hour-time">${hhmm}</div>
          ${window.ERPIcons.weatherSymbolHtml(s.symbol, 20)}
          <div class="forecast-hour-temp tabular-nums">${f(s.temperature, "°C")}</div>
          <div class="kpi-sub tabular-nums" style="margin-top:0;font-size:0.69rem;">RH ${f(s.humidity, "%")} · ${f(s.precipitation_1h ?? 0, " mm")}</div>
        </div>`;
      }).join("");
    }

    const uvNow = Number(cur?.uv_index ?? 0);
    const uvBadge = uvNow >= 8
      ? `<span class="badge badge-danger">Very High UV</span>`
      : uvNow >= 6
        ? `<span class="badge badge-warn">High UV</span>`
        : `<span class="badge badge-ok">Low / Moderate UV</span>`;

    const fcPts = (fn) => fcSteps.filter((s) => fn(s) != null).map((s) => ({ t: String(s.time_local || s.time_utc || "").slice(11, 16), v: Number(fn(s)) }));
    const tempSeries = [
      { label: "Nhiệt độ không khí", unit: "°C", color: "#38bdf8", points: fcPts((s) => s.temperature) },
      { label: "Nhiệt độ cảm nhận", unit: "°C", color: "#f59e0b", points: fcPts((s) => s.feels_like) },
    ];
    const dewPts = fcPts((s) => s.dew_point);
    if (dewPts.length) tempSeries.push({ label: "Điểm sương", unit: "°C", color: "#22c55e", points: dewPts });

    window.ERPCharts.renderComponentChartsGrid($("forecastComponentCharts"), [
      {
        id: "fc_temp",
        title: "Nhiệt độ không khí, Cảm nhận & Điểm sương",
        subtitle: "Nhiệt độ môi trường không khí, cảm nhận thực tế & điểm sương (2m)",
        unit: "°C",
        icon: "thermometer-sun",
        accentColor: "#f59e0b",
        badgeHtml: curSymbolHtml,
        series: tempSeries,
      },
      {
        id: "fc_rain",
        title: "Lượng mưa (1 giờ)",
        subtitle: "Lượng mưa dự báo trong 1 giờ phục vụ kế hoạch phun",
        unit: "mm",
        icon: "cloud-rain",
        accentColor: "#0ea5e9",
        chartType: "bar",
        badgeHtml: curSymbolHtml,
        series: [{ label: "Lượng mưa (1 giờ)", unit: "mm", color: "#0ea5e9", points: fcPts((s) => s.precipitation_1h ?? s.precipitation_6h ?? 0) }],
      },
      {
        id: "fc_rh",
        title: "Độ ẩm tương đối",
        subtitle: "Độ ẩm không khí tương đối & nguy cơ đọng sương",
        unit: "%",
        icon: "droplet",
        accentColor: "#14b8a6",
        series: [{ label: "Độ ẩm tương đối", unit: "%", color: "#14b8a6", points: fcPts((s) => s.humidity) }],
      },
      {
        id: "fc_wind",
        title: "Tốc độ gió TB",
        subtitle: "Tốc độ gió trung bình đánh giá độ bay tạt",
        unit: "km/h",
        icon: "wind",
        accentColor: "#a78bfa",
        series: [{ label: "Tốc độ gió TB", unit: "km/h", color: "#a78bfa", points: fcPts((s) => s.wind_speed) }],
      },
      {
        id: "fc_pressure",
        title: "Áp suất khí quyển",
        subtitle: "Áp suất khí quyển tại trạm",
        unit: "hPa",
        icon: "gauge",
        accentColor: "#60a5fa",
        series: [{ label: "Áp suất khí quyển", unit: "hPa", color: "#60a5fa", points: fcPts((s) => s.pressure) }],
      },
      {
        id: "fc_cloud",
        title: "Độ che phủ mây",
        subtitle: "Tỷ lệ mây che phủ bầu trời trong 24 giờ",
        unit: "%",
        icon: "cloud",
        accentColor: "#94a3b8",
        badgeHtml: curSymbolHtml,
        series: [{ label: "Độ che phủ mây", unit: "%", color: "#94a3b8", points: fcPts((s) => s.cloud_cover) }],
      },
      {
        id: "fc_uv",
        title: "Chỉ số UV",
        subtitle: "Chỉ số tia cực tím (UV) theo dõi cường độ nắng",
        unit: "UV",
        icon: "sun",
        accentColor: "#facc15",
        badgeHtml: uvBadge,
        series: [{ label: "Chỉ số UV", unit: "UV", color: "#facc15", points: fcPts((s) => s.uv_index) }],
      },
    ]);

    $("janesStatusBadge").className = `badge ${janes.status === "CONNECTED" ? "badge-ok" : "badge-warn"}`;
    $("janesStatusBadge").textContent = janes.status;
    $("janesBody").innerHTML = janes.status === "CONNECTED"
      ? (janes.spray_windows || []).map((w) => `<div class="stack-item"><span>${w.start_utc} &rarr; ${w.end_utc}</span>${badge(w.quality || "IDEAL")}</div>`).join("") || '<div class="kpi-sub">Connected — no spray windows returned.</div>'
      : `<div class="stack-item"><span>Jane's Weather provider is not connected on this project in AxisStream HQ.</span><span class="badge badge-warn">DISCONNECTED</span></div>`;
  }

  function renderFieldsAndAssets(fields, assets, providers) {
    $("fieldsList").innerHTML = fields.map((f) => `
      <div class="stack-item">
        <div><strong>${f.name}</strong><div class="kpi-sub">${f.address || f.category}</div></div>
        <span class="badge badge-info">${(f.sites || []).length} site(s)</span>
      </div>
    `).join("") || '<div class="kpi-sub">No fields registered</div>';

    $("assetsBody").innerHTML = assets.map((a) => `
      <tr>
        <td><div style="display:flex;align-items:center;gap:8px;"><span class="icon-avatar" style="width:32px;height:32px;">${window.ERPIcons.assetIconHtml(a.asset_type, 16)}</span><strong>${a.name}</strong></div></td>
        <td>${a.asset_type}</td><td>${a.make || "-"} ${a.model || ""}</td>
        <td class="tabular-nums">${a.capacity_litres ? `${a.capacity_litres} L` : (a.number_plate || "-")}</td>
        <td class="mono">${a.position ? `${a.position.latitude.toFixed(5)}, ${a.position.longitude.toFixed(5)}` : "-"}</td>
      </tr>
    `).join("") || '<tr><td colspan="5">No assets in project</td></tr>';

    $("providersList").innerHTML = providers.map((p) => `
      <div class="stack-item"><strong>${p.name}</strong>${badge(p.status)}</div>
    `).join("") || '<div class="kpi-sub">No connected external providers</div>';
  }

  function resolveForecastLocation(forecast, devices = [], fields = []) {
    const ml = forecast?.met_norway?.location;
    if (ml && Number.isFinite(Number(ml.latitude)) && Number.isFinite(Number(ml.longitude))) {
      return {
        name: ml.name || "AxisStream Forecast Site",
        latitude: Number(ml.latitude),
        longitude: Number(ml.longitude),
        elevation: ml.elevation ?? null,
        time_zone: ml.time_zone || "UTC",
        source: "MET Norway Location (AxisStream HQ)",
      };
    }
    const ws = (devices || []).find((d) => d.source_code === "weather" && d.coordinates) || (devices || []).find((d) => d.coordinates);
    if (ws && ws.coordinates) {
      return {
        name: `${ws.name} (Fallback)`,
        latitude: Number(ws.coordinates.latitude),
        longitude: Number(ws.coordinates.longitude),
        elevation: null,
        time_zone: "UTC",
        source: "Active Device Coordinates",
      };
    }
    for (const f of fields || []) {
      for (const s of f.sites || []) {
        const ring = s.geojson?.coordinates?.[0];
        if (Array.isArray(ring) && ring.length) {
          const avgLon = ring.reduce((acc, pt) => acc + Number(pt[0]), 0) / ring.length;
          const avgLat = ring.reduce((acc, pt) => acc + Number(pt[1]), 0) / ring.length;
          if (Number.isFinite(avgLat) && Number.isFinite(avgLon)) {
            return {
              name: f.name || s.name || "Field Centroid",
              latitude: avgLat,
              longitude: avgLon,
              elevation: null,
              time_zone: "UTC",
              source: "Field GeoJSON Centroid",
            };
          }
        }
      }
    }
    return null;
  }

  const API_FORECAST_METRICS = [
    { key: "temperature", title: "Nhiệt độ không khí", tooltip: "Nhiệt độ môi trường không khí", unit: "°C", color: "#38bdf8", chartType: "line", pick: (s) => s.temperature },
    { key: "feels_like", title: "Nhiệt độ cảm nhận", tooltip: "Nhiệt độ cảm nhận thực tế", unit: "°C", color: "#f59e0b", chartType: "line", pick: (s) => s.feels_like },
    { key: "dew_point", title: "Điểm sương", tooltip: "Nhiệt độ điểm sương", unit: "°C", color: "#22c55e", chartType: "line", pick: (s) => s.dew_point },
    { key: "precipitation_1h", title: "Lượng mưa (1 giờ)", tooltip: "Lượng mưa trong 1 giờ", unit: "mm", color: "#0ea5e9", chartType: "bar", pick: (s) => s.precipitation_1h ?? s.precipitation_6h },
    { key: "humidity", title: "Độ ẩm tương đối", tooltip: "Độ ẩm không khí tương đối", unit: "%", color: "#14b8a6", chartType: "line", pick: (s) => s.humidity },
    { key: "wind_speed", title: "Tốc độ gió TB", tooltip: "Tốc độ gió trung bình", unit: "km/h", color: "#a78bfa", chartType: "line", pick: (s) => s.wind_speed },
    { key: "pressure", title: "Áp suất khí quyển", tooltip: "Áp suất khí quyển tại trạm", unit: "hPa", color: "#60a5fa", chartType: "line", pick: (s) => s.pressure },
    { key: "cloud_cover", title: "Độ che phủ mây", tooltip: "Tỷ lệ mây che phủ bầu trời", unit: "%", color: "#94a3b8", chartType: "line", pick: (s) => s.cloud_cover },
    { key: "uv_index", title: "Chỉ số UV", tooltip: "Chỉ số tia cực tím (UV)", unit: "UV", color: "#facc15", chartType: "line", pick: (s) => s.uv_index },
  ];

  function renderApiModuleDevice() {
    if (!$("tab-api-module")) return;
    const isDevices = state.apiModuleMode !== "forecast";
    document.querySelectorAll(".mode-tab-btn[data-api-mode]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.apiMode === (isDevices ? "devices" : "forecast"));
    });
    if ($("apiModuleDeviceControls")) $("apiModuleDeviceControls").style.display = isDevices ? "flex" : "none";
    if ($("apiModuleForecastControls")) $("apiModuleForecastControls").style.display = isDevices ? "none" : "flex";

    const devices = state.dash?.devices || [];
    const snapshots = state.dash?.snapshots || [];
    const snapMap = Object.fromEntries(snapshots.map((s) => [s.device_id, s]));

    if (isDevices) {
      if (!devices.some((d) => d.id === state.apiModuleDeviceId)) {
        const liveDev = devices.find((d) => getDevicePowerState(d, snapMap[d.id]).isOn);
        state.apiModuleDeviceId = liveDev?.id || devices[0]?.id || "";
      }
      const selEl = $("apiModuleDeviceSelect");
      if (selEl) {
        selEl.innerHTML = devices.map((d) => {
          const pw = getDevicePowerState(d, snapMap[d.id]);
          return `<option value="${d.id}">${d.name} (${d.external_id}) · ${pw.label}</option>`;
        }).join("") || '<option value="">No devices synced</option>';
        selEl.value = state.apiModuleDeviceId;
      }

      const dev = devices.find((d) => d.id === state.apiModuleDeviceId);
      const snap = snapMap[dev?.id] || { status: "NO_DATA", readings: [] };
      const devBuf = (dev && state.seriesHistory[dev.id]) || {};
      const metricKeys = Object.keys(devBuf).filter((k) => devBuf[k]?.length);
      if (!metricKeys.includes(state.apiModuleMetric)) {
        state.apiModuleMetric = metricKeys[0] || snap.readings?.[0]?.metric || "";
      }

      if ($("apiModuleMetricPills")) {
        $("apiModuleMetricPills").innerHTML = metricKeys.map((k) => {
          const mm = window.ERPIcons.getMetricMeta(k);
          const lbl = SINGLE_METRIC_META[k]?.title || mm.label;
          return `<button type="button" class="metric-pill ${state.apiModuleMetric === k ? "active" : ""}" data-dev-metric="${k}" title="${mm.tooltip}">${lbl}</button>`;
        }).join("") || `<span class="kpi-sub">Chưa có chuỗi dữ liệu cảm biến cho thiết bị này</span>`;

        $("apiModuleMetricPills").querySelectorAll("[data-dev-metric]").forEach((btn) => {
          btn.addEventListener("click", () => {
            state.apiModuleMetric = btn.dataset.devMetric;
            state.apiModulePage = 1;
            renderApiModuleDevice();
          });
        });
      }

      if ($("apiModuleMapTitle")) $("apiModuleMapTitle").textContent = dev ? `Định vị thiết bị: ${dev.name} (${dev.external_id})` : "Định vị thiết bị";
      if ($("apiModuleLocationBadge")) {
        $("apiModuleLocationBadge").innerHTML = dev ? powerBadge(dev, snap) : `<span class="badge badge-muted">KHÔNG CÓ THIẾT BỊ</span>`;
      }
      if ($("apiModuleGeoSummary")) {
        $("apiModuleGeoSummary").textContent = dev?.coordinates
          ? `GPS: ${Number(dev.coordinates.latitude).toFixed(5)}, ${Number(dev.coordinates.longitude).toFixed(5)} · ${dev.comm_type || "IoT"}`
          : "Thiết bị chưa có GPS cố định — hiển thị GeoJSON vùng";
      }

      apiModuleMap.render({ fields: state.fields, devices, snapshots, assets: state.assets }, state.projectId, {
        selectedDeviceId: dev?.id || "",
      });

      const points = (state.apiModuleMetric && devBuf[state.apiModuleMetric]) ? devBuf[state.apiModuleMetric] : [];
      const meta = SINGLE_METRIC_META[state.apiModuleMetric] || {};
      const curMeta = window.ERPIcons.getMetricMeta(state.apiModuleMetric);
      const metricLabel = meta.title || curMeta.label || state.apiModuleMetric || "Thông số đo";
      const metricUnit = points[0]?.unit || meta.unit || "";
      const metricColor = meta.color || "#38bdf8";

      const vals = points.map((p) => Number(p.v)).filter((n) => isFinite(n));
      const minV = vals.length ? Math.min(...vals).toFixed(2) : "-";
      const maxV = vals.length ? Math.max(...vals).toFixed(2) : "-";
      const avgV = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
      const latestV = vals.length ? vals[vals.length - 1].toFixed(2) : "-";

      if ($("apiModuleMetricTitle")) $("apiModuleMetricTitle").innerHTML = `<i data-lucide="table"></i><span title="${curMeta.tooltip}">1 Bảng dữ liệu + 1 Đồ thị — ${dev?.name || "Thiết bị"} · ${metricLabel}</span>`;
      if ($("apiModuleMetricStats")) {
        $("apiModuleMetricStats").innerHTML = `<span class="stat-pill">Mới nhất <strong>${latestV} ${metricUnit}</strong></span><span class="stat-pill">Min <strong>${minV}</strong></span><span class="stat-pill">TB <strong>${avgV}</strong></span><span class="stat-pill">Max <strong>${maxV}</strong></span>`;
      }
      if ($("apiModuleChartHeader")) {
        $("apiModuleChartHeader").textContent = `${metricLabel}${metricUnit ? ` (${metricUnit})` : ""}`;
        $("apiModuleChartHeader").title = curMeta.tooltip;
      }
      if ($("apiModuleChartBadge")) $("apiModuleChartBadge").textContent = `${latestV} ${metricUnit}`.trim();

      const reversedPts = [...points].reverse();
      const safePage = renderTablePagination(
        $("apiModulePagination"),
        reversedPts.length,
        state.apiModulePage,
        API_MODULE_PAGE_SIZE,
        (nextPage) => {
          state.apiModulePage = nextPage;
          renderApiModuleDevice();
        }
      );
      state.apiModulePage = safePage;
      const pageRows = reversedPts.slice((safePage - 1) * API_MODULE_PAGE_SIZE, safePage * API_MODULE_PAGE_SIZE);

      $("apiModuleTableHead").innerHTML = `<tr><th>Thời gian</th><th>Thiết bị</th><th>Thông số</th><th>Giá trị</th><th>Đơn vị</th><th>Nguồn</th></tr>`;
      $("apiModuleTableBody").innerHTML = pageRows.map((pt) => `
        <tr>
          <td>${pt.t}</td>
          <td>${dev?.name || "-"}</td>
          <td title="${curMeta.tooltip}">${metricLabel}</td>
          <td><strong>${Number(pt.v).toFixed(2)}</strong></td>
          <td>${metricUnit || "-"}</td>
          <td>${dev ? powerBadge(dev, snap) : "-"}</td>
        </tr>
      `).join("") || `<tr><td colspan="6">Chưa có bản ghi cho thông số thiết bị đã chọn</td></tr>`;

      window.ERPCharts.renderRealtimeSeries($("apiModuleChartCanvas"), $("apiModuleChartTooltip"), {
        height: 290,
        series: points.length ? [{ label: metricLabel, unit: metricUnit, color: metricColor, points }] : [],
        emptyText: "Đang chờ dữ liệu cảm biến cho thiết bị này...",
      });
    } else {
      const met = state.forecast?.met_norway || { status: "DISCONNECTED", steps: [] };
      const steps = met.steps || [];
      const curStep = steps[met.current_step_index || 0] || steps[0] || null;
      const loc = resolveForecastLocation(state.forecast, devices, state.fields);

      if ($("apiModuleForecastMetricPills")) {
        $("apiModuleForecastMetricPills").innerHTML = API_FORECAST_METRICS.map((fm) => `
          <button type="button" class="metric-pill ${state.apiModuleForecastMetric === fm.key ? "active" : ""}" data-fc-metric="${fm.key}" title="${fm.tooltip}">${fm.title}</button>
        `).join("");
        $("apiModuleForecastMetricPills").querySelectorAll("[data-fc-metric]").forEach((btn) => {
          btn.addEventListener("click", () => {
            state.apiModuleForecastMetric = btn.dataset.fcMetric;
            state.apiModulePage = 1;
            renderApiModuleDevice();
          });
        });
      }

      if ($("apiModuleMapTitle")) $("apiModuleMapTitle").textContent = loc ? `Định vị điểm dự báo: ${loc.name}` : "Định vị điểm dự báo";
      if ($("apiModuleLocationBadge")) {
        $("apiModuleLocationBadge").innerHTML = curStep ? window.ERPIcons.weatherSymbolBadgeHtml(curStep.symbol) : badge(met.status || "DISCONNECTED");
      }
      if ($("apiModuleGeoSummary")) {
        $("apiModuleGeoSummary").textContent = loc
          ? `GPS: ${loc.latitude.toFixed(5)}, ${loc.longitude.toFixed(5)}${loc.elevation != null ? ` · Độ cao: ${loc.elevation}m` : ""} · ${loc.time_zone} (${loc.source})`
          : "Chưa nhận được tọa độ WGS84 dự báo";
      }

      apiModuleMap.renderForecastLocation(loc, curStep, state.fields);

      const fm = API_FORECAST_METRICS.find((x) => x.key === state.apiModuleForecastMetric) || API_FORECAST_METRICS[0];
      const fcPoints = steps
        .filter((s) => fm.pick(s) != null)
        .map((s) => ({
          t: s.time_local ? String(s.time_local).replace("T", " ").slice(5, 16) : String(s.time_utc || "").slice(5, 16),
          v: Number(fm.pick(s)),
          step: s,
        }));

      const vals = fcPoints.map((p) => p.v).filter((n) => isFinite(n));
      const minV = vals.length ? Math.min(...vals).toFixed(1) : "-";
      const maxV = vals.length ? Math.max(...vals).toFixed(1) : "-";
      const avgV = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : "-";
      const curV = curStep && fm.pick(curStep) != null ? Number(fm.pick(curStep)).toFixed(1) : (vals[0] != null ? vals[0].toFixed(1) : "-");

      if ($("apiModuleMetricTitle")) $("apiModuleMetricTitle").innerHTML = `<i data-lucide="cloud-sun-rain"></i><span title="${fm.tooltip}">1 Bảng dữ liệu + 1 Đồ thị — Dự báo · ${fm.title}</span>`;
      if ($("apiModuleMetricStats")) {
        $("apiModuleMetricStats").innerHTML = `<span class="stat-pill">Hiện tại <strong>${curV} ${fm.unit}</strong></span><span class="stat-pill">Min <strong>${minV}</strong></span><span class="stat-pill">TB <strong>${avgV}</strong></span><span class="stat-pill">Max <strong>${maxV}</strong></span>`;
      }
      if ($("apiModuleChartHeader")) {
        $("apiModuleChartHeader").textContent = `${fm.title} (${fm.unit})`;
        $("apiModuleChartHeader").title = fm.tooltip;
      }
      if ($("apiModuleChartBadge")) $("apiModuleChartBadge").textContent = `${curV} ${fm.unit}`;

      const safePage = renderTablePagination(
        $("apiModulePagination"),
        fcPoints.length,
        state.apiModulePage,
        API_MODULE_PAGE_SIZE,
        (nextPage) => {
          state.apiModulePage = nextPage;
          renderApiModuleDevice();
        }
      );
      state.apiModulePage = safePage;
      const pageRows = fcPoints.slice((safePage - 1) * API_MODULE_PAGE_SIZE, safePage * API_MODULE_PAGE_SIZE);

      $("apiModuleTableHead").innerHTML = `<tr><th>Thời gian</th><th title="Trạng thái thời tiết tổng hợp">Thời tiết</th><th title="${fm.tooltip}">${fm.title}</th><th>Đơn vị</th><th title="Lượng mưa trong 1 giờ">Lượng mưa (1 giờ)</th><th title="Tốc độ gió trung bình">Tốc độ gió TB</th></tr>`;
      $("apiModuleTableBody").innerHTML = pageRows.map((pt) => {
        const st = pt.step;
        const rainStr = st.precipitation_1h != null ? `${Number(st.precipitation_1h).toFixed(1)} mm` : "-";
        const windStr = st.wind_speed != null ? `${Number(st.wind_speed).toFixed(1)} km/h` : "-";
        return `<tr>
          <td>${pt.t}</td>
          <td>${window.ERPIcons.weatherSymbolBadgeHtml(st.symbol)}</td>
          <td><strong>${pt.v.toFixed(1)}</strong></td>
          <td>${fm.unit}</td>
          <td>${rainStr}</td>
          <td>${windStr}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="6">Không có bản ghi dự báo cho thông số này</td></tr>`;

      const chartPts = fcPoints.slice(0, 36).map((p) => ({ t: p.t.slice(-5), v: p.v }));
      window.ERPCharts.renderRealtimeSeries($("apiModuleChartCanvas"), $("apiModuleChartTooltip"), {
        height: 290,
        chartType: fm.chartType || "line",
        series: chartPts.length ? [{ label: fm.title, unit: fm.unit, color: fm.color, points: chartPts }] : [],
        emptyText: "Chưa có dữ liệu chuỗi dự báo...",
      });
    }

    const share = resolveCurrentModuleShare();
    if ($("apiModuleApiUrlPreview")) $("apiModuleApiUrlPreview").textContent = share.apiUrl;
    if ($("apiModulePageUrlPreview")) $("apiModulePageUrlPreview").textContent = share.pageUrl;
    if (state.activeTab === "api-module") syncBrowserUrl("api-module", { replace: true });
    window.ERPIcons.refresh();
  }

  function renderAlertsOnly(incidents, policies, history) {
    $("incidentsBody").innerHTML = incidents.map((inc) => `
      <tr>
        <td>${inc.policy_name}</td><td>${inc.device_name || inc.device_id}</td>
        <td>${badge(inc.severity)}</td><td>${badge(inc.status)}</td><td>${inc.message}</td>
        <td>
          ${inc.status === "OPEN" ? `<button class="btn btn-ghost btn-sm" data-act="acknowledge" data-id="${inc.id}">Acknowledge</button>` : ""}
          ${inc.status !== "RESOLVED" ? `<button class="btn btn-primary btn-sm" data-act="resolve" data-id="${inc.id}">Resolve</button>` : "Closed"}
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6">No open or historical incidents</td></tr>';

    $("policiesBody").innerHTML = policies.map((p) => `
      <tr><td>${p.name}</td><td>${p.device_name}</td><td>${badge(p.priority)}</td><td>${badge(p.status)}</td><td class="tabular-nums">${p.frequency_window_minutes}m</td></tr>
    `).join("") || '<tr><td colspan="5">No alert policies</td></tr>';

    const safeAlertPage = renderTablePagination(
      $("alertHistoryPagination"),
      (history || []).length,
      state.alertHistoryPage,
      PAGE_SIZE,
      (nextPage) => {
        state.alertHistoryPage = nextPage;
        renderAlertsOnly(incidents, policies, history);
      }
    );
    state.alertHistoryPage = safeAlertPage;
    const alertSlice = (history || []).slice((safeAlertPage - 1) * PAGE_SIZE, safeAlertPage * PAGE_SIZE);
    $("alertHistoryBody").innerHTML = alertSlice.map((h) => `
      <tr>
        <td class="tabular-nums">${h.triggered_at_utc || "-"}</td><td>${h.policy_name}</td><td>${h.device_name || "-"}</td>
        <td>${h.rule_description}</td><td>${badge(h.delivery_status)}</td><td class="tabular-nums">${h.notification_count}</td>
      </tr>
    `).join("") || '<tr><td colspan="6">No alert history</td></tr>';
  }

  function renderAudit(entries, sec = {}) {
    const badgeEl = $("securityOverallBadge");
    if (badgeEl) {
      const ok = sec.audit_chain_verified !== false;
      badgeEl.className = `badge ${ok ? "badge-ok" : "badge-danger"}`;
      badgeEl.textContent = ok ? "CHAIN VERIFIED" : "TAMPER ALERT";
    }
    if ($("securityPostureGrid")) {
      const items = [
        ["Encryption At Rest", sec.encryption_at_rest ? sec.encryption_algorithm : "Standby (Set ERP_ENCRYPTION_KEY)"],
        ["Audit Hash Chain", sec.audit_chain_verified !== false ? `Verified (${sec.audit_entries ?? entries.length} entries)` : "Integrity Mismatch"],
        ["Rate Limit Policy", `${sec.rate_limit_rpm || 300} req/min per IP`],
        ["Write API Key Guard", sec.api_key_guard_enabled ? "Enforced (Constant-Time)" : "Optional (Set ERP_REQUIRE_API_KEY)"],
        ["Content Security Policy", sec.csp_policy || "script-src 'self'"],
        ["Upstream Sync Mode", sec.read_only_cloud_sync !== false ? "Read-Only Cloud Sync" : "Custom"],
      ];
      $("securityPostureGrid").innerHTML = items.map(([k, v]) => `
        <div class="metric-box"><div class="metric-name">${k}</div><div class="metric-val" style="font-size:0.9rem;">${v}</div></div>
      `).join("");
    }
    const safeAuditPage = renderTablePagination(
      $("auditPagination"),
      (entries || []).length,
      state.auditPage,
      PAGE_SIZE,
      (nextPage) => {
        state.auditPage = nextPage;
        renderAudit(entries, sec);
      }
    );
    state.auditPage = safeAuditPage;
    const auditSlice = (entries || []).slice((safeAuditPage - 1) * PAGE_SIZE, safeAuditPage * PAGE_SIZE);
    $("auditBody").innerHTML = auditSlice.map((e) => `
      <tr>
        <td class="tabular-nums">${e.timestamp_utc}</td><td>${e.actor}</td><td><strong>${e.action}</strong></td>
        <td>${e.resource_type}:${e.resource_id}</td><td><code>${(e.correlation_id || "").slice(0, 12)}</code></td>
        <td><code title="${e.entry_hash || ""}">${e.entry_hash ? e.entry_hash.slice(0, 12) + "…" : "-"}</code></td>
        <td>${e.details}</td>
      </tr>
    `).join("") || '<tr><td colspan="7">No audit events recorded yet</td></tr>';
  }

  function rerenderAllViews() {
    if (!state.dash) return;
    renderOverview(state.dash);
    renderTelemetry(state.dash);
    renderForecast(state.forecast);
    renderFieldsAndAssets(state.fields, state.assets, state.dash.providers || []);
    renderAlertsOnly(state.incidents, state.policies, state.alertHistory);
    renderAudit(state.audit, state.security || state.dash.security || {});
    renderApiModuleDevice();

    const mapPayload = {
      fields: state.fields,
      devices: state.dash.devices || [],
      snapshots: state.dash.snapshots || [],
      assets: state.assets,
    };
    overviewMap.render(mapPayload, state.projectId);
    fullMap.render(mapPayload, state.projectId);
    window.ERPIcons.refresh();
  }

  async function refreshAll() {
    const q = state.projectId ? `?project_id=${encodeURIComponent(state.projectId)}` : "";
    const dash = await api(`/api/erp/v1/dashboard${q}`);
    state.dash = dash;
    if (!state.projectId && dash.active_project_id) state.projectId = dash.active_project_id;

    const sel = $("projectSelect");
    if (sel.options.length !== (dash.projects || []).length) {
      sel.innerHTML = (dash.projects || []).map((p) => `<option value="${p.id}">${formatWorkspaceLabel(p)}</option>`).join("");
    }
    sel.value = state.projectId;

    const pq = `?project_id=${encodeURIComponent(state.projectId)}`;
    const [fields, assets, policies, alertHistory, incidents, forecast, audit, hist, sec, modCatalog] = await Promise.all([
      api(`/api/erp/v1/fields${pq}`),
      api(`/api/erp/v1/assets${pq}`),
      api(`/api/erp/v1/alerts/policies${pq}`),
      api(`/api/erp/v1/alerts/history${pq}`),
      api(`/api/erp/v1/incidents${pq}`),
      api(`/api/erp/v1/forecast${pq}`),
      api(`/api/erp/v1/audit?limit=200`),
      api(`/api/erp/v1/telemetry/history${pq}&hours=24`).catch(() => ({ data: [] })),
      api(`/api/erp/v1/security/status`).catch(() => dash.security || null),
      api(`/api/tbsgagtech/v1/modules/catalog`).catch(() => ({ devices: [], forecasts: [] })),
    ]);

    state.fields = fields.data || [];
    state.assets = assets.data || [];
    state.policies = policies.data || [];
    state.alertHistory = alertHistory.data || [];
    state.incidents = incidents.data || [];
    state.forecast = forecast;
    state.audit = audit.data || [];
    state.security = sec;
    state.moduleCatalog = modCatalog || { devices: [], forecasts: [] };

    if (!state.routeApplied) {
      state.routeApplied = true;
      const prevProj = state.projectId;
      applyRouteFromLocation();
      if (state.projectId && state.projectId !== prevProj) {
        return refreshAll();
      }
    }

    ingestHistoryReadings(hist.data || []);
    (dash.snapshots || []).forEach((s) => recordDeviceSnapshotSeries(s, []));

    rerenderAllViews();
  }

  function buildSearchCatalog() {
    const items = [];
    (state.dash?.devices || []).forEach((d) => items.push({ kind: "DEVICE", label: d.name, sub: `${d.external_id} · ${d.source_code}`, id: d.id }));
    state.fields.forEach((f) => items.push({ kind: "FIELD", label: f.name, sub: f.address || f.category, tab: "fields" }));
    state.assets.forEach((a) => items.push({ kind: "ASSET", label: a.name, sub: a.asset_type, tab: "assets" }));
    state.policies.forEach((p) => items.push({ kind: "POLICY", label: p.name, sub: `${p.priority} · ${p.status}`, tab: "incidents" }));
    return items;
  }

  function openSearch() {
    const modal = $("searchModal");
    const inp = $("quickSearchInput");
    modal.classList.add("open");
    inp.value = "";
    const catalog = buildSearchCatalog();
    const onSelect = (hit) => {
      modal.classList.remove("open");
      if (hit.kind === "DEVICE") openInspectorForDevice(hit.id);
      else if (hit.tab) switchTab(hit.tab);
    };
    window.ERPInspector.renderQuickSearch("", catalog, onSelect);
    inp.oninput = () => window.ERPInspector.renderQuickSearch(inp.value, catalog, onSelect);
    setTimeout(() => inp.focus(), 30);
  }

  // Event Listeners
  document.querySelectorAll(".nav-item").forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));
  $("projectSelect").addEventListener("change", (e) => {
    state.projectId = e.target.value;
    state.selectedDeviceId = "";
    state.selectedMetricFilter = "ALL";
    state.apiModuleDeviceId = "";
    state.apiModulePage = 1;
    refreshAll();
  });

  document.querySelectorAll(".mode-tab-btn[data-api-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.apiModuleMode = btn.dataset.apiMode;
      state.apiModulePage = 1;
      renderApiModuleDevice();
    });
  });

  if ($("apiModuleDeviceSelect")) {
    $("apiModuleDeviceSelect").addEventListener("change", (e) => {
      state.apiModuleDeviceId = e.target.value;
      state.apiModuleMetric = "";
      state.apiModulePage = 1;
      renderApiModuleDevice();
    });
  }

  $("syncBtn").addEventListener("click", async () => {
    try { await api("/api/erp/v1/sync/now", { method: "POST" }); }
    catch (err) { $("errorBanner").textContent = `Manual sync error: ${err.message}`; $("errorBanner").style.display = "block"; }
    await refreshAll();
  });

  $("themeBtn").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    localStorage.setItem("axs_theme", state.theme);
    document.documentElement.dataset.theme = state.theme;
  });

  document.querySelectorAll(".map-btn-group").forEach((grp) => {
    const t = grp.dataset.mapTarget;
    const engine = t === "overview" ? overviewMap : t === "apimodule" ? apiModuleMap : fullMap;
    grp.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.dataset.fit) { engine.fitBounds(); return; }
      if (btn.dataset.layer) {
        grp.querySelectorAll("button[data-layer]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        engine.setBaseLayer(btn.dataset.layer);
      }
    });
  });

  $("chkFields").addEventListener("change", (e) => fullMap.setLayerVisibility("fields", e.target.checked));
  $("chkDevices").addEventListener("change", (e) => fullMap.setLayerVisibility("devices", e.target.checked));
  $("chkAssets").addEventListener("change", (e) => fullMap.setLayerVisibility("assets", e.target.checked));

  $("closeDrawerBtn").addEventListener("click", () => $("deviceDrawer").classList.remove("open"));
  $("deviceDrawer").addEventListener("click", (e) => { if (e.target.id === "deviceDrawer") $("deviceDrawer").classList.remove("open"); });

  $("quickSearchBtn").addEventListener("click", openSearch);
  $("closeSearchBtn").addEventListener("click", () => $("searchModal").classList.remove("open"));
  $("searchModal").addEventListener("click", (e) => { if (e.target.id === "searchModal") $("searchModal").classList.remove("open"); });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); }
    if (e.key === "Escape") {
      $("searchModal").classList.remove("open");
      $("deviceDrawer").classList.remove("open");
    }
  });

  document.body.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    await api(`/api/erp/v1/incidents/${btn.dataset.id}/${btn.dataset.act}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: "erp-operator", notes: `Action ${btn.dataset.act} via ISO Dashboard` }),
    });
    await refreshAll();
  });

  const es = new EventSource("/api/erp/v1/events");
  es.addEventListener("connected", () => {
    $("sseStatus").innerHTML = `<i data-lucide="radio"></i><span>SSE LIVE STREAM</span>`;
    $("sseStatus").className = "status-pill live";
    window.ERPIcons.refresh();
  });
  es.addEventListener("sync_update", () => refreshAll());
  es.addEventListener("incident_update", () => refreshAll());
  es.onerror = () => {
    $("sseStatus").innerHTML = `<i data-lucide="radio"></i><span>SSE RECONNECTING</span>`;
    $("sseStatus").className = "status-pill connecting";
    window.ERPIcons.refresh();
  };

  const copyUrlToClipboard = (btnEl, relativeUrl) => {
    const full = `${window.location.origin}${relativeUrl}`;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(full).catch(() => {});
    }
    if (btnEl) {
      const span = btnEl.querySelector("span");
      const orig = span ? span.textContent : "";
      if (span) span.textContent = "Copied!";
      setTimeout(() => { if (span) span.textContent = orig; }, 1400);
    }
  };
  if ($("copyApiUrlBtn")) $("copyApiUrlBtn").addEventListener("click", () => copyUrlToClipboard($("copyApiUrlBtn"), resolveCurrentModuleShare().apiUrl));
  if ($("copyPageUrlBtn")) $("copyPageUrlBtn").addEventListener("click", () => copyUrlToClipboard($("copyPageUrlBtn"), resolveCurrentModuleShare().pageUrl));
  if ($("copyEmbedUrlBtn")) $("copyEmbedUrlBtn").addEventListener("click", () => copyUrlToClipboard($("copyEmbedUrlBtn"), resolveCurrentModuleShare().embedUrl));
  window.addEventListener("popstate", () => applyRouteFromLocation());

  let resizeTimer = null;
  const handleViewportReflow = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      overviewMap.invalidateSize();
      fullMap.invalidateSize();
      apiModuleMap.invalidateSize();
      if (!state.dash) return;
      if (state.activeTab === "overview") renderCascadingStep3();
      else if (state.activeTab === "telemetry") renderTelemetryTrendChart();
      else if (state.activeTab === "forecast" && state.forecast) renderForecast(state.forecast);
      else if (state.activeTab === "api-module") renderApiModuleDevice();
    }, 180);
  };
  window.addEventListener("resize", handleViewportReflow);
  window.addEventListener("orientationchange", handleViewportReflow);

  window.ERPIcons.refresh();
  refreshAll().catch(console.error);
})();
