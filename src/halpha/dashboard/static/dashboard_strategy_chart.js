    (function () {
      const shared = window.HalphaDashboardShared;
      if (!shared) {
        throw new Error("Halpha dashboard shared helpers did not load.");
      }
      const {escapeHtml, formatNumber} = shared;
      const chartViews = new Map();

      function quoteAsset(symbol) {
        const value = String(symbol || "").trim();
        if (!value) return "n/a";
        for (const suffix of ["USDT", "USDC", "USD", "BTC", "ETH"]) {
          if (value.endsWith(suffix) && value.length > suffix.length) {
            return suffix;
          }
        }
        return value;
      }

      function strategyWindowLabel(vis, displayTimezone = "Asia/Shanghai") {
        const bars = Array.isArray(vis.bars) ? vis.bars : [];
        const timeframe = vis.timeframe || "timeframe n/a";
        if (!bars.length) return `${timeframe} / no candle window`;
        const first = bars[0]?.time;
        const last = bars[bars.length - 1]?.time;
        return `${timeframe} / ${bars.length} candles / ${formatTimestamp(first, displayTimezone)} to ${formatTimestamp(last, displayTimezone)}`;
      }

      function renderCandlestickSvg(selector, vis, options = {}) {
        const svg = document.querySelector(selector);
        if (!svg) return;
        const sourceBars = normalizeBars(vis.bars);
        const markers = normalizeMarkers(vis.markers);
        const dataKey = chartDataKey(vis, sourceBars, markers);
        if (options.resetView) {
          chartViews.delete(selector);
        }
        const view = chartView(selector, dataKey, sourceBars.length);
        const bars = sourceBars.slice(view.start, view.end + 1);
        if (!sourceBars.length) {
          svg.innerHTML = `<text x="490" y="235" fill="#9fb2c7" text-anchor="middle">No backtest visualization available</text>`;
          hideTooltip(svg);
          return;
        }
        const width = 980;
        const height = 470;
        const pad = {left: 44, right: 70, top: 28, bottom: 86};
        const max = Math.max(...bars.map((bar) => Number(bar.high) || 0));
        const min = Math.min(...bars.map((bar) => Number(bar.low) || 0));
        const priceY = (value) => pad.top + (max - value) / Math.max(1, max - min) * (height - pad.top - pad.bottom);
        const barStep = (width - pad.left - pad.right) / Math.max(1, bars.length - 1);
        const x = (index) => pad.left + index * barStep;
        const candleWidth = Math.max(3, Math.min(9, (width - pad.left - pad.right) / bars.length * 0.58));
        const maxVolume = Math.max(...bars.map((bar) => Number(bar.volume) || 0), 1);
        const markerByTime = groupMarkers(markers);
        const candleSvg = bars.map((bar, index) => {
          const open = Number(bar.open);
          const close = Number(bar.close);
          const high = Number(bar.high);
          const low = Number(bar.low);
          const up = close >= open;
          const color = up ? "#00a88f" : "#f04438";
          const cx = x(index);
          const yOpen = priceY(open);
          const yClose = priceY(close);
          const yHigh = priceY(high);
          const yLow = priceY(low);
          const bodyY = Math.min(yOpen, yClose);
          const bodyH = Math.max(2, Math.abs(yOpen - yClose));
          const volumeH = (Number(bar.volume) || 0) / maxVolume * 70;
          const volumeY = height - pad.bottom + 64 - volumeH;
          const candleMarkers = markerByTime.get(bar.time) || [];
          const markerSvg = candleMarkers.map((marker, markerIndex) => renderTradeMarker(
            cx,
            priceY(Number(marker.price) || close),
            marker,
            markerIndex,
          )).join("");
          const hitWidth = Math.max(1.5, Math.min(candleWidth + 8, barStep * 0.92));
          return `
            <g class="candle-node">
              <line x1="${cx}" x2="${cx}" y1="${yHigh}" y2="${yLow}" stroke="${color}" stroke-width="1.2"></line>
              <rect x="${cx - candleWidth / 2}" y="${bodyY}" width="${candleWidth}" height="${bodyH}" fill="${color}" rx="1"></rect>
              <rect x="${cx - candleWidth / 2}" y="${volumeY}" width="${candleWidth}" height="${volumeH}" fill="${color}" opacity="0.42"></rect>
              ${markerSvg}
              <rect class="candle-hit" x="${cx - hitWidth / 2}" y="${pad.top}" width="${hitWidth}" height="${height - pad.top - 20}" fill="transparent" data-candle-index="${index}" data-candle-x="${cx}" data-candle-time="${escapeHtml(bar.time)}" data-operation-count="${candleMarkers.length}"></rect>
            </g>`;
        }).join("");
        const grid = Array.from({length: 6}, (_, index) => {
          const y = pad.top + index * ((height - pad.top - pad.bottom) / 5);
          const price = max - index * ((max - min) / 5);
          return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" stroke="rgba(255,255,255,0.07)"></line><text x="${width - pad.right + 12}" y="${y + 4}" fill="#9fb2c7" font-size="12">${formatNumber(Math.round(price))}</text>`;
        }).join("");
        const ma50 = renderAverageLine(bars, x, priceY, 12, "#4f8cff");
        const ma200 = renderAverageLine(bars, x, priceY, 34, "#f59e0b");
        const viewportLabel = view.start > 0 || view.end < sourceBars.length - 1
          ? `${view.start + 1}-${view.end + 1} / ${sourceBars.length} candles`
          : `${sourceBars.length} candles`;
        const crosshair = `<line class="candle-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height - 22}" visibility="hidden"></line>`;
        svg.innerHTML = `${grid}${ma50}${ma200}${candleSvg}${crosshair}<text x="54" y="24" fill="#dbe7f3" font-size="13">${escapeHtml([vis.symbol, vis.timeframe].filter(Boolean).join(" - ") || "OHLCV")}</text><text x="54" y="44" fill="#9fb2c7" font-size="12">MA 12 close  MA 34 close</text><text x="54" y="64" fill="#9fb2c7" font-size="12">${escapeHtml(viewportLabel)}</text>`;
        wireCandleTooltip(svg, bars, markerByTime, options.displayTimezone);
        wireChartNavigation(svg, selector, vis, options, {
          plotLeft: pad.left,
          plotRight: width - pad.right,
          sourceBars,
        });
      }

      function renderAverageLine(bars, x, priceY, windowSize, color) {
        const points = [];
        bars.forEach((bar, index) => {
          const slice = bars.slice(Math.max(0, index - windowSize + 1), index + 1);
          const avg = slice.reduce((sum, item) => sum + Number(item.close || 0), 0) / slice.length;
          points.push(`${x(index)},${priceY(avg)}`);
        });
        return `<polyline points="${points.join(" ")}" fill="none" stroke="${color}" stroke-width="2" opacity="0.95"></polyline>`;
      }

      function renderTradeMarker(x, y, marker, markerIndex = 0) {
        const tone = markerTone(marker);
        const exit = tone === "exit" || tone === "short";
        const color = markerColor(tone);
        const labelText = marker.label || marker.side || marker.kind || (exit ? "Exit" : "Long");
        const offset = markerIndex * 25;
        const labelY = exit ? y - 24 - offset : y + 28 + offset;
        const labelWidth = Math.max(34, Math.min(72, String(labelText).length * 7 + 16));
        return `<g class="strategy-marker ${escapeHtml(tone)}"><line x1="${x}" x2="${x}" y1="${exit ? y - 4 : y + 4}" y2="${exit ? labelY + 10 : labelY - 10}" stroke="${color}" stroke-width="1.4"></line><rect x="${x - labelWidth / 2}" y="${labelY - 11}" width="${labelWidth}" height="22" rx="4" fill="${color}"></rect><text x="${x}" y="${labelY + 4}" fill="#fff" text-anchor="middle" font-size="11" font-weight="800">${escapeHtml(labelText)}</text></g>`;
      }

      function normalizeBars(value) {
        if (!Array.isArray(value)) return [];
        return value
          .map((bar) => ({
            time: bar?.time || bar?.open_time,
            open: bar?.open,
            high: bar?.high,
            low: bar?.low,
            close: bar?.close,
            volume: bar?.volume,
          }))
          .filter((bar) => bar.time);
      }

      function normalizeMarkers(value) {
        if (!Array.isArray(value)) return [];
        return value.filter((marker) => marker && marker.time);
      }

      function groupMarkers(markers) {
        const groups = new Map();
        markers.forEach((marker) => {
          const time = String(marker.time || "");
          if (!time) return;
          if (!groups.has(time)) groups.set(time, []);
          groups.get(time).push(marker);
        });
        return groups;
      }

      function chartDataKey(vis, bars, markers) {
        const first = bars[0]?.time || "";
        const last = bars[bars.length - 1]?.time || "";
        return [
          vis.chart_type || "candlestick",
          vis.strategy_name || "",
          vis.source || "",
          vis.symbol || "",
          vis.timeframe || "",
          first,
          last,
          bars.length,
          markers.length,
        ].join("|");
      }

      function chartView(selector, key, totalBars) {
        let view = chartViews.get(selector);
        if (!view || view.key !== key || view.end >= totalBars) {
          view = {key, start: 0, end: Math.max(0, totalBars - 1), drag: null};
          chartViews.set(selector, view);
        }
        return view;
      }

      function resetCandlestickView(selector) {
        chartViews.delete(selector);
      }

      function wireCandleTooltip(svg, bars, markerByTime, displayTimezone) {
        const tooltip = ensureTooltip(svg);
        svg.querySelectorAll(".candle-hit").forEach((node) => {
          node.addEventListener("mouseenter", () => {
            showCandleCrosshair(svg, node.dataset.candleX);
          });
          node.addEventListener("mousemove", (event) => {
            const bar = bars[Number(node.dataset.candleIndex)];
            if (!bar) return;
            const markers = markerByTime.get(bar.time) || [];
            showCandleCrosshair(svg, node.dataset.candleX);
            showTooltip(svg, tooltip, event, candleTooltipHtml(bar, markers, displayTimezone));
          });
          node.addEventListener("mouseleave", () => hideChartHover(svg));
        });
        svg.addEventListener("mouseleave", () => hideChartHover(svg));
      }

      function showCandleCrosshair(svg, x) {
        const crosshair = svg?.querySelector(".candle-crosshair");
        const number = Number(x);
        if (!crosshair || !Number.isFinite(number)) return;
        crosshair.setAttribute("x1", String(number));
        crosshair.setAttribute("x2", String(number));
        crosshair.setAttribute("visibility", "visible");
      }

      function hideCandleCrosshair(svg) {
        const crosshair = svg?.querySelector(".candle-crosshair");
        if (crosshair) crosshair.setAttribute("visibility", "hidden");
      }

      function hideChartHover(svg) {
        hideTooltip(svg);
        hideCandleCrosshair(svg);
      }

      function candleTooltipHtml(bar, markers, displayTimezone) {
        const markerHtml = markers.length
          ? `<div class="chart-tooltip-section"><strong>Operations</strong>${markers.map((marker) => `
            <div class="chart-tooltip-op ${markerClass(marker)}">
              <span>${escapeHtml(marker.label || marker.kind || "operation")}</span>
              <span>${escapeHtml(formatPrice(marker.price))}${marker.position !== undefined ? ` / pos ${escapeHtml(formatPrice(marker.position))}` : ""}</span>
            </div>
            ${markerDetailRows(marker)}`).join("")}</div>`
          : "";
        return `
          <div class="chart-tooltip-title">${escapeHtml(formatTimestamp(bar.time, displayTimezone))}</div>
          <div class="chart-tooltip-grid">
            <span>Open</span><strong>${escapeHtml(formatPrice(bar.open))}</strong>
            <span>High</span><strong>${escapeHtml(formatPrice(bar.high))}</strong>
            <span>Low</span><strong>${escapeHtml(formatPrice(bar.low))}</strong>
            <span>Close</span><strong>${escapeHtml(formatPrice(bar.close))}</strong>
            <span>Volume</span><strong>${escapeHtml(formatPrice(bar.volume))}</strong>
          </div>
          ${markerHtml}`;
      }

      function markerClass(marker) {
        return markerTone(marker);
      }

      function markerTone(marker) {
        const text = `${marker.kind || ""} ${marker.label || ""} ${marker.side || ""}`.toLowerCase();
        if (text.includes("funding")) return "funding";
        if (text.includes("event")) return "event";
        if (text.includes("multi") || text.includes("leg")) return "multi-leg";
        if (text.includes("exit") || text.includes("close") || text.includes("sell")) return "exit";
        if (text.includes("short")) return "short";
        if (text.includes("long") || text.includes("buy") || text.includes("entry")) return "entry";
        return "entry";
      }

      function markerColor(tone) {
        if (tone === "exit") return "#f04438";
        if (tone === "short") return "#f97316";
        if (tone === "event") return "#8b5cf6";
        if (tone === "funding") return "#0ea5e9";
        if (tone === "multi-leg") return "#64748b";
        return "#00a88f";
      }

      function markerDetailRows(marker) {
        const rows = [
          ["Side", marker.side],
          ["Exposure", marker.exposure],
          ["Execution", marker.execution_timing],
          ["Cost", marker.cost],
          ["Funding", marker.funding],
          ["Source", marker.source_ref],
        ].filter(([, value]) => value !== undefined && value !== null && value !== "");
        const warnings = Array.isArray(marker.warnings) ? marker.warnings.filter(Boolean) : [];
        if (!rows.length && !warnings.length) return "";
        return `<div class="chart-tooltip-op-detail">
          ${rows.map(([name, value]) => `<span>${escapeHtml(name)}</span><strong>${escapeHtml(formatPrice(value))}</strong>`).join("")}
          ${warnings.map((warning) => `<span>Warning</span><strong>${escapeHtml(warning)}</strong>`).join("")}
        </div>`;
      }

      function ensureTooltip(svg) {
        const parent = svg.parentElement;
        let tooltip = parent?.querySelector(".chart-tooltip");
        if (!tooltip && parent) {
          tooltip = document.createElement("div");
          tooltip.className = "chart-tooltip hidden";
          parent.appendChild(tooltip);
        }
        return tooltip;
      }

      function showTooltip(svg, tooltip, event, html) {
        if (!tooltip) return;
        const rect = svg.parentElement.getBoundingClientRect();
        tooltip.innerHTML = html;
        tooltip.classList.remove("hidden");
        const width = tooltip.offsetWidth || 230;
        const height = tooltip.offsetHeight || 160;
        const x = Math.min(Math.max(10, event.clientX - rect.left + 14), Math.max(10, rect.width - width - 10));
        const y = Math.min(Math.max(10, event.clientY - rect.top + 14), Math.max(10, rect.height - height - 10));
        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
      }

      function hideTooltip(svg) {
        const tooltip = svg?.parentElement?.querySelector(".chart-tooltip");
        if (tooltip) tooltip.classList.add("hidden");
      }

      function wireChartNavigation(svg, selector, vis, options, geometry) {
        const totalBars = geometry.sourceBars.length;
        svg.classList.toggle("is-draggable", totalBars > 1);
        if (totalBars <= 1) return;
        svg.onwheel = (event) => {
          event.preventDefault();
          const view = chartViews.get(selector);
          if (!view) return;
          const rect = svg.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)));
          const visible = view.end - view.start + 1;
          const nextVisible = event.deltaY < 0
            ? Math.max(8, Math.round(visible * 0.74))
            : Math.min(totalBars, Math.round(visible * 1.36));
          if (nextVisible === visible) return;
          const center = view.start + Math.round((visible - 1) * ratio);
          const start = Math.round(center - (nextVisible - 1) * ratio);
          setViewport(selector, start, start + nextVisible - 1, totalBars);
          renderCandlestickSvg(selector, vis, options);
        };
        svg.ondblclick = () => {
          resetCandlestickView(selector);
          renderCandlestickSvg(selector, vis, options);
        };
        svg.onpointerdown = (event) => {
          if (event.button !== 0) return;
          const view = chartViews.get(selector);
          if (!view) return;
          view.drag = {
            clientX: event.clientX,
            start: view.start,
            end: view.end,
            lastDeltaBars: 0,
            renderFrame: 0,
          };
          svg.classList.add("dragging");
          svg.setPointerCapture?.(event.pointerId);
        };
        svg.onpointermove = (event) => {
          const view = chartViews.get(selector);
          const drag = view?.drag;
          if (!drag) return;
          const rect = svg.getBoundingClientRect();
          const visible = drag.end - drag.start + 1;
          const pxPerBar = Math.max(1, rect.width / Math.max(1, visible));
          const deltaBars = Math.round((drag.clientX - event.clientX) / pxPerBar);
          if (deltaBars === drag.lastDeltaBars) return;
          drag.lastDeltaBars = deltaBars;
          setViewport(selector, drag.start + deltaBars, drag.end + deltaBars, totalBars);
          if (!drag.renderFrame) {
            drag.renderFrame = requestAnimationFrame(() => {
              drag.renderFrame = 0;
              renderCandlestickSvg(selector, vis, options);
            });
          }
        };
        svg.onpointerup = (event) => {
          const view = chartViews.get(selector);
          const drag = view?.drag;
          if (!drag) return;
          const rect = svg.getBoundingClientRect();
          const visible = drag.end - drag.start + 1;
          const pxPerBar = Math.max(1, rect.width / Math.max(1, visible));
          const deltaBars = Math.round((drag.clientX - event.clientX) / pxPerBar);
          setViewport(selector, drag.start + deltaBars, drag.end + deltaBars, totalBars);
          if (drag.renderFrame) {
            cancelAnimationFrame(drag.renderFrame);
          }
          view.drag = null;
          svg.classList.remove("dragging");
          renderCandlestickSvg(selector, vis, options);
        };
        svg.onpointercancel = () => {
          const view = chartViews.get(selector);
          if (view?.drag?.renderFrame) {
            cancelAnimationFrame(view.drag.renderFrame);
          }
          if (view) view.drag = null;
          svg.classList.remove("dragging");
        };
      }

      function setViewport(selector, start, end, totalBars) {
        const view = chartViews.get(selector);
        if (!view) return;
        const size = Math.max(1, end - start + 1);
        const maxStart = Math.max(0, totalBars - size);
        const nextStart = Math.min(Math.max(0, start), maxStart);
        view.start = nextStart;
        view.end = Math.min(totalBars - 1, nextStart + size - 1);
      }

      function formatPrice(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return String(value ?? "n/a");
        return number.toLocaleString(undefined, {maximumFractionDigits: 8});
      }

      function formatTimestamp(value, displayTimezone) {
        return shared.formatTimestamp(value, displayTimezone);
      }

      window.HalphaDashboardStrategyChart = {
        quoteAsset,
        resetCandlestickView,
        renderCandlestickSvg,
        strategyWindowLabel,
      };
    })();
