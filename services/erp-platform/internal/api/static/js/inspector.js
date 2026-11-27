/* Slide-over Device Inspector Drawer (L3) & Ctrl+K Command Palette */
window.ERPInspector = (() => {
  function rssiBarsHtml(dbm) {
    const val = Number(dbm);
    const active = !isFinite(val) ? 0 : val >= -65 ? 4 : val >= -78 ? 3 : val >= -90 ? 2 : 1;
    const heights = [5, 8, 11, 14];
    return `<span class="rssi-bars" title="${dbm ?? "N/A"} dBm">${heights.map((h, i) =>
      `<span class="rssi-bar ${i < active ? "on" : ""}" style="height:${h}px"></span>`
    ).join("")}</span>`;
  }

  function openDeviceDrawer(ctx, { device, snapshot, alerts, onLocate }) {
    const backdrop = document.getElementById("deviceDrawer");
    const body = document.getElementById("drawerBody");
    if (!backdrop || !body || !device) return;

    const snap = snapshot || { status: "UNKNOWN", readings: [], metadata: {} };
    const meta = snap.metadata || {};
    const avatarHtml = window.ERPIcons
      ? window.ERPIcons.deviceIconHtml(device.source_code, 26)
      : `<i data-lucide="cpu"></i>`;

    const devAlerts = (alerts || []).filter((a) =>
      a.device_name === device.name || (a.device_name || "").includes(device.external_id)
    ).slice(0, 6);

    const soilHtml = String(device.source_code || "").toLowerCase().includes("soil")
      ? window.ERPCharts.renderSoilDepthHtml(snap.readings)
      : "";

    body.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;">
        <div class="icon-avatar" style="width:56px;height:56px;">${avatarHtml}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;font-size:1.05rem;">${device.name}</div>
          <div class="mono" style="color:var(--muted);">${device.external_id} · ${device.source_code} · ${device.comm_type || "iot"}</div>
        </div>
      </div>

      <div class="metric-grid">
        <div class="metric-box"><div class="metric-name">Status</div><div class="metric-val">${snap.status}</div></div>
        <div class="metric-box"><div class="metric-name">Battery</div><div class="metric-val tabular-nums">${meta.battery_level != null ? meta.battery_level + "%" : "-"}</div></div>
        <div class="metric-box"><div class="metric-name">Signal</div><div class="metric-val tabular-nums">${rssiBarsHtml(meta.signal_strength_dbm)} ${meta.signal_strength_dbm != null ? meta.signal_strength_dbm + " dBm" : "-"}</div></div>
        <div class="metric-box"><div class="metric-name">Interval</div><div class="metric-val">${meta.reading_interval || "-"}</div></div>
      </div>

      ${device.coordinates ? `<button id="drawerLocateBtn" class="btn btn-primary" style="justify-content:center;">
        <i data-lucide="crosshair"></i> Locate on Google Satellite (${device.coordinates.latitude.toFixed(4)}, ${device.coordinates.longitude.toFixed(4)})
      </button>` : ""}

      ${soilHtml ? `<div><h4 style="font-size:0.86rem;margin-bottom:8px;">Rootzone Soil Profile</h4>${soilHtml}</div>` : ""}

      <div>
        <h4 style="font-size:0.86rem;margin-bottom:8px;">All Live Telemetry Readings</h4>
        <div class="metric-grid">
          ${(snap.readings || []).map((r) => `
            <div class="metric-box">
              <div class="metric-name">${r.metric}${r.depth_level ? ` D${r.depth_level}` : ""}</div>
              <div class="metric-val tabular-nums">${r.value ?? "-"} <small>${r.unit || ""}</small></div>
            </div>
          `).join("") || '<div class="kpi-sub">No active readings (Epoch 1970 / NO_DATA guarded)</div>'}
        </div>
      </div>

      <div>
        <h4 style="font-size:0.86rem;margin-bottom:8px;">Recent Device Alerts (${devAlerts.length})</h4>
        <div class="stack-list">
          ${devAlerts.map((a) => `
            <div class="stack-item">
              <div><strong>${a.policy_name}</strong><div class="kpi-sub">${a.rule_description}</div></div>
              <span class="badge badge-info">${a.delivery_status}</span>
            </div>
          `).join("") || '<div class="kpi-sub">No recent alerts for this device.</div>'}
        </div>
      </div>
    `;

    const locBtn = document.getElementById("drawerLocateBtn");
    if (locBtn && device.coordinates) {
      locBtn.addEventListener("click", () => {
        backdrop.classList.remove("open");
        onLocate(device.coordinates.latitude, device.coordinates.longitude);
      });
    }

    backdrop.classList.add("open");
    if (typeof lucide !== "undefined") lucide.createIcons();
  }

  function renderQuickSearch(query, catalog, onSelect) {
    const box = document.getElementById("searchResults");
    if (!box) return;
    const q = String(query || "").trim().toLowerCase();
    const hits = catalog.filter((item) =>
      !q || item.label.toLowerCase().includes(q) || item.sub.toLowerCase().includes(q)
    ).slice(0, 12);

    box.innerHTML = hits.map((h, idx) => `
      <div class="search-hit" data-hit-idx="${idx}">
        <div><strong>${h.label}</strong><div class="kpi-sub">${h.sub}</div></div>
        <span class="badge badge-info">${h.kind}</span>
      </div>
    `).join("") || '<div class="kpi-sub">No matching devices, fields, assets, or policies.</div>';

    box.querySelectorAll(".search-hit").forEach((el) => {
      el.addEventListener("click", () => {
        const hit = hits[Number(el.dataset.hitIdx)];
        if (hit) onSelect(hit);
      });
    });
  }

  return { rssiBarsHtml, openDeviceDrawer, renderQuickSearch };
})();
