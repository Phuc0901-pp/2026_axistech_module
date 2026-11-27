/* Standalone Isolated Module Controller (ISO 27001 Least Privilege: ONLY fetches /api/tbsgagtech/v1/modules/{dev|forecast}/{token}) */
(() => {
  const PAGE_SIZE = 10;
  const AUTO_POLL_MS = 15000;

  const FORECAST_METRICS = [
    { key: "temperature", title: "Air Temperature", unit: "°C", color: "#38bdf8", chartType: "line" },
    { key: "feels_like", title: "Feels Like Temperature", unit: "°C", color: "#f59e0b", chartType: "line" },
    { key: "dew_point", title: "Dew Point", unit: "°C", color: "#22c55e", chartType: "line" },
    { key: "precipitation_1h", title: "Hourly Precipitation", unit: "mm", color: "#0ea5e9", chartType: "bar" },
    { key: "humidity", title: "Relative Humidity", unit: "%", color: "#14b8a6", chartType: "line" },
    { key: "wind_speed", title: "Wind Speed", unit: "km/h", color: "#a78bfa", chartType: "line" },
    { key: "pressure", title: "Atmospheric Pressure", unit: "hPa", color: "#60a5fa", chartType: "line" },
    { key: "cloud_cover", title: "Cloud Cover", unit: "%", color: "#94a3b8", chartType: "line" },
    { key: "uv_index", title: "UV Index", unit: "UV", color: "#facc15", chartType: "line" },
  ];

  const METRIC_COLORS = {
    temperature: "#38bdf8",
    humidity: "#22c55e",
    moisture: "#14b8a6",
    atmos_pressure: "#60a5fa",
    msl_pressure: "#818cf8",
    delta_t: "#fb7185",
    dew_point: "#a78bfa",
    wind_speed: "#f59e0b",
    wind_gust: "#fb7185",
    solar_radiation: "#facc15",
    uv_index: "#fb923c",
    battery_pct: "#22c55e",
    signal_strength_dbm: "#14b8a6",
  };

  const state = {
    mode: "",
    token: "",
    metric: "",
    page: 1,
    theme: localStorage.getItem("axs_theme") || "dark",
    mapInitializedFor: "",
    data: null,
  };

  document.documentElement.dataset.theme = state.theme;
  const $ = (id) => document.getElementById(id);

  function parseRouteToken() {
    const path = window.location.pathname || "";
    const devM = path.match(/^\/tbsgagtech\/v1\/modules\/devices\/([^/]+)/);
    if (devM) {
      state.mode = "devices";
      state.token = decodeURIComponent(devM[1]);
      return true;
    }
    const fcM = path.match(/^\/tbsgagtech\/v1\/modules\/forecast\/([^/]+)/);
    if (fcM) {
      state.mode = "forecast";
      state.token = decodeURIComponent(fcM[1]);
      state.metric = "temperature";
      return true;
    }
    return false;
  }

  const standaloneMap = new window.SatelliteMapEngine("standaloneMap", "standaloneCoords", {
    onInspectDevice: () => {},
  });

  function renderPagination(totalItems, currentPage) {
    const pagerEl = $("standalonePagination");
    if (!pagerEl) return 1;
    const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
    const safePage = Math.min(Math.max(1, currentPage), totalPages);
    if (!totalItems) {
      pagerEl.innerHTML = `<span class="kpi-sub">0 records (${PAGE_SIZE}/page)</span>`;
      return 1;
    }
    const startIdx = (safePage - 1) * PAGE_SIZE + 1;
    const endIdx = Math.min(totalItems, safePage * PAGE_SIZE);
    let pageBtns = "";
    for (let p = Math.max(1, safePage - 2); p <= Math.min(totalPages, safePage + 2); p++) {
      pageBtns += `<button type="button" class="page-btn ${p === safePage ? "active" : ""}" data-page="${p}">${p}</button>`;
    }
    pagerEl.innerHTML = `
      <span class="tabular-nums">Showing <strong>${startIdx}-${endIdx}</strong> of <strong>${totalItems}</strong> (${PAGE_SIZE}/page)</span>
      <div class="page-controls">
        <button type="button" class="page-btn" data-page="${safePage - 1}" ${safePage <= 1 ? "disabled" : ""}>Prev</button>
        ${pageBtns}
        <button type="button" class="page-btn" data-page="${safePage + 1}" ${safePage >= totalPages ? "disabled" : ""}>Next</button>
      </div>
    `;
    pagerEl.querySelectorAll(".page-btn[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextPage = Number(btn.dataset.page);
        if (nextPage >= 1 && nextPage <= totalPages && nextPage !== state.page) {
          state.page = nextPage;
          refreshModule();
        }
      });
    });
    return safePage;
  }

  function renderDeviceView(d) {
    const dev = d.device || {};
    const pw = d.power_state || { status: "OFF", reason: "Unknown" };
    const isOn = String(pw.status).toUpperCase() === "ON";
    const meta = d.metadata || {};

    $("standaloneTitle").textContent = dev.name || "AxisTech Device";
    $("standaloneIcon").innerHTML = window.ERPIcons.deviceIconHtml(dev.source_code, 22);
    $("standaloneStatusSlot").innerHTML = `
      <span class="power-pill ${isOn ? "on" : "off"}">
        <span class="power-dot"></span>
        ${window.ERPIcons.iconHtml(isOn ? "power" : "power-off", 12)}
        <span>${pw.status} · ${pw.reason}</span>
      </span>
    `;
    const gps = d.geolocation?.coordinates;
    const gpsText = gps ? `GPS: ${Number(gps.latitude).toFixed(5)}, ${Number(gps.longitude).toFixed(5)}` : "GPS: N/A";
    const battStr = meta.battery_level != null ? ` · Batt: ${meta.battery_level}%` : "";
    const sigStr = meta.signal_strength_dbm != null ? ` · RSSI: ${meta.signal_strength_dbm} dBm` : "";
    $("standaloneSubtitle").textContent = `ID: ${dev.external_id || "-"} · ${dev.source_code || "sensor"} · ${gpsText}${battStr}${sigStr}`;

    const metrics = Array.isArray(d.available_metrics) && d.available_metrics.length
      ? d.available_metrics
      : (d.chart?.metric ? [d.chart.metric] : []);
    if (!state.metric || (metrics.length && !metrics.includes(state.metric))) {
      state.metric = d.chart?.metric || metrics[0] || "";
    }
    $("standaloneMetricPills").innerHTML = metrics.map((m) => `
      <button type="button" class="metric-pill ${state.metric === m ? "active" : ""}" data-metric="${m}">${m}</button>
    `).join("") || '<span class="kpi-sub">No active telemetry metrics</span>';
    $("standaloneMetricPills").querySelectorAll("[data-metric]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.metric = btn.dataset.metric;
        state.page = 1;
        refreshModule();
      });
    });

    $("standaloneMapTitle").textContent = `Device Geolocation: ${dev.name || dev.external_id || ""}`;
    $("standaloneGeoSummary").textContent = gps
      ? `${gpsText} · Comm: ${dev.comm_type || "IoT"}`
      : "No fixed GPS — showing field geometry";
    const snapStatus = isOn ? "LIVE" : (pw.reason === "Disabled" ? "OFFLINE" : "NO_DATA");
    standaloneMap.render(
      {
        fields: d.geolocation?.fields || [],
        devices: dev.id ? [dev] : [],
        snapshots: dev.id ? [{ device_id: dev.id, status: snapStatus, readings: d.table?.rows || [] }] : [],
        assets: [],
      },
      dev.id || "standalone",
      { selectedDeviceId: dev.id || "" }
    );

    const chart = d.chart || {};
    const metricName = chart.metric || state.metric || "Telemetry";
    const metricUnit = chart.unit || "";
    const pts = (chart.points || []).map((p) => ({
      t: String(p.t || "").slice(5, 16).replace("T", " "),
      v: Number(p.v),
    }));
    const vals = pts.map((p) => p.v).filter((n) => isFinite(n));
    const minV = vals.length ? Math.min(...vals).toFixed(2) : "-";
    const maxV = vals.length ? Math.max(...vals).toFixed(2) : "-";
    const avgV = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
    const latestV = vals.length ? vals[vals.length - 1].toFixed(2) : "-";

    $("standaloneMetricTitle").innerHTML = `${window.ERPIcons.iconHtml("table", 16)}<span>1 Data + 1 Graph — ${metricName}</span>`;
    $("standaloneMetricStats").innerHTML = `
      <span class="stat-pill">Latest <strong>${latestV} ${metricUnit}</strong></span>
      <span class="stat-pill">Min <strong>${minV}</strong></span>
      <span class="stat-pill">Avg <strong>${avgV}</strong></span>
      <span class="stat-pill">Max <strong>${maxV}</strong></span>
    `;
    $("standaloneChartHeader").textContent = `${metricName}${metricUnit ? ` (${metricUnit})` : ""}`;
    $("standaloneChartBadge").textContent = `${latestV} ${metricUnit}`.trim();

    const tbl = d.table || { total: 0, page: 1, rows: [] };
    renderPagination(tbl.total || 0, tbl.page || state.page);
    $("standaloneTableHead").innerHTML = `<tr><th>Timestamp (UTC)</th><th>Metric</th><th>Depth</th><th>Value</th><th>Unit</th><th>Power</th></tr>`;
    $("standaloneTableBody").innerHTML = (tbl.rows || []).map((r) => `
      <tr>
        <td>${String(r.timestamp_utc || "").replace("T", " ").slice(0, 19)}</td>
        <td>${r.metric}</td>
        <td>${r.depth_level ? `${r.depth_level * 10} cm` : "-"}</td>
        <td><strong>${r.value != null ? Number(r.value).toFixed(2) : "-"}</strong></td>
        <td>${r.unit || "-"}</td>
        <td><span class="power-pill ${isOn ? "on" : "off"}"><span class="power-dot"></span>${pw.status}</span></td>
      </tr>
    `).join("") || '<tr><td colspan="6">No records for selected metric</td></tr>';

    window.ERPCharts.renderRealtimeSeries($("standaloneChartCanvas"), $("standaloneChartTooltip"), {
      height: 290,
      series: pts.length ? [{ label: metricName, unit: metricUnit, color: METRIC_COLORS[metricName] || "#38bdf8", points: pts }] : [],
      emptyText: "Waiting for telemetry samples...",
    });
  }

  function renderForecastView(d) {
    const loc = d.location || {};
    const cur = d.current || null;
    const sym = cur?.symbol || "cloud-sun";

    $("standaloneTitle").textContent = loc.name || "Forecast Point";
    $("standaloneIcon").innerHTML = window.ERPIcons.weatherSymbolHtml(sym, 22);
    $("standaloneStatusSlot").innerHTML = window.ERPIcons.weatherSymbolBadgeHtml(sym);

    const lat = Number(loc.latitude);
    const lon = Number(loc.longitude);
    const gpsText = (isFinite(lat) && isFinite(lon)) ? `GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)}` : "GPS: N/A";
    const elevStr = loc.elevation != null ? ` · Elev: ${loc.elevation}m` : "";
    $("standaloneSubtitle").textContent = `${gpsText}${elevStr} · TZ: ${loc.time_zone || "UTC"}`;

    if (!state.metric) state.metric = "temperature";
    $("standaloneMetricPills").innerHTML = FORECAST_METRICS.map((fm) => `
      <button type="button" class="metric-pill ${state.metric === fm.key ? "active" : ""}" data-fc-metric="${fm.key}">${fm.title}</button>
    `).join("");
    $("standaloneMetricPills").querySelectorAll("[data-fc-metric]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.metric = btn.dataset.fcMetric;
        state.page = 1;
        refreshModule();
      });
    });

    $("standaloneMapTitle").textContent = `Forecast Target Location: ${loc.name || ""}`;
    $("standaloneGeoSummary").textContent = `${gpsText}${elevStr} · MET Norway Forecast`;
    standaloneMap.renderForecastLocation(
      { ...loc, source: "MET Norway (AxisStream)" },
      cur,
      []
    );

    const fm = FORECAST_METRICS.find((x) => x.key === state.metric) || FORECAST_METRICS[0];
    const chart = d.chart || {};
    const pts = (chart.points || []).slice(0, 36).map((p) => ({
      t: String(p.t || "").slice(11, 16),
      v: Number(p.v),
    }));
    const vals = (chart.points || []).map((p) => Number(p.v)).filter((n) => isFinite(n));
    const minV = vals.length ? Math.min(...vals).toFixed(1) : "-";
    const maxV = vals.length ? Math.max(...vals).toFixed(1) : "-";
    const avgV = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : "-";
    const nowV = vals.length ? vals[0].toFixed(1) : "-";

    $("standaloneMetricTitle").innerHTML = `${window.ERPIcons.iconHtml("cloud-sun-rain", 16)}<span>1 Data + 1 Graph — ${fm.title}</span>`;
    $("standaloneMetricStats").innerHTML = `
      <span class="stat-pill">Now <strong>${nowV} ${chart.unit || fm.unit}</strong></span>
      <span class="stat-pill">Min <strong>${minV}</strong></span>
      <span class="stat-pill">Avg <strong>${avgV}</strong></span>
      <span class="stat-pill">Max <strong>${maxV}</strong></span>
    `;
    $("standaloneChartHeader").textContent = `${fm.title} (${chart.unit || fm.unit})`;
    $("standaloneChartBadge").textContent = `${nowV} ${chart.unit || fm.unit}`;

    const tbl = d.table || { total: 0, page: 1, rows: [] };
    renderPagination(tbl.total || 0, tbl.page || state.page);
    $("standaloneTableHead").innerHTML = `<tr><th>Time</th><th>Weather Symbol</th><th>${fm.title}</th><th>Unit</th><th>Rain 1h</th><th>Wind</th></tr>`;
    $("standaloneTableBody").innerHTML = (tbl.rows || []).map((r) => `
      <tr>
        <td>${(r.time_local || r.time_utc || "").replace("T", " ").slice(5, 16)}</td>
        <td>${window.ERPIcons.weatherSymbolBadgeHtml(r.symbol)}</td>
        <td><strong>${r.value != null ? Number(r.value).toFixed(1) : "-"}</strong></td>
        <td>${r.unit || fm.unit}</td>
        <td>${r.precipitation_1h != null ? `${Number(r.precipitation_1h).toFixed(1)} mm` : "-"}</td>
        <td>${r.wind_speed != null ? `${Number(r.wind_speed).toFixed(1)} km/h` : "-"}</td>
      </tr>
    `).join("") || '<tr><td colspan="6">No forecast records available</td></tr>';

    window.ERPCharts.renderRealtimeSeries($("standaloneChartCanvas"), $("standaloneChartTooltip"), {
      height: 290,
      chartType: chart.chart_type || fm.chartType,
      series: pts.length ? [{ label: fm.title, unit: chart.unit || fm.unit, color: fm.color, points: pts }] : [],
      emptyText: "No forecast series points available...",
    });
  }

  async function refreshModule() {
    if (!state.token || !state.mode) return;
    const base = state.mode === "devices"
      ? `/api/tbsgagtech/v1/modules/devices/${encodeURIComponent(state.token)}`
      : `/api/tbsgagtech/v1/modules/forecast/${encodeURIComponent(state.token)}`;
    const params = new URLSearchParams();
    if (state.metric) params.set("metric", state.metric);
    params.set("page", String(state.page));
    params.set("page_size", String(PAGE_SIZE));

    try {
      const res = await fetch(`${base}?${params.toString()}`);
      if (!res.ok) {
        const prob = await res.json().catch(() => ({}));
        throw new Error(prob.detail || `HTTP ${res.status} (${prob.title || "ACCESS_DENIED"})`);
      }
      const data = await res.json();
      state.data = data;
      $("standaloneError").style.display = "none";

      if (state.mode === "devices") renderDeviceView(data);
      else renderForecastView(data);

      $("standaloneUpdatedAt").textContent = `${new Date().toISOString().slice(11, 19)} UTC`;
      window.ERPIcons.refresh();
    } catch (err) {
      $("standaloneError").textContent = `Module Security / Sync Error: ${err.message}`;
      $("standaloneError").style.display = "block";
    }
  }

  $("standaloneThemeBtn").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    localStorage.setItem("axs_theme", state.theme);
    document.documentElement.dataset.theme = state.theme;
  });

  document.querySelectorAll(".map-btn-group").forEach((grp) => {
    grp.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.dataset.fit) { standaloneMap.fitBounds(); return; }
      if (btn.dataset.layer) {
        grp.querySelectorAll("button[data-layer]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        standaloneMap.setBaseLayer(btn.dataset.layer);
      }
    });
  });

  if (!parseRouteToken()) {
    $("standaloneError").textContent = "Invalid ISO module URL: missing encrypted dev_ or fcp_ resource token.";
    $("standaloneError").style.display = "block";
    return;
  }

  // Real-time auto-update via SSE + 15s fallback poll
  const es = new EventSource("/api/erp/v1/events");
  es.addEventListener("connected", () => {
    $("standaloneLiveBadge").className = "status-pill live";
  });
  es.addEventListener("sync_update", () => refreshModule());
  es.onerror = () => {
    $("standaloneLiveBadge").className = "status-pill connecting";
  };
  setInterval(() => refreshModule(), AUTO_POLL_MS);

  window.ERPIcons.refresh();
  refreshModule();
})();
