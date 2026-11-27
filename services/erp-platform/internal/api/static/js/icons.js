// Pure Lucide icon + color-coded weather symbol mapping for AxisTech ISO ERP.
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

  function getWeatherSymbolMeta(symbol = "") {
    const raw = String(symbol || "").trim();
    const s = raw.toLowerCase();
    const isNight = s.includes("_night") || s.endsWith("night");
    const label = raw
      ? raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      : "Unknown";

    if (s.includes("thunder")) {
      return {
        icon: "cloud-lightning",
        label,
        color: "#c084fc",
        bg: "rgba(192, 132, 252, 0.16)",
        border: "rgba(192, 132, 252, 0.42)",
      };
    }
    if (s.includes("heavyrain") || s.includes("rainshowers")) {
      return {
        icon: "cloud-rain-wind",
        label,
        color: "#0ea5e9",
        bg: "rgba(14, 165, 233, 0.16)",
        border: "rgba(14, 165, 233, 0.42)",
      };
    }
    if (s.includes("rain") || s.includes("drizzle") || s.includes("sleet")) {
      return {
        icon: "cloud-rain",
        label,
        color: "#38bdf8",
        bg: "rgba(56, 189, 248, 0.16)",
        border: "rgba(56, 189, 248, 0.40)",
      };
    }
    if (s.includes("snow")) {
      return {
        icon: "snowflake",
        label,
        color: "#67e8f9",
        bg: "rgba(103, 232, 249, 0.16)",
        border: "rgba(103, 232, 249, 0.42)",
      };
    }
    if (s.includes("fog")) {
      return {
        icon: "cloud-fog",
        label,
        color: "#94a3b8",
        bg: "rgba(148, 163, 184, 0.16)",
        border: "rgba(148, 163, 184, 0.40)",
      };
    }
    if (isNight && (s.includes("clear") || s.includes("fair"))) {
      return {
        icon: "moon-star",
        label,
        color: "#818cf8",
        bg: "rgba(129, 140, 248, 0.16)",
        border: "rgba(129, 140, 248, 0.40)",
      };
    }
    if (isNight && s.includes("partly")) {
      return {
        icon: "cloud-moon",
        label,
        color: "#a78bfa",
        bg: "rgba(167, 139, 250, 0.16)",
        border: "rgba(167, 139, 250, 0.40)",
      };
    }
    if (s.includes("clear") || s.includes("fair") || s.includes("sun")) {
      return {
        icon: "sun",
        label,
        color: "#f59e0b",
        bg: "rgba(245, 158, 11, 0.16)",
        border: "rgba(245, 158, 11, 0.42)",
      };
    }
    if (s.includes("partly")) {
      return {
        icon: "cloud-sun",
        label,
        color: "#fbbf24",
        bg: "rgba(251, 191, 36, 0.16)",
        border: "rgba(251, 191, 36, 0.40)",
      };
    }
    if (s.includes("cloud")) {
      return {
        icon: "cloud",
        label,
        color: "#64748b",
        bg: "rgba(100, 116, 139, 0.16)",
        border: "rgba(100, 116, 139, 0.40)",
      };
    }
    return {
      icon: "cloud-sun",
      label,
      color: "#38bdf8",
      bg: "rgba(56, 189, 248, 0.14)",
      border: "rgba(56, 189, 248, 0.36)",
    };
  }

  function iconHtml(name, size = 18, extraClass = "") {
    const safeName = String(name || "cpu").replace(/[^a-z0-9-]/gi, "");
    const cls = extraClass ? ` ${extraClass}` : "";
    return `<i data-lucide="${safeName}" class="lucide-icon${cls}" style="width:${size}px;height:${size}px"></i>`;
  }

  function weatherSymbolHtml(symbol = "", size = 24) {
    const meta = getWeatherSymbolMeta(symbol);
    const pad = Math.max(6, Math.round(size * 0.34));
    return `<span class="weather-sym-chip" title="${meta.label}" style="color:${meta.color};background:${meta.bg};border-color:${meta.border};padding:${pad}px;">
      ${iconHtml(meta.icon, size)}
    </span>`;
  }

  function weatherSymbolBadgeHtml(symbol = "") {
    const meta = getWeatherSymbolMeta(symbol);
    return `<span class="weather-sym-badge" title="${meta.label}" style="color:${meta.color};background:${meta.bg};border-color:${meta.border};">
      ${iconHtml(meta.icon, 14)}
      <span>${meta.label}</span>
    </span>`;
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
    getWeatherSymbolMeta,
    weatherSymbolHtml,
    weatherSymbolBadgeHtml,
    iconHtml,
    deviceIconHtml,
    assetIconHtml,
    vendorIconHtml,
    refresh,
  };
})();
