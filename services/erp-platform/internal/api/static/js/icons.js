// Pure Lucide icon mapping for all ERP devices, assets, vendors, and metrics.
window.ERPIcons = (() => {
  const DEVICE_ICONS = {
    SOIL_MOISTURE: "droplets",
    SOILPROBE: "sprout",
    TEMP_HUMIDITY: "thermometer-sun",
    WEATHER_STATION: "cloud-sun-rain",
    RAIN_GAUGE: "cloud-rain",
    SOLAR_GATEWAY: "radio-tower",
    IRRIGATION_VALVE: "gauge",
    GATEWAY: "router",
    WATER_LEVEL: "waves",
  };

  const ASSET_ICONS = {
    TRACTOR: "tractor",
    PUMP: "droplet",
    PUMP_STATION: "droplet",
    SILO: "warehouse",
    WAREHOUSE: "warehouse",
    DRONE: "plane",
    GREENHOUSE: "trees",
    FIELD: "map-pinned",
    WEATHER_STATION: "cloud-sun",
    SENSOR: "cpu",
  };

  function deviceName(sourceCode = "") {
    const code = String(sourceCode || "").toUpperCase();
    for (const [key, icon] of Object.entries(DEVICE_ICONS)) {
      if (code.includes(key)) return icon;
    }
    if (code.includes("SOIL")) return "sprout";
    if (code.includes("WEATHER") || code.includes("MET")) return "cloud-sun-rain";
    if (code.includes("VALVE") || code.includes("PUMP")) return "gauge";
    if (code.includes("GATEWAY")) return "radio-tower";
    return "cpu";
  }

  function assetName(assetType = "") {
    const type = String(assetType || "").toUpperCase();
    for (const [key, icon] of Object.entries(ASSET_ICONS)) {
      if (type.includes(key)) return icon;
    }
    return "tractor";
  }

  function vendorName(id = "") {
    const k = String(id || "").toLowerCase();
    if (k.includes("demo")) return "layers";
    return "building-2";
  }

  function iconHtml(name, size = 18, extraClass = "") {
    const safeName = String(name || "cpu").replace(/[^a-z0-9-]/gi, "");
    const cls = extraClass ? ` ${extraClass}` : "";
    return `<i data-lucide="${safeName}" class="lucide-icon${cls}" style="width:${size}px;height:${size}px"></i>`;
  }

  function deviceIconHtml(sourceCode = "", size = 20, extraClass = "") {
    return iconHtml(deviceName(sourceCode), size, extraClass);
  }

  function assetIconHtml(assetType = "", size = 20, extraClass = "") {
    return iconHtml(assetName(assetType), size, extraClass);
  }

  function vendorIconHtml(vendorId = "", size = 20, extraClass = "") {
    return iconHtml(vendorName(vendorId), size, extraClass);
  }

  function refresh(root = document) {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      try {
        window.lucide.createIcons({ root });
      } catch (_) {
        window.lucide.createIcons();
      }
    }
  }

  return {
    deviceName,
    assetName,
    vendorName,
    iconHtml,
    deviceIconHtml,
    assetIconHtml,
    vendorIconHtml,
    refresh,
  };
})();
