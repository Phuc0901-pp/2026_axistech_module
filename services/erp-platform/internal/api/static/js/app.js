/* AxisTech ISO ERP Main Application Controller (Pure Lucide + Enterprise 3-Step Flow + Security Posture) */
(() => {
  const MAX_SERIES_POINTS = 48;

  const state = {
    projectId: "",
    selectedDeviceId: "",
    selectedMetricFilter: "ALL",
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
    { col: "temperature_avg", key: "temperature", title: "Air Temperature", unit: "°C", icon: "thermometer-sun", cat: "thermal", color: "#38bdf8" },
    { col: "dewpoint_avg", key: "dew_point", title: "Dew Point", unit: "°C", icon: "thermometer", cat: "thermal", color: "#a78bfa" },
    { col: "deltat_avg", key: "delta_t", title: "Delta-T (Evaporation)", unit: "°C", icon: "droplets", cat: "thermal", color: "#fb7185" },
    { col: "humidity_avg", key: "humidity", title: "Relative Humidity", unit: "%", icon: "droplet", cat: "moisture", color: "#22c55e" },
    { col: "rainfall", key: "rainfall", title: "Rainfall", unit: "mm", icon: "cloud-rain", cat: "moisture", color: "#38bdf8" },
    { col: "rainfall_total", key: "rainfall_total", title: "Cumulative Rainfall", unit: "mm", icon: "cloud-rain-wind", cat: "moisture", color: "#14b8a6" },
    { col: "atmos_pressure_avg", key: "atmos_pressure", title: "Atmospheric Pressure", unit: "hPa", icon: "gauge", cat: "wind_pressure", color: "#60a5fa" },
    { col: "msl_pressure", key: "msl_pressure", title: "Mean Sea-Level Pressure", unit: "hPa", icon: "gauge", cat: "wind_pressure", color: "#818cf8" },
    { col: "wind_speed_avg", key: "wind_speed", title: "Wind Speed Avg", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#f59e0b" },
    { col: "wind_speed_min", key: "wind_speed_min", title: "Wind Speed Min", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#38bdf8" },
    { col: "wind_speed_max", key: "wind_speed_max", title: "Wind Speed Max", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#ef4444" },
    { col: "wind_dir_deg_avg", key: "wind_direction", title: "Wind Direction", unit: "°", icon: "compass", cat: "wind_pressure", color: "#14b8a6" },
    { col: "wind_dir_var_avg", key: "wind_dir_var", title: "Wind Direction Variance", unit: "°", icon: "compass", cat: "wind_pressure", color: "#a78bfa" },
    { col: "solar_rad_avg", key: "solar_radiation", title: "Solar Radiation", unit: "W/m²", icon: "sun", cat: "solar", color: "#facc15" },
    { col: "uv_index_avg", key: "uv_index", title: "UV Index", unit: "UV", icon: "sun-medium", cat: "solar", color: "#fb923c" },
  ];

  const CATEGORY_LABELS = {
    ALL: "All Components",
    thermal: "Thermal & Delta-T",
    moisture: "Moisture & Rain",
    wind_pressure: "Wind & Pressure",
    solar: "Solar & UV",
    soil: "Soil Temp / pH / EC",
    nutrients: "Soil NPK Nutrients",
    power: "Power & 4G Signal",
    other: "Other Telemetry",
  };

  const DEPTH_METRIC_META = {
    temperature: { title: "Soil Temperature (3 Depths)", unit: "°C", icon: "thermometer", cat: "soil" },
    moisture: { title: "Soil Moisture (3 Depths)", unit: "%", icon: "droplets", cat: "soil" },
    ph: { title: "Soil pH (3 Depths)", unit: "pH", icon: "flask-conical", cat: "soil" },
    ec: { title: "Electrical Conductivity (3 Depths)", unit: "µS/cm", icon: "zap", cat: "soil" },
    salinity: { title: "Soil Salinity (3 Depths)", unit: "ppm", icon: "waves", cat: "soil" },
    nitrogen: { title: "Nitrogen N (3 Depths)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
    phosphorus: { title: "Phosphorus P (3 Depths)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
    potassium: { title: "Potassium K (3 Depths)", unit: "mg/kg", icon: "sprout", cat: "nutrients" },
  };

  const SINGLE_METRIC_META = Object.fromEntries([
    ...EXCHANGE_COLUMN_SPECS.map((s) => [s.key, { title: s.title, unit: s.unit, icon: s.icon, cat: s.cat, color: s.color }]),
    ["wind_gust", { title: "Wind Gust", unit: "km/h", icon: "wind", cat: "wind_pressure", color: "#fb7185" }],
    ["apparent_temperature_avg", { title: "Apparent Temperature", unit: "°C", icon: "thermometer-sun", cat: "thermal", color: "#f59e0b" }],
    ["vapour_pressure_deficit", { title: "Vapour Pressure Deficit", unit: "kPa", icon: "cloud-fog", cat: "moisture", color: "#a78bfa" }],
    ["vapour_pressure", { title: "Vapour Pressure", unit: "kPa", icon: "cloud-fog", cat: "moisture", color: "#38bdf8" }],
    ["battery_voltage", { title: "Battery Voltage", unit: "V", icon: "battery-charging", cat: "power", color: "#22c55e" }],
    ["solar_voltage", { title: "Solar Panel Voltage", unit: "V", icon: "sun", cat: "power", color: "#facc15" }],
    ["battery_pct", { title: "Battery Charge", unit: "%", icon: "battery", cat: "power", color: "#22c55e" }],
    ["signal_dbm", { title: "Signal Strength RSSI", unit: "dBm", icon: "signal", cat: "power", color: "#38bdf8" }],
    ["csq", { title: "4G CSQ Quality", unit: "csq", icon: "radio-tower", cat: "power", color: "#a78bfa" }],
    ["water_volume", { title: "Water Flow Volume", unit: "L", icon: "droplets", cat: "moisture", color: "#38bdf8" }],
    ["cumulative_water", { title: "Cumulative Water", unit: "L", icon: "waves", cat: "moisture", color: "#14b8a6" }],
    ["water_level", { title: "Water Tank Level", unit: "m", icon: "waves", cat: "moisture", color: "#38bdf8" }],
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
      const lbl = r.depth_level
        ? `${r.metric} ${r.depth_level * 10}cm`
        : (SINGLE_METRIC_META[r.metric]?.title || r.metric);
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

  function switchTab(tabName) {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
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
    if (tabName === "exchange") {
      setTimeout(() => renderExchangeRealtimeChart(), 40);
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
          ${badge(snap.status)}
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
        title: "Wind Speed (Avg / Min / Max / Gust)",
        unit: "km/h",
        icon: "wind",
        cat: "wind_pressure",
        series: windKeys.map((k) => {
          consumed.add(k);
          return {
            label: SINGLE_METRIC_META[k]?.title || k,
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
        title: "Battery & Solar Voltage",
        unit: "V",
        icon: "battery-charging",
        cat: "power",
        series: voltKeys.map((k) => {
          consumed.add(k);
          return {
            label: SINGLE_METRIC_META[k]?.title || k,
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
      const meta = SINGLE_METRIC_META[k] || {
        title: devBuf[k][0]?.label || k,
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
    $("detailKpiMetrics").innerHTML = readings.map((r) => `
      <div class="metric-box">
        <div class="metric-name">${r.metric}${r.depth_level ? ` · ${r.depth_level * 10}cm` : ""}</div>
        <div class="metric-val tabular-nums">${r.value ?? "-"} <small>${r.unit || ""}</small></div>
      </div>
    `).join("") || `<div class="kpi-sub">No active numeric metrics yet (NO_DATA / Epoch sentinel guarded).</div>`;

    // Build ALL component chart specs and category filter pills
    const devBuf = state.seriesHistory[dev.id] || {};
    const allSpecs = buildComponentChartSpecs(dev, devBuf);
    const categoriesPresent = [...new Set(allSpecs.map((s) => s.cat))];
    const pills = [{ key: "ALL", label: `All Components (${allSpecs.length})` }]
      .concat(categoriesPresent.map((cat) => ({
        key: `CAT:${cat}`,
        label: `${CATEGORY_LABELS[cat] || cat} (${allSpecs.filter((s) => s.cat === cat).length})`,
      })))
      .concat(allSpecs.map((s) => ({ key: `SPEC:${s.id}`, label: s.title })));

    $("productMetricPills").innerHTML = pills.map((p) => `
      <button type="button" class="metric-pill ${state.selectedMetricFilter === p.key ? "active" : ""}" data-metric-key="${p.key}">${p.label}</button>
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
    const kpis = [
      ["AxisTech IoT Fleet", d.total_devices, `${d.live_devices} LIVE · ${d.no_data_devices} NO_DATA`, "cpu"],
      ["Open Incidents", d.open_incidents, `${d.acknowledged_incidents} Acknowledged · ${d.active_policies} Policies`, "bell-ring"],
      ["Weather Exchange", d.exchange_rows, `${d.total_fields} Fields · ${d.total_assets} Assets`, "database"],
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
      ? keys.map((k) => `<div class="metric-box"><div class="metric-name">${k}</div><div class="metric-val tabular-nums">${Number(w[k]).toFixed(2)}</div></div>`).join("")
      : `<div class="kpi-sub">No live weather readings in this project.</div>`;

    $("isoGrid").innerHTML = Object.entries(d.iso_compliance || {}).map(([k, v]) => `
      <div class="iso-row"><strong>${k}</strong><span class="badge badge-ok">${v}</span></div>
    `).join("");

    const snapMap = Object.fromEntries((d.snapshots || []).map((s) => [s.device_id, s]));
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
        <td>${badge(s.status || "UNKNOWN")}</td><td class="tabular-nums">${batt} / ${sig}</td><td class="tabular-nums">${ts}</td>
      </tr>`;
    }).join("") || '<tr><td colspan="7">No devices in selected project</td></tr>';

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
        ${(s.readings || []).map((r) => `
          <div class="metric-box">
            <div class="metric-name">${r.metric}${r.depth_level ? ` · ${r.depth_level * 10}cm` : ""}</div>
            <div class="metric-val tabular-nums">${r.value ?? "-"} <small>${r.unit || ""}</small></div>
          </div>
        `).join("") || '<div class="kpi-sub">No active readings (Epoch 1970 / NO_DATA guarded)</div>'}
      </div>`;

      return `<div class="sensor-card" data-device-id="${s.device_id}">
        <div class="sensor-card-head">
          <div class="sensor-title-wrap">
            <div class="icon-avatar">${window.ERPIcons.deviceIconHtml(s.source_code, 22)}</div>
            <div><strong>${dev.name}</strong><div class="mono" style="color:var(--muted)">${s.external_id} · ${s.source_code}</div></div>
          </div>
          ${badge(s.status)}
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
          ["Temp", f(cur.temperature, " °C")],
          ["Feels Like", f(cur.feels_like, " °C")],
          ["Humidity", f(cur.humidity, " %")],
          ["Pressure", f(cur.pressure, " hPa")],
          ["Wind", f(cur.wind_speed, " km/h")],
          ["Rain 1h/6h", `${f(cur.precipitation_1h)} / ${f(cur.precipitation_6h, " mm")}`],
          ["UV Index", f(cur.uv_index)],
          ["Cloud Cover", f(cur.cloud_cover, " %")],
        ].map(([n, v]) => `<div class="metric-box"><div class="metric-name">${n}</div><div class="metric-val tabular-nums">${v}</div></div>`).join("")
      : `<div class="kpi-sub">No current forecast step available</div>`;

    $("forecastDaysGrid").innerHTML = (met.days || []).map((d) => `
      <div class="forecast-day-card">
        <div class="forecast-day-date">${d.date}</div>
        ${window.ERPIcons.iconHtml(weatherLucideIcon(d.symbol), 28)}
        <div class="forecast-day-temps tabular-nums">${f(d.temperature_max, "°")} / ${f(d.temperature_min, "°")}</div>
        <div class="kpi-sub tabular-nums">Rain: ${f(d.precipitation, " mm")}</div>
        <div class="kpi-sub">${d.symbol || "-"}</div>
      </div>
    `).join("") || `<div class="kpi-sub">No forecast days available</div>`;

    $("forecastStepsBody").innerHTML = steps.slice(0, 24).map((s) => `
      <tr class="tabular-nums">
        <td>${s.time_utc}</td><td>${f(s.temperature)}</td><td>${f(s.feels_like)}</td><td>${f(s.humidity)}</td>
        <td>${f(s.pressure)}</td><td>${f(s.wind_speed)}</td><td>${f(s.precipitation_1h)}</td>
        <td>${f(s.cloud_cover)}</td><td>${f(s.uv_index)}</td><td>${s.symbol || "-"}</td>
      </tr>
    `).join("") || '<tr><td colspan="10">No hourly forecast steps</td></tr>';

    window.ERPCharts.renderForecastChart($("forecastCanvas"), $("forecastTooltip"), steps);

    const fcSteps = steps.slice(0, 24);
    const fcPts = (fn) => fcSteps.filter((s) => fn(s) != null).map((s) => ({ t: String(s.time_utc || "").slice(11, 16), v: Number(fn(s)) }));
    window.ERPCharts.renderComponentChartsGrid($("forecastComponentCharts"), [
      {
        id: "fc_temp", title: "Forecast Temperature & Feels Like", unit: "°C", icon: "thermometer-sun",
        series: [
          { label: "Temp", unit: "°C", color: "#38bdf8", points: fcPts((s) => s.temperature) },
          { label: "Feels Like", unit: "°C", color: "#f59e0b", points: fcPts((s) => s.feels_like) },
        ],
      },
      {
        id: "fc_rain", title: "Hourly Precipitation", unit: "mm", icon: "cloud-rain",
        series: [{ label: "Rain 1h", unit: "mm", color: "#22c55e", points: fcPts((s) => s.precipitation_1h ?? s.precipitation_6h ?? 0) }],
      },
      {
        id: "fc_rh", title: "Relative Humidity", unit: "%", icon: "droplet",
        series: [{ label: "Humidity", unit: "%", color: "#14b8a6", points: fcPts((s) => s.humidity) }],
      },
      {
        id: "fc_wind", title: "Wind Speed Forecast", unit: "km/h", icon: "wind",
        series: [{ label: "Wind", unit: "km/h", color: "#a78bfa", points: fcPts((s) => s.wind_speed) }],
      },
      {
        id: "fc_pressure", title: "Atmospheric Pressure Forecast", unit: "hPa", icon: "gauge",
        series: [{ label: "Pressure", unit: "hPa", color: "#60a5fa", points: fcPts((s) => s.pressure) }],
      },
      {
        id: "fc_cloud_uv", title: "Cloud Cover & UV Index", unit: "%", icon: "cloud-sun",
        series: [
          { label: "Cloud Cover", unit: "%", color: "#94a3b8", points: fcPts((s) => s.cloud_cover) },
          { label: "UV Index", unit: "UV", color: "#facc15", points: fcPts((s) => s.uv_index) },
        ],
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

  function renderAlertsAndExchange(incidents, policies, history, tokens, rows) {
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

    $("alertHistoryBody").innerHTML = (history || []).slice(0, 30).map((h) => `
      <tr>
        <td class="tabular-nums">${h.triggered_at_utc || "-"}</td><td>${h.policy_name}</td><td>${h.device_name || "-"}</td>
        <td>${h.rule_description}</td><td>${badge(h.delivery_status)}</td><td class="tabular-nums">${h.notification_count}</td>
      </tr>
    `).join("") || '<tr><td colspan="6">No alert history</td></tr>';

    const q = ($("exchangeSearch").value || "").toLowerCase();
    const filtered = rows.filter((r) => !q || r.code.toLowerCase().includes(q) || r.time.toLowerCase().includes(q));
    $("exchangeTokenMeta").textContent = tokens.length
      ? `Active Token: ${tokens[0].name} · Valid Until: ${tokens[0].valid_until_utc || "N/A"} · Limit: ${tokens[0].default_rows_per_request} rows/req`
      : "Weather rows derived live from project Weather Station";
    const f = (v) => (v == null ? "-" : Number(v).toFixed(1));
    $("exchangeBody").innerHTML = filtered.map((r) => `
      <tr>
        <td><code>${r.code}</code></td><td>${r.time}</td><td>${f(r.temperature_avg)}</td><td>${f(r.humidity_avg)}</td>
        <td>${f(r.deltat_avg)}</td><td>${f(r.dewpoint_avg)}</td><td>${f(r.atmos_pressure_avg)}</td><td>${f(r.msl_pressure)}</td>
        <td>${f(r.rainfall)}</td><td>${f(r.rainfall_total)}</td><td>${f(r.wind_speed_avg)}</td><td>${f(r.wind_speed_min)}</td>
        <td>${f(r.wind_speed_max)}</td><td>${f(r.wind_dir_deg_avg)}</td><td>${f(r.wind_dir_var_avg)}</td>
        <td>${f(r.solar_rad_avg)}</td><td>${f(r.uv_index_avg)}</td>
      </tr>
    `).join("") || '<tr><td colspan="17">No exchange rows available</td></tr>';

    renderExchangeRealtimeChart();
  }

  function renderExchangeRealtimeChart() {
    const ordered = [...(state.exchangeRows || [])].reverse().slice(-32);
    const specs = [];
    if (ordered.length) {
      EXCHANGE_COLUMN_SPECS.forEach((colSpec) => {
        const pts = ordered
          .filter((r) => r[colSpec.col] != null)
          .map((r) => ({ t: String(r.time || "").slice(11, 16), v: Number(r[colSpec.col]) }));
        if (pts.length) {
          specs.push({
            id: `ex_${colSpec.key}`,
            title: colSpec.title,
            unit: colSpec.unit,
            icon: colSpec.icon,
            cat: colSpec.cat,
            series: [{ label: colSpec.title, unit: colSpec.unit, color: colSpec.color, points: pts }],
          });
        }
      });
    }
    const primaryTemp = specs.find((s) => s.id === "ex_temperature") || specs[0];
    window.ERPCharts.renderRealtimeSeries($("exchangeRealtimeCanvas"), $("exchangeRealtimeTooltip"), {
      series: primaryTemp ? primaryTemp.series : [],
      emptyText: "No Weather Exchange rows in selected project.",
    });
    window.ERPCharts.renderComponentChartsGrid($("exchangeComponentCharts"), specs);
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
    $("auditBody").innerHTML = entries.map((e) => `
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
    renderAlertsAndExchange(state.incidents, state.policies, state.alertHistory, state.exchangeTokens, state.exchangeRows);
    renderAudit(state.audit, state.security || state.dash.security || {});

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
    $("exportCsvBtn").href = `/api/erp/v1/exchange/weather/export.csv?project_id=${encodeURIComponent(state.projectId)}`;

    const pq = `?project_id=${encodeURIComponent(state.projectId)}`;
    const [fields, assets, policies, alertHistory, incidents, exchange, forecast, audit, hist, sec] = await Promise.all([
      api(`/api/erp/v1/fields${pq}`),
      api(`/api/erp/v1/assets${pq}`),
      api(`/api/erp/v1/alerts/policies${pq}`),
      api(`/api/erp/v1/alerts/history${pq}`),
      api(`/api/erp/v1/incidents${pq}`),
      api(`/api/erp/v1/exchange/weather${pq}`),
      api(`/api/erp/v1/forecast${pq}`),
      api(`/api/erp/v1/audit?limit=40`),
      api(`/api/erp/v1/telemetry/history${pq}&hours=24`).catch(() => ({ data: [] })),
      api(`/api/erp/v1/security/status`).catch(() => dash.security || null),
    ]);

    state.fields = fields.data || [];
    state.assets = assets.data || [];
    state.policies = policies.data || [];
    state.alertHistory = alertHistory.data || [];
    state.incidents = incidents.data || [];
    state.exchangeTokens = exchange.tokens || [];
    state.exchangeRows = exchange.data || [];
    state.forecast = forecast;
    state.audit = audit.data || [];
    state.security = sec;

    ingestHistoryReadings(hist.data || []);
    (dash.snapshots || []).forEach((s) => recordDeviceSnapshotSeries(s, state.exchangeRows));

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
    refreshAll();
  });
  $("exchangeSearch").addEventListener("input", () => rerenderAllViews());

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
    const engine = grp.dataset.mapTarget === "overview" ? overviewMap : fullMap;
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

  window.ERPIcons.refresh();
  refreshAll().catch(console.error);
})();
