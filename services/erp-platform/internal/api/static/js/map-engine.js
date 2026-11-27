/* Google Satellite Interactive Map Engine (Leaflet + Google Tiles + GeoJSON + Pure Lucide Markers) */
window.SatelliteMapEngine = class SatelliteMapEngine {
  constructor(containerId, coordReadoutId, opts = {}) {
    this.containerId = containerId;
    this.coordReadoutId = coordReadoutId;
    this.onInspectDevice = opts.onInspectDevice || (() => {});
    this.map = null;
    this.baseLayers = {};
    this.activeLayerKey = "satellite";
    this.fieldGroup = null;
    this.deviceGroup = null;
    this.assetGroup = null;
    this.forecastGroup = null;
    this.layerVis = { fields: true, devices: true, assets: true };
    this._lastBounds = null;
    this._lastProjectId = null;
    this._cachedData = null;
  }

  init() {
    if (this.map || typeof L === "undefined") return;
    const el = document.getElementById(this.containerId);
    if (!el) return;

    this.baseLayers = {
      satellite: L.tileLayer("https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", {
        subdomains: ["0", "1", "2", "3"], maxZoom: 21, attribution: "Google Satellite",
      }),
      hybrid: L.tileLayer("https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", {
        subdomains: ["0", "1", "2", "3"], maxZoom: 21, attribution: "Google Hybrid",
      }),
      terrain: L.tileLayer("https://mt{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}", {
        subdomains: ["0", "1", "2", "3"], maxZoom: 20, attribution: "Google Terrain",
      }),
      roadmap: L.tileLayer("https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", {
        subdomains: ["0", "1", "2", "3"], maxZoom: 21, attribution: "Google Maps",
      }),
    };

    this.map = L.map(el, {
      center: [11.6901, 106.8495],
      zoom: 16,
      layers: [this.baseLayers.satellite],
      zoomControl: true,
    });

    this.fieldGroup = L.layerGroup().addTo(this.map);
    this.deviceGroup = L.layerGroup().addTo(this.map);
    this.assetGroup = L.layerGroup().addTo(this.map);
    this.forecastGroup = L.layerGroup().addTo(this.map);

    this.map.on("mousemove", (ev) => {
      const out = document.getElementById(this.coordReadoutId);
      if (out) out.textContent = `GPS: ${ev.latlng.lat.toFixed(5)}, ${ev.latlng.lng.toFixed(5)}`;
    });
  }

  setBaseLayer(key) {
    if (!this.map || !this.baseLayers[key] || key === this.activeLayerKey) return;
    this.map.removeLayer(this.baseLayers[this.activeLayerKey]);
    this.baseLayers[key].addTo(this.map);
    this.activeLayerKey = key;
  }

  setLayerVisibility(name, visible) {
    this.layerVis[name] = visible;
    if (!this.map) return;
    const grp = name === "fields" ? this.fieldGroup : name === "devices" ? this.deviceGroup : this.assetGroup;
    if (!grp) return;
    if (visible && !this.map.hasLayer(grp)) grp.addTo(this.map);
    if (!visible && this.map.hasLayer(grp)) this.map.removeLayer(grp);
  }

  invalidateSize() {
    if (this.map) setTimeout(() => this.map.invalidateSize(), 60);
  }

  fitBounds() {
    if (this.map && this._lastBounds && this._lastBounds.isValid()) {
      this.map.fitBounds(this._lastBounds.pad(0.22), { maxZoom: 18 });
    }
  }

  focusCoordinate(lat, lon, zoom = 18) {
    if (this.map && Number.isFinite(Number(lat)) && Number.isFinite(Number(lon))) {
      this.map.setView([Number(lat), Number(lon)], zoom, { animate: true });
    }
  }

  _approxAreaHa(ring) {
    if (!Array.isArray(ring) || ring.length < 3) return 0;
    const rad = Math.PI / 180;
    const R = 6378137;
    let area = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[i + 1];
      area += (lon2 - lon1) * rad * (2 + Math.sin(lat1 * rad) + Math.sin(lat2 * rad));
    }
    return Math.abs((area * R * R) / 2) / 10000;
  }

  render(data, projectId = "", opts = {}) {
    this._cachedData = data;
    this.init();
    if (!this.map) return;

    this.fieldGroup.clearLayers();
    this.deviceGroup.clearLayers();
    this.assetGroup.clearLayers();
    if (this.forecastGroup) this.forecastGroup.clearLayers();

    const bounds = L.latLngBounds([]);
    const snapMap = Object.fromEntries((data.snapshots || []).map((s) => [s.device_id, s]));
    const selectedId = opts.selectedDeviceId || "";
    let focusedCoords = null;

    // 1. GeoJSON Fields
    (data.fields || []).forEach((fld) => {
      (fld.sites || []).forEach((site) => {
        if (!site.geojson) return;
        const layer = L.geoJSON(site.geojson, {
          style: { color: "#38bdf8", weight: 2.5, fillColor: "#0ea5e9", fillOpacity: 0.2 },
          onEachFeature: (feat, lyr) => {
            const ring = feat.geometry && feat.geometry.coordinates && feat.geometry.coordinates[0];
            const ha = site.area != null ? Number(site.area).toFixed(2) : this._approxAreaHa(ring).toFixed(2);
            lyr.bindTooltip(`<strong>${fld.name}</strong><br>${site.name} (${ha} ha)`, { sticky: true });
          },
        });
        layer.addTo(this.fieldGroup);
        try {
          const b = layer.getBounds();
          if (b.isValid()) bounds.extend(b);
        } catch (_) {}
      });
    });

    // 2. IoT Device Markers (Pure Lucide + Status Ring)
    (data.devices || []).forEach((dev) => {
      if (!dev.coordinates) return;
      const latlng = [dev.coordinates.latitude, dev.coordinates.longitude];
      bounds.extend(latlng);

      const snap = snapMap[dev.id] || { status: "UNKNOWN", readings: [] };
      const innerSvg = window.ERPIcons
        ? window.ERPIcons.deviceIconHtml(dev.source_code, 18)
        : `<i data-lucide="cpu"></i>`;

      const isSelected = Boolean(selectedId && dev.id === selectedId);
      if (isSelected) focusedCoords = latlng;
      const ringCls = snap.status === "NO_DATA" || snap.status === "OFFLINE" ? "nodata" : "";
      const iconHtml = `<div class="axs-marker-wrap">
        <span class="axs-marker-ring ${ringCls}"></span>
        <span class="axs-marker-core ${isSelected ? "selected" : ""}">${innerSvg}</span>
      </div>`;

      const marker = L.marker(latlng, {
        icon: L.divIcon({ className: "", html: iconHtml, iconSize: [44, 44], iconAnchor: [22, 22] }),
      });

      const previewMetrics = (snap.readings || []).slice(0, 4)
        .map((r) => `<div><span style="color:var(--muted)">${r.metric}${r.depth_level ? ` D${r.depth_level}` : ""}:</span> <strong class="tabular-nums">${r.value} ${r.unit || ""}</strong></div>`)
        .join("") || '<div style="color:var(--muted)">Status: NO_DATA (Epoch sentinel guarded)</div>';

      const popupEl = document.createElement("div");
      popupEl.className = "map-popup";
      popupEl.innerHTML = `
        <div class="map-popup-head">${dev.name}</div>
        <div class="mono" style="color:var(--muted)">${dev.external_id} · ${dev.source_code} · ${snap.status}</div>
        ${previewMetrics}
        <button class="btn btn-primary btn-sm" style="margin-top:4px;justify-content:center;">Inspect Device Details</button>
      `;
      popupEl.querySelector("button").addEventListener("click", () => this.onInspectDevice(dev.id));

      marker.bindPopup(popupEl);
      marker.addTo(this.deviceGroup);
    });

    // 3. Physical Assets
    (data.assets || []).forEach((ast) => {
      if (!ast.position) return;
      const latlng = [ast.position.latitude, ast.position.longitude];
      bounds.extend(latlng);
      const innerSvg = window.ERPIcons
        ? window.ERPIcons.assetIconHtml(ast.asset_type, 18)
        : `<i data-lucide="tractor"></i>`;
      const iconHtml = `<div class="axs-marker-wrap"><span class="axs-marker-core" style="border-color:#f59e0b">${innerSvg}</span></div>`;
      L.marker(latlng, {
        icon: L.divIcon({ className: "", html: iconHtml, iconSize: [40, 40], iconAnchor: [20, 20] }),
      }).bindPopup(`<div class="map-popup"><div class="map-popup-head">${ast.name}</div><div>Type: ${ast.asset_type}</div><div>Capacity: ${ast.capacity_litres ? ast.capacity_litres + " L" : "-"}</div></div>`)
        .addTo(this.assetGroup);
    });

    const projectChanged = projectId && projectId !== this._lastProjectId;
    const firstRender = !this._lastBounds;
    this._lastBounds = bounds;
    if (projectId) this._lastProjectId = projectId;
    if (focusedCoords) this.focusCoordinate(focusedCoords[0], focusedCoords[1], 17);
    else if ((firstRender || projectChanged) && bounds.isValid()) this.fitBounds();
    if (typeof lucide !== "undefined") lucide.createIcons();
  }

  renderForecastLocation(location, currentStep = null, fields = []) {
    this.init();
    if (!this.map) return;

    this.fieldGroup.clearLayers();
    this.deviceGroup.clearLayers();
    this.assetGroup.clearLayers();
    if (this.forecastGroup) this.forecastGroup.clearLayers();

    const bounds = L.latLngBounds([]);
    (fields || []).forEach((fld) => {
      (fld.sites || []).forEach((site) => {
        if (!site.geojson) return;
        const layer = L.geoJSON(site.geojson, {
          style: { color: "#38bdf8", weight: 2, fillColor: "#0ea5e9", fillOpacity: 0.14 },
        });
        layer.addTo(this.fieldGroup);
        try {
          const b = layer.getBounds();
          if (b.isValid()) bounds.extend(b);
        } catch (_) {}
      });
    });

    const lat = Number(location?.latitude);
    const lon = Number(location?.longitude);
    if (Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      const sym = currentStep?.symbol || "cloud-sun";
      const symMeta = window.ERPIcons
        ? window.ERPIcons.getWeatherSymbolMeta(sym)
        : { color: "#38bdf8", bg: "rgba(56,189,248,0.18)", border: "#38bdf8", label: sym };
      const symHtml = window.ERPIcons
        ? window.ERPIcons.weatherSymbolHtml(sym, 22)
        : `<i data-lucide="cloud-sun"></i>`;

      L.circle([lat, lon], {
        radius: 450,
        color: symMeta.color,
        weight: 2,
        fillColor: symMeta.color,
        fillOpacity: 0.14,
      }).addTo(this.forecastGroup);

      const tempStr = currentStep?.temperature != null ? `${Number(currentStep.temperature).toFixed(1)} °C` : "-";
      const rhStr = currentStep?.humidity != null ? `${Number(currentStep.humidity).toFixed(0)} %` : "-";
      const rainStr = currentStep?.precipitation_1h != null ? `${Number(currentStep.precipitation_1h).toFixed(1)} mm` : "0.0 mm";
      const elevStr = location?.elevation != null ? ` · Elev: ${location.elevation} m` : "";
      const markerHtml = `<div class="forecast-pin-marker" style="border-color:${symMeta.color};box-shadow:0 0 18px ${symMeta.color}66;">${symHtml}</div>`;

      const fMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: "", html: markerHtml, iconSize: [52, 52], iconAnchor: [26, 26] }),
      });
      fMarker.bindPopup(`
        <div class="map-popup">
          <div class="map-popup-head">${location?.name || "Forecast Target Location"}</div>
          <div class="mono" style="color:var(--muted)">GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)}${elevStr}</div>
          <div>Source: <strong>${location?.source || "MET Norway (AxisStream)"}</strong></div>
          <div>Condition: <strong>${symMeta.label}</strong></div>
          <div>Temp: <strong>${tempStr}</strong> · RH: <strong>${rhStr}</strong> · Rain: <strong>${rainStr}</strong></div>
        </div>
      `);
      fMarker.addTo(this.forecastGroup);
      bounds.extend([lat, lon]);
      this._lastBounds = bounds;
      this.focusCoordinate(lat, lon, 14);
    } else if (bounds.isValid()) {
      this._lastBounds = bounds;
      this.fitBounds();
    }
    if (typeof lucide !== "undefined") lucide.createIcons();
  }
};
