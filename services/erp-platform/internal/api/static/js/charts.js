/* Interactive HiDPI Canvas Charts + Soil 3-Depth Profile Renderer */
window.ERPCharts = (() => {
  function setupCanvas(canvas, customHeight = 240) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(320, rect.width || 880);
    const h = customHeight || 240;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    return { ctx, w, h };
  }

  function renderForecastChart(canvas, tooltip, steps) {
    if (!canvas) return;
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);

    const pts = (steps || []).slice(0, 24).filter((s) => s.temperature != null);
    if (!pts.length) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "13px system-ui";
      ctx.fillText("No MET Norway hourly forecast steps available", 24, 42);
      return;
    }

    const temps = pts.map((s) => Number(s.temperature));
    const rains = pts.map((s) => Number(s.precipitation_1h ?? s.precipitation_6h ?? 0));
    const minT = Math.min(...temps) - 2;
    const maxT = Math.max(...temps) + 2;
    const maxR = Math.max(2, ...rains);
    const padL = 44, padR = 44, padT = 28, padB = 28;
    const cw = w - padL - padR, ch = h - padT - padB;

    // Grid lines
    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * ch;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      const val = maxT - (g / 4) * (maxT - minT);
      ctx.fillStyle = "#94a3b8"; ctx.font = "11px system-ui";
      ctx.fillText(`${val.toFixed(0)}°`, 8, y + 4);
    }

    // Rain bars
    const barW = Math.max(6, (cw / pts.length) * 0.45);
    pts.forEach((s, idx) => {
      const x = padL + (idx / Math.max(1, pts.length - 1)) * cw;
      const r = rains[idx];
      const barH = (r / maxR) * (ch * 0.6);
      ctx.fillStyle = "rgba(56, 189, 248, 0.35)";
      ctx.fillRect(x - barW / 2, padT + ch - barH, barW, barH);
    });

    // Temperature smooth line
    const coords = pts.map((s, idx) => ({
      x: padL + (idx / Math.max(1, pts.length - 1)) * cw,
      y: padT + ch - ((Number(s.temperature) - minT) / Math.max(0.1, maxT - minT)) * ch,
      s,
    }));

    ctx.strokeStyle = "#22c55e";
    ctx.lineWidth = 2.6;
    ctx.beginPath();
    coords.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.stroke();

    coords.forEach((p) => {
      ctx.fillStyle = "#22c55e";
      ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2); ctx.fill();
    });

    ctx.fillStyle = "#22c55e"; ctx.font = "12px system-ui";
    ctx.fillText("MET Norway Hourly Temp (°C)", padL, 16);
    ctx.fillStyle = "#38bdf8";
    ctx.fillText("Precipitation (mm)", padL + 190, 16);

    canvas.onmousemove = (ev) => {
      if (!tooltip) return;
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      let best = coords[0], bestDist = Infinity;
      coords.forEach((p) => {
        const d = Math.abs(p.x - mx);
        if (d < bestDist) { bestDist = d; best = p; }
      });
      if (bestDist > 36) { tooltip.style.display = "none"; return; }
      const st = best.s;
      tooltip.innerHTML = `
        <strong>${st.time_local || st.time_utc}</strong><br>
        Temp: <b>${Number(st.temperature).toFixed(1)}°C</b> (Feels ${st.feels_like != null ? Number(st.feels_like).toFixed(1) : "-"}°C)<br>
        Rain: <b>${Number(st.precipitation_1h ?? st.precipitation_6h ?? 0).toFixed(1)} mm</b> · RH: ${st.humidity ?? "-"}%
      `;
      tooltip.style.display = "block";
      tooltip.style.left = `${Math.min(rect.width - 190, Math.max(8, best.x + 10))}px`;
      tooltip.style.top = `${Math.max(8, best.y - 45)}px`;
    };
    canvas.onmouseleave = () => { if (tooltip) tooltip.style.display = "none"; };
  }

  function renderExchangeChart(canvas, tooltip, rows) {
    if (!canvas) return;
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const ordered = [...(rows || [])].reverse();
    if (!ordered.length) {
      ctx.fillStyle = "#94a3b8"; ctx.font = "13px system-ui";
      ctx.fillText("No tbncorp.weather exchange rows available", 24, 42);
      return;
    }

    const temps = ordered.map((r) => Number(r.temperature_avg ?? 0));
    const minT = Math.min(...temps) - 1, maxT = Math.max(...temps) + 1;
    const padL = 44, padR = 24, padT = 28, padB = 26;
    const cw = w - padL - padR, ch = h - padT - padB;

    const coords = ordered.map((r, idx) => ({
      x: padL + (idx / Math.max(1, ordered.length - 1)) * cw,
      y: padT + ch - ((Number(r.temperature_avg ?? minT) - minT) / Math.max(0.1, maxT - minT)) * ch,
      r,
    }));

    ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2.6;
    ctx.beginPath();
    coords.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.stroke();

    coords.forEach((p) => {
      ctx.fillStyle = "#38bdf8";
      ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2); ctx.fill();
    });

    ctx.fillStyle = "#38bdf8"; ctx.font = "12px system-ui";
    ctx.fillText(`tbncorp.weather Avg Temperature (${minT.toFixed(1)}°C .. ${maxT.toFixed(1)}°C)`, padL, 16);

    canvas.onmousemove = (ev) => {
      if (!tooltip) return;
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      let best = coords[0], bestDist = Infinity;
      coords.forEach((p) => { const d = Math.abs(p.x - mx); if (d < bestDist) { bestDist = d; best = p; } });
      if (bestDist > 40) { tooltip.style.display = "none"; return; }
      tooltip.innerHTML = `<strong>${best.r.code}</strong> · ${best.r.time}<br>Temp: <b>${best.r.temperature_avg}°C</b> · RH: <b>${best.r.humidity_avg}%</b>`;
      tooltip.style.display = "block";
      tooltip.style.left = `${Math.min(rect.width - 190, Math.max(8, best.x + 10))}px`;
      tooltip.style.top = `${Math.max(8, best.y - 36)}px`;
    };
    canvas.onmouseleave = () => { if (tooltip) tooltip.style.display = "none"; };
  }

  function renderSoilDepthHtml(readings) {
    const byDepth = {};
    (readings || []).forEach((r) => {
      if (!r.depth_level) return;
      if (!byDepth[r.depth_level]) byDepth[r.depth_level] = {};
      byDepth[r.depth_level][r.metric] = r;
    });
    const depths = Object.keys(byDepth).sort((a, b) => Number(a) - Number(b));
    if (!depths.length) return "";
    return `<div class="soil-depth-list">${depths.map((d) => {
      const m = byDepth[d];
      const moist = m.moisture ? Number(m.moisture.value) : 0;
      const temp = m.temperature ? Number(m.temperature.value).toFixed(1) : "-";
      const vic = m.vic ? Number(m.vic.value).toFixed(0) : null;
      const ph = m.ph ? Number(m.ph.value).toFixed(1) : null;
      const ec = m.ec ? Number(m.ec.value).toFixed(0) : null;
      const sal = m.salinity ? Number(m.salinity.value).toFixed(0) : null;
      const n = m.nitrogen ? Number(m.nitrogen.value).toFixed(0) : null;
      const p = m.phosphorus ? Number(m.phosphorus.value).toFixed(0) : null;
      const k = m.potassium ? Number(m.potassium.value).toFixed(0) : null;
      const pct = Math.min(100, Math.max(0, moist));
      const extras = [
        vic !== null ? `VIC ${vic}` : null,
        ph !== null ? `pH ${ph}` : null,
        ec !== null ? `EC ${ec} µS/cm` : null,
        sal !== null ? `Sal ${sal} ppm` : null,
        n !== null ? `N-P-K ${n}/${p ?? "-"}/${k ?? "-"} mg/kg` : null,
      ].filter(Boolean).join(" · ");
      return `<div class="soil-depth-row">
        <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
          <span><strong>Depth ${Number(d) * 10} cm</strong></span>
          <span class="tabular-nums"><strong>${moist.toFixed(1)}%</strong> · ${temp}°C${extras ? " · " + extras : ""}</span>
        </div>
        <div class="soil-bar-track"><div class="soil-bar-fill" style="width:${pct}%"></div></div>
      </div>`;
    }).join("")}</div>`;
  }

  function renderSoilNpkChart(canvas, tooltip, readings) {
    if (!canvas) return;
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);

    const byDepth = { 1: {}, 2: {}, 3: {} };
    (readings || []).forEach((r) => {
      if (r.depth_level && byDepth[r.depth_level]) {
        byDepth[r.depth_level][r.metric] = Number(r.value ?? 0);
      }
    });
    const depths = [1, 2, 3].filter((d) => Object.keys(byDepth[d]).length > 0);
    if (!depths.length) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "13px system-ui";
      ctx.fillText("No multi-depth soil N-P-K readings synced yet", 24, 42);
      return;
    }

    const metrics = [
      { key: "nitrogen", label: "N (Nitrogen)", color: "#38bdf8" },
      { key: "phosphorus", label: "P (Phosphorus)", color: "#22c55e" },
      { key: "potassium", label: "K (Potassium)", color: "#f59e0b" },
    ];
    let maxVal = 100;
    depths.forEach((d) => metrics.forEach((m) => { maxVal = Math.max(maxVal, byDepth[d][m.key] || 0); }));
    maxVal *= 1.15;

    const padL = 48, padR = 24, padT = 32, padB = 30;
    const cw = w - padL - padR, ch = h - padT - padB;
    const groupW = cw / depths.length;
    const barW = Math.min(44, (groupW - 36) / metrics.length);

    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * ch;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      ctx.fillStyle = "#94a3b8"; ctx.font = "11px system-ui";
      ctx.fillText(`${Math.round(maxVal * (1 - g / 4))}`, 6, y + 4);
    }

    const hitBoxes = [];
    depths.forEach((d, gi) => {
      const gx = padL + gi * groupW + (groupW - barW * metrics.length - 12) / 2;
      metrics.forEach((m, mi) => {
        const val = byDepth[d][m.key] || 0;
        const bh = (val / maxVal) * ch;
        const x = gx + mi * (barW + 6);
        const y = padT + ch - bh;
        ctx.fillStyle = m.color;
        ctx.fillRect(x, y, barW, bh);
        ctx.fillStyle = "#e2e8f0"; ctx.font = "10px system-ui";
        ctx.fillText(`${Math.round(val)}`, x + 4, Math.max(padT + 10, y - 4));
        hitBoxes.push({ x, y, w: barW, h: bh, depth: d * 10, label: m.label, val });
      });
      ctx.fillStyle = "#cbd5e1"; ctx.font = "12px system-ui";
      ctx.fillText(`Depth ${d * 10} cm`, padL + gi * groupW + groupW / 2 - 34, h - 8);
    });

    metrics.forEach((m, i) => {
      ctx.fillStyle = m.color;
      ctx.fillRect(padL + i * 130, 8, 10, 10);
      ctx.fillStyle = "#cbd5e1"; ctx.font = "11px system-ui";
      ctx.fillText(m.label + " mg/kg", padL + i * 130 + 14, 17);
    });

    canvas.onmousemove = (ev) => {
      if (!tooltip) return;
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      const hit = hitBoxes.find((b) => mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h);
      if (!hit) { tooltip.style.display = "none"; return; }
      tooltip.innerHTML = `<strong>${hit.depth} cm</strong> · ${hit.label}: <b>${hit.val} mg/kg</b>`;
      tooltip.style.display = "block";
      tooltip.style.left = `${Math.min(rect.width - 170, mx + 10)}px`;
      tooltip.style.top = `${Math.max(6, my - 34)}px`;
    };
    canvas.onmouseleave = () => { if (tooltip) tooltip.style.display = "none"; };
  }

  function renderRealtimeSeries(canvas, tooltip, opts = {}) {
    if (!canvas) return;
    const seriesList = Array.isArray(opts.series) ? opts.series.filter((s) => Array.isArray(s.points) && s.points.length > 0) : [];
    const { ctx, w, h } = setupCanvas(canvas, opts.height || 240);
    ctx.clearRect(0, 0, w, h);

    if (!seriesList.length) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "13px system-ui";
      ctx.fillText(opts.emptyText || "Waiting for live telemetry points...", 18, Math.max(40, h / 2));
      canvas.onmousemove = null;
      canvas.onmouseleave = null;
      return;
    }

    const palette = ["#38bdf8", "#22c55e", "#f59e0b", "#a78bfa", "#fb7185", "#14b8a6"];
    let minVal = Infinity;
    let maxVal = -Infinity;
    let maxLen = 0;

    seriesList.forEach((s) => {
      maxLen = Math.max(maxLen, s.points.length);
      s.points.forEach((pt) => {
        const v = Number(pt.v);
        if (isFinite(v)) {
          minVal = Math.min(minVal, v);
          maxVal = Math.max(maxVal, v);
        }
      });
    });

    if (!isFinite(minVal) || !isFinite(maxVal)) {
      minVal = 0;
      maxVal = 100;
    }
    if (Math.abs(maxVal - minVal) < 0.001) {
      minVal -= 1;
      maxVal += 1;
    } else {
      const spanPad = (maxVal - minVal) * 0.14;
      minVal -= spanPad;
      maxVal += spanPad;
    }

    const padL = 50, padR = 20, padT = 34, padB = 30;
    const cw = Math.max(40, w - padL - padR);
    const ch = Math.max(40, h - padT - padB);
    const yOf = (v) => padT + ch - ((v - minVal) / (maxVal - minVal)) * ch;

    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = "rgba(148,163,184,0.18)";
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * ch;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      const labelVal = maxVal - (g / 4) * (maxVal - minVal);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "11px system-ui";
      ctx.fillText(`${labelVal.toFixed(1)}`, 6, y + 4);
    }
    ctx.restore();

    const refLabels = seriesList[0].points.map((p) => p.t || "");
    const denom = Math.max(1, maxLen - 1);
    const xOf = (idx) => padL + (maxLen === 1 ? cw / 2 : (idx / denom) * cw);

    const stepX = Math.max(1, Math.ceil(refLabels.length / 6));
    refLabels.forEach((lbl, idx) => {
      if (idx % stepX === 0 || idx === refLabels.length - 1) {
        ctx.fillStyle = "#94a3b8";
        ctx.font = "10px system-ui";
        ctx.fillText(String(lbl).slice(-8), Math.max(padL, xOf(idx) - 22), h - 8);
      }
    });

    const isBar = opts.chartType === "bar";
    const smooth = opts.smooth !== false;
    const drawSmoothPath = (pts) => {
      pts.forEach((pt, idx) => {
        const px = xOf(idx);
        const py = yOf(Number(pt.v));
        if (idx === 0) {
          ctx.moveTo(px, py);
        } else if (smooth && idx > 0) {
          const prevX = xOf(idx - 1);
          const prevY = yOf(Number(pts[idx - 1].v));
          const cx = (prevX + px) / 2;
          ctx.bezierCurveTo(cx, prevY, cx, py, px, py);
        } else {
          ctx.lineTo(px, py);
        }
      });
    };

    const columns = [];
    seriesList.forEach((s, si) => {
      const color = s.color || palette[si % palette.length];
      const pts = s.points;
      if (!pts.length) return;

      if (isBar) {
        const barSlot = cw / Math.max(1, pts.length);
        const bw = Math.max(4, Math.min(20, barSlot * 0.62));
        const baseY = padT + ch;
        pts.forEach((pt, idx) => {
          const val = Number(pt.v);
          const px = xOf(idx);
          const py = yOf(val);
          const barH = Math.max(2, baseY - py);
          const grad = ctx.createLinearGradient(0, py, 0, baseY);
          grad.addColorStop(0, `${color}ee`);
          grad.addColorStop(1, `${color}33`);
          ctx.fillStyle = grad;
          ctx.fillRect(px - bw / 2, py, bw, barH);
          if (!columns[idx]) columns[idx] = { x: px, time: pt.t || `#${idx + 1}`, items: [] };
          columns[idx].items.push({ label: s.label, val, unit: s.unit || "", color });
        });
        return;
      }

      const grad = ctx.createLinearGradient(0, padT, 0, padT + ch);
      grad.addColorStop(0, `${color}48`);
      grad.addColorStop(1, `${color}02`);

      ctx.beginPath();
      drawSmoothPath(pts);
      if (pts.length > 1) {
        ctx.lineTo(xOf(pts.length - 1), padT + ch);
        ctx.lineTo(xOf(0), padT + ch);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();
      }

      ctx.strokeStyle = color;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      drawSmoothPath(pts);
      pts.forEach((pt, idx) => {
        const px = xOf(idx);
        if (!columns[idx]) columns[idx] = { x: px, time: pt.t || `#${idx + 1}`, items: [] };
        columns[idx].items.push({ label: s.label, val: Number(pt.v), unit: s.unit || "", color });
      });
      ctx.stroke();

      pts.forEach((pt, idx) => {
        const px = xOf(idx);
        const py = yOf(Number(pt.v));
        const isLast = idx === pts.length - 1;
        ctx.fillStyle = isLast ? "#ffffff" : color;
        ctx.beginPath();
        ctx.arc(px, py, isLast ? 4.2 : 2.3, 0, Math.PI * 2);
        ctx.fill();
        if (isLast) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });
    });

    let lx = padL;
    seriesList.slice(0, 5).forEach((s, si) => {
      const color = s.color || palette[si % palette.length];
      ctx.fillStyle = color;
      ctx.fillRect(lx, 10, 10, 10);
      ctx.fillStyle = "#cbd5e1";
      ctx.font = "11px system-ui";
      const txt = `${s.label}${s.unit ? ` (${s.unit})` : ""}`;
      ctx.fillText(txt, lx + 14, 19);
      lx += Math.min(180, txt.length * 6.5 + 26);
    });

    canvas.onmousemove = (ev) => {
      if (!tooltip || !columns.length) return;
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      let nearest = columns[0];
      let bestDist = Infinity;
      columns.forEach((col) => {
        const d = Math.abs(mx - col.x);
        if (d < bestDist) {
          bestDist = d;
          nearest = col;
        }
      });
      if (!nearest) return;
      tooltip.innerHTML = `<div style="font-weight:700;margin-bottom:4px;">${nearest.time}</div>` +
        nearest.items.map((it) =>
          `<div style="display:flex;justify-content:space-between;gap:12px;"><span style="color:${it.color}">● ${it.label}</span><b class="tabular-nums">${it.val.toFixed(2)} ${it.unit}</b></div>`
        ).join("");
      tooltip.style.display = "block";
      tooltip.style.left = `${Math.min(rect.width - 210, Math.max(8, mx + 12))}px`;
      tooltip.style.top = `${Math.max(8, my - 40)}px`;
    };
    canvas.onmouseleave = () => {
      if (tooltip) tooltip.style.display = "none";
    };
  }

  function renderComponentChartsGrid(containerEl, specs = []) {
    if (!containerEl) return;
    const validSpecs = Array.isArray(specs) ? specs.filter((sp) => Array.isArray(sp.series) && sp.series.some((s) => s.points?.length)) : [];
    if (!validSpecs.length) {
      containerEl.innerHTML = `<div class="kpi-sub">No active time-series components available for this view yet.</div>`;
      return;
    }

    containerEl.innerHTML = validSpecs.map((sp, idx) => {
      const allVals = [];
      let totalPts = 0;
      let latestStr = "-";
      sp.series.forEach((s, si) => {
        totalPts = Math.max(totalPts, s.points.length);
        s.points.forEach((p) => {
          const n = Number(p.v);
          if (isFinite(n)) allVals.push(n);
        });
        if (si === 0 && s.points.length) {
          const last = Number(s.points[s.points.length - 1].v);
          if (isFinite(last)) latestStr = `${last.toFixed(1)} ${sp.unit || s.unit || ""}`.trim();
        }
      });
      const minStr = allVals.length ? Math.min(...allVals).toFixed(1) : "-";
      const maxStr = allVals.length ? Math.max(...allVals).toFixed(1) : "-";
      const avgStr = allVals.length ? (allVals.reduce((a, b) => a + b, 0) / allVals.length).toFixed(1) : "-";
      const accent = sp.accentColor || sp.series[0]?.color || "#38bdf8";
      const iconHtml = window.ERPIcons ? window.ERPIcons.iconHtml(sp.icon || "activity", 16) : `<i data-lucide="activity"></i>`;

      return `<div class="component-chart-card" style="border-top: 3px solid ${accent};">
        <div class="component-chart-head">
          <div style="display:flex;align-items:center;gap:9px;min-width:0;">
            <span class="component-icon-pill" style="color:${accent};background:${accent}20;border-color:${accent}45;">${iconHtml}</span>
            <div style="min-width:0;">
              <div style="font-weight:600;font-size:0.88rem;line-height:1.25;">${sp.title}</div>
              ${sp.subtitle ? `<div class="kpi-sub" style="margin-top:1px;font-size:0.71rem;">${sp.subtitle}</div>` : ""}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            ${sp.badgeHtml || ""}
            <span class="badge badge-info tabular-nums" style="color:${accent};background:${accent}18;border-color:${accent}44;">Now: ${latestStr}</span>
          </div>
        </div>
        <div class="component-chart-stats tabular-nums">
          <span class="stat-pill">Min <strong>${minStr}</strong></span>
          <span class="stat-pill">Avg <strong>${avgStr}</strong></span>
          <span class="stat-pill">Max <strong>${maxStr}</strong></span>
          <span style="margin-left:auto;">${sp.series.length} series · ${totalPts} pts</span>
        </div>
        <div class="chart-wrap">
          <canvas id="${containerEl.id}_cv_${idx}" class="erp-canvas erp-canvas-sm"></canvas>
          <div id="${containerEl.id}_tt_${idx}" class="chart-tooltip"></div>
        </div>
      </div>`;
    }).join("");

    validSpecs.forEach((sp, idx) => {
      const cv = document.getElementById(`${containerEl.id}_cv_${idx}`);
      const tt = document.getElementById(`${containerEl.id}_tt_${idx}`);
      renderRealtimeSeries(cv, tt, { series: sp.series, height: 195, chartType: sp.chartType || "line", emptyText: sp.emptyText });
    });
    if (window.ERPIcons) window.ERPIcons.refresh(containerEl);
  }

  return { renderForecastChart, renderExchangeChart, renderSoilDepthHtml, renderSoilNpkChart, renderRealtimeSeries, renderComponentChartsGrid };
})();
