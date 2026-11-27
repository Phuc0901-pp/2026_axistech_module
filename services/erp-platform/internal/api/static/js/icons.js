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

    if (s.includes("thunder")) {
      return {
        icon: "cloud-lightning",
        label: "Dông sét",
        color: "#c084fc",
        bg: "rgba(192, 132, 252, 0.16)",
        border: "rgba(192, 132, 252, 0.42)",
      };
    }
    if (s.includes("heavyrain")) {
      return {
        icon: "cloud-rain-wind",
        label: "Mưa lớn",
        color: "#0ea5e9",
        bg: "rgba(14, 165, 233, 0.16)",
        border: "rgba(14, 165, 233, 0.42)",
      };
    }
    if (s.includes("rainshowers")) {
      return {
        icon: "cloud-rain-wind",
        label: "Mưa rào",
        color: "#0ea5e9",
        bg: "rgba(14, 165, 233, 0.16)",
        border: "rgba(14, 165, 233, 0.42)",
      };
    }
    if (s.includes("lightrain") || s.includes("drizzle")) {
      return {
        icon: "cloud-rain",
        label: "Mưa nhẹ",
        color: "#38bdf8",
        bg: "rgba(56, 189, 248, 0.16)",
        border: "rgba(56, 189, 248, 0.40)",
      };
    }
    if (s.includes("rain") || s.includes("sleet")) {
      return {
        icon: "cloud-rain",
        label: "Có mưa",
        color: "#38bdf8",
        bg: "rgba(56, 189, 248, 0.16)",
        border: "rgba(56, 189, 248, 0.40)",
      };
    }
    if (s.includes("snow")) {
      return {
        icon: "snowflake",
        label: "Tuyết rơi",
        color: "#67e8f9",
        bg: "rgba(103, 232, 249, 0.16)",
        border: "rgba(103, 232, 249, 0.42)",
      };
    }
    if (s.includes("fog")) {
      return {
        icon: "cloud-fog",
        label: "Sương mù",
        color: "#94a3b8",
        bg: "rgba(148, 163, 184, 0.16)",
        border: "rgba(148, 163, 184, 0.40)",
      };
    }
    if (isNight && (s.includes("clear") || s.includes("fair"))) {
      return {
        icon: "moon-star",
        label: "Đêm quang",
        color: "#818cf8",
        bg: "rgba(129, 140, 248, 0.16)",
        border: "rgba(129, 140, 248, 0.40)",
      };
    }
    if (isNight && s.includes("partly")) {
      return {
        icon: "cloud-moon",
        label: "Đêm ít mây",
        color: "#a78bfa",
        bg: "rgba(167, 139, 250, 0.16)",
        border: "rgba(167, 139, 250, 0.40)",
      };
    }
    if (s.includes("clear") || s.includes("fair") || s.includes("sun")) {
      return {
        icon: "sun",
        label: "Quang mây",
        color: "#f59e0b",
        bg: "rgba(245, 158, 11, 0.16)",
        border: "rgba(245, 158, 11, 0.42)",
      };
    }
    if (s.includes("partly")) {
      return {
        icon: "cloud-sun",
        label: "Ít mây",
        color: "#fbbf24",
        bg: "rgba(251, 191, 36, 0.16)",
        border: "rgba(251, 191, 36, 0.40)",
      };
    }
    if (s.includes("cloud")) {
      return {
        icon: "cloud",
        label: "Nhiều mây",
        color: "#64748b",
        bg: "rgba(100, 116, 139, 0.16)",
        border: "rgba(100, 116, 139, 0.40)",
      };
    }
    return {
      icon: "cloud-sun",
      label: raw || "Ổn định",
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

  const METRIC_META = {
    temperature: { label: "Nhiệt độ không khí", tooltip: "Nhiệt độ môi trường không khí" },
    air_temperature: { label: "Nhiệt độ không khí", tooltip: "Nhiệt độ môi trường không khí" },
    feels_like: { label: "Nhiệt độ cảm nhận", tooltip: "Nhiệt độ cảm nhận thực tế" },
    atmos_pressure: { label: "Áp suất khí quyển", tooltip: "Áp suất khí quyển tại trạm" },
    pressure: { label: "Áp suất khí quyển", tooltip: "Áp suất khí quyển tại trạm" },
    msl_pressure: { label: "Áp suất mực nước biển", tooltip: "Áp suất quy chuẩn mực nước biển (MSLP)" },
    humidity: { label: "Độ ẩm tương đối", tooltip: "Độ ẩm không khí tương đối" },
    relative_humidity: { label: "Độ ẩm tương đối", tooltip: "Độ ẩm không khí tương đối" },
    delta_t: { label: "Chỉ số Delta-T (Bốc hơi)", tooltip: "Chênh lệch nhiệt độ Delta-T (Đánh giá mức bốc hơi)" },
    dew_point: { label: "Điểm sương", tooltip: "Nhiệt độ điểm sương" },
    wind_speed: { label: "Tốc độ gió TB", tooltip: "Tốc độ gió trung bình" },
    wind_speed_min: { label: "Tốc độ gió nhỏ nhất", tooltip: "Tốc độ gió cực tiểu" },
    wind_speed_max: { label: "Tốc độ gió lớn nhất", tooltip: "Tốc độ gió cực đại" },
    wind_gust: { label: "Gió giật", tooltip: "Tốc độ gió giật cực đại" },
    wind_direction: { label: "Hướng gió", tooltip: "Hướng gió thổi" },
    wind_dir_var: { label: "Độ biến thiên hướng gió", tooltip: "Độ lệch chuẩn hướng gió" },
    solar_radiation: { label: "Bức xạ mặt trời", tooltip: "Cường độ bức xạ mặt trời" },
    uv_index: { label: "Chỉ số UV", tooltip: "Chỉ số tia cực tím (UV)" },
    rainfall: { label: "Lượng mưa (1 giờ)", tooltip: "Lượng mưa trong 1 giờ" },
    precipitation_1h: { label: "Lượng mưa (1 giờ)", tooltip: "Lượng mưa trong 1 giờ" },
    precipitation_6h: { label: "Lượng mưa (6 giờ)", tooltip: "Lượng mưa dự báo trong 6 giờ" },
    rainfall_total: { label: "Lượng mưa tích lũy", tooltip: "Tổng lượng mưa tích lũy" },
    rainfall_last_24hrs: { label: "Lượng mưa 24 giờ qua", tooltip: "Lượng mưa trong 24 giờ gần nhất" },
    cloud_cover: { label: "Độ che phủ mây", tooltip: "Tỷ lệ mây che phủ bầu trời" },
    battery: { label: "Nguồn pin", tooltip: "Điện áp / Trạng thái pin thiết bị" },
    battery_pct: { label: "Mức pin", tooltip: "Trạng thái / Dung lượng pin thiết bị" },
    battery_level: { label: "Mức pin", tooltip: "Trạng thái / Dung lượng pin thiết bị" },
    battery_voltage: { label: "Điện áp pin", tooltip: "Điện áp nguồn pin thiết bị" },
    solar_voltage: { label: "Điện áp pin mặt trời", tooltip: "Điện áp tấm sạc năng lượng mặt trời" },
    signal_strength_dbm: { label: "Cường độ tín hiệu (RSSI)", tooltip: "Cường độ tín hiệu thu sóng (RSSI)" },
    rssi: { label: "Cường độ tín hiệu (RSSI)", tooltip: "Cường độ tín hiệu thu sóng (RSSI)" },
    moisture: { label: "Độ ẩm đất", tooltip: "Độ ẩm thể tích tầng đất" },
    vic: { label: "Độ dẫn điện đất (VIC)", tooltip: "Chỉ số độ dẫn điện / ion thể tích đất (VIC)" },
    soil_temperature: { label: "Nhiệt độ đất", tooltip: "Nhiệt độ tầng đất đo từ cảm biến" },
    water_volume: { label: "Lưu lượng nước", tooltip: "Lưu lượng dòng chảy qua cảm biến" },
    cumulative_water: { label: "Tổng lượng nước tích lũy", tooltip: "Tổng thể tích nước tích lũy qua trạm" },
    water_level: { label: "Mực nước", tooltip: "Cao độ / Mực nước đo được" },
    ph: { label: "Độ pH đất", tooltip: "Chỉ số độ pH đất / nước" },
    ec: { label: "Độ dẫn điện (EC)", tooltip: "Độ dẫn điện dung dịch đất (EC)" },
    salinity: { label: "Độ mặn đất", tooltip: "Nồng độ muối / Độ mặn trong đất" },
    nitrogen: { label: "Đạm (N)", tooltip: "Hàm lượng Đạm (Nitơ) khả dụng" },
    phosphorus: { label: "Lân (P)", tooltip: "Hàm lượng Lân (Phốt pho) khả dụng" },
    potassium: { label: "Kali (K)", tooltip: "Hàm lượng Kali khả dụng" },
    weather_symbol: { label: "Biểu tượng thời tiết", tooltip: "Trạng thái thời tiết tổng hợp" },
  };

  function getMetricMeta(rawKey, depthLevel = 0) {
    const raw = String(rawKey || "").trim();
    if (!raw) return { key: "", label: "-", tooltip: "" };
    let normalized = raw
      .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
      .toLowerCase()
      .replace(/[\s-]+/g, "_");
    let depth = Number(depthLevel) || 0;
    const depthMatch = normalized.match(/^(.*)_d(\d+)$/);
    if (depthMatch) {
      normalized = depthMatch[1];
      if (!depth) depth = Number(depthMatch[2]) || 0;
    }
    const base = METRIC_META[normalized] || {
      label: raw.replace(/_/g, " "),
      tooltip: raw.replace(/_/g, " "),
    };
    if (depth > 0) {
      const depthCmMap = { 1: "10 cm", 2: "20 cm", 3: "30 cm", 4: "40 cm", 5: "50 cm", 6: "60 cm" };
      const depthTag = depthCmMap[depth] || `Tầng ${depth}`;
      if (normalized === "temperature" || normalized === "air_temperature" || normalized === "soil_temperature") {
        return {
          key: normalized,
          label: `Nhiệt độ đất (${depthTag})`,
          tooltip: `Nhiệt độ tầng đất ở độ sâu ${depthTag}`,
        };
      }
      return {
        key: normalized,
        label: `${base.label} (${depthTag})`,
        tooltip: `${base.tooltip} ở độ sâu ${depthTag}`,
      };
    }
    return { key: normalized, label: base.label, tooltip: base.tooltip };
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
    getMetricMeta,
    iconHtml,
    deviceIconHtml,
    assetIconHtml,
    vendorIconHtml,
    refresh,
  };
})();
