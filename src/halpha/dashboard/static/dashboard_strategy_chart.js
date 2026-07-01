    (function () {
      const shared = window.HalphaDashboardShared;
      if (!shared) {
        throw new Error("Halpha dashboard shared helpers did not load.");
      }
      const {escapeHtml, formatNumber, pnlColors} = shared;
      const chartViews = new Map();
      const EQUITY_CHART_MAX_POINTS = 140;
      const EQUITY_CHART_MIN_VISIBLE_POINTS = 12;

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
          svg.innerHTML = `<text x="490" y="235" fill="#6F7682" text-anchor="middle">No backtest visualization available</text>`;
          hideTooltip(svg);
          return;
        }
        const width = 980;
        const height = 470;
        const pad = {left: 44, right: 70, top: 28, bottom: 86};
        const colors = pnlColors(options.pnlColorScheme);
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
          const color = up ? colors.up : colors.down;
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
            colors,
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
          return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" stroke="#E1E5EC"></line><text x="${width - pad.right + 12}" y="${y + 4}" fill="#6F7682" font-size="12">${formatNumber(Math.round(price))}</text>`;
        }).join("");
        const ma50 = renderAverageLine(sourceBars, view.start, view.end, x, priceY, 12, "#4f8cff");
        const ma200 = renderAverageLine(sourceBars, view.start, view.end, x, priceY, 34, "#f59e0b");
        const viewportLabel = view.start > 0 || view.end < sourceBars.length - 1
          ? `${view.start + 1}-${view.end + 1} / ${sourceBars.length} candles`
          : `${sourceBars.length} candles`;
        const crosshair = `<line class="candle-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height - 22}" visibility="hidden"></line>`;
        svg.innerHTML = `${grid}${ma50}${ma200}${candleSvg}${crosshair}<text x="54" y="24" fill="#111827" font-size="13">${escapeHtml([vis.symbol, vis.timeframe].filter(Boolean).join(" - ") || "OHLCV")}</text><text x="54" y="44" fill="#6F7682" font-size="12">MA 12 close  MA 34 close</text><text x="54" y="64" fill="#6F7682" font-size="12">${escapeHtml(viewportLabel)}</text>`;
        wireCandleTooltip(svg, bars, markerByTime, options.displayTimezone);
        wireChartNavigation(svg, selector, vis, options, {
          plotLeft: pad.left,
          plotRight: width - pad.right,
          sourceBars,
        });
      }

      function renderEquityCurveSvg(selector, curve, options = {}) {
        const svg = document.querySelector(selector);
        if (!svg) return;
        const sourcePoints = normalizeEquityCurve(curve);
        const dataKey = equityChartDataKey(sourcePoints);
        if (options.resetView) {
          chartViews.delete(selector);
        }
        if (!sourcePoints.length) {
          svg.innerHTML = `<text x="450" y="112" fill="#6F7682" text-anchor="middle">No equity curve is available</text>`;
          hideTooltip(svg);
          return;
        }
        const view = chartView(selector, dataKey, sourcePoints.length);
        const visiblePoints = sourcePoints.slice(view.start, view.end + 1);
        const sampledPoints = aggregateEquityPoints(visiblePoints, EQUITY_CHART_MAX_POINTS);
        const width = 900;
        const height = 240;
        const pad = {left: 62, right: 28, top: 22, bottom: 42};
        const colors = pnlColors(options.pnlColorScheme);
        const values = visiblePoints.map((point) => point.value);
        const rawMin = Math.min(...values);
        const rawMax = Math.max(...values);
        const range = Math.max(0.000001, rawMax - rawMin);
        const min = rawMin - range * 0.08;
        const max = rawMax + range * 0.08;
        const baseline = visiblePoints[0]?.value ?? sampledPoints[0]?.value ?? 0;
        const plotWidth = width - pad.left - pad.right;
        const plotHeight = height - pad.top - pad.bottom;
        const pointX = (point) => {
          const ratio = visiblePoints.length <= 1
            ? 0.5
            : (point.index - view.start) / Math.max(1, visiblePoints.length - 1);
          return pad.left + ratio * plotWidth;
        };
        const pointY = (value) => pad.top + (max - value) / Math.max(0.000001, max - min) * plotHeight;
        const plotted = sampledPoints.map((point) => ({
          ...point,
          x: Number(pointX(point).toFixed(2)),
          y: Number(pointY(point.value).toFixed(2)),
        }));
        const baselineY = Number(pointY(baseline).toFixed(2));
        const grid = renderEquityGrid({
          width,
          height,
          pad,
          min,
          max,
          baselineY,
          visiblePoints,
          pointX,
          displayTimezone: options.displayTimezone,
        });
        const lineSegments = renderEquitySegments(plotted, baseline, baselineY, colors);
        const hitNodes = plotted.map((point) => {
          const hitWidth = Math.max(7, Math.min(22, plotWidth / Math.max(1, plotted.length)));
          return `<circle class="equity-chart-hit" cx="${point.x}" cy="${point.y}" r="${hitWidth / 2}" fill="transparent" data-equity-index="${point.index}" data-equity-x="${point.x}" data-equity-y="${point.y}"></circle>`;
        }).join("");
        const visibleLabel = view.start > 0 || view.end < sourcePoints.length - 1
          ? `${view.start + 1}-${view.end + 1} / ${sourcePoints.length} points`
          : `${sourcePoints.length} points`;
        const crosshair = `<line class="equity-chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height - pad.bottom}" visibility="hidden"></line>`;
        svg.innerHTML = `
          ${grid}
          ${lineSegments}
          ${hitNodes}
          ${crosshair}
          <text class="equity-chart-status" x="${pad.left}" y="${height - 12}" fill="#6F7682" font-size="12">${escapeHtml(visibleLabel)}</text>`;
        wireEquityTooltip(svg, sourcePoints, baseline, options.displayTimezone);
        wireEquityChartNavigation(svg, selector, curve, options, sourcePoints.length);
      }

      function renderDrawdownCurveSvg(selector, curve, options = {}) {
        const svg = document.querySelector(selector);
        if (!svg) return;
        const sourcePoints = drawdownPointsFromEquityCurve(curve);
        const dataKey = drawdownChartDataKey(sourcePoints);
        if (options.resetView) {
          chartViews.delete(selector);
        }
        if (!sourcePoints.length) {
          svg.innerHTML = `<text x="450" y="112" fill="#6F7682" text-anchor="middle">No drawdown data is available</text>`;
          hideTooltip(svg);
          return;
        }
        const view = chartView(selector, dataKey, sourcePoints.length);
        const visiblePoints = sourcePoints.slice(view.start, view.end + 1);
        const sampledPoints = aggregateDrawdownPoints(visiblePoints, EQUITY_CHART_MAX_POINTS);
        const width = 900;
        const height = 240;
        const pad = {left: 62, right: 28, top: 22, bottom: 48};
        const values = visiblePoints.map((point) => point.value);
        const rawMin = Math.min(...values, 0);
        const rawMax = Math.max(...values, 0);
        const range = Math.max(0.000001, rawMax - rawMin);
        const min = rawMin - range * 0.1;
        const max = Math.max(0, rawMax + range * 0.04);
        const plotWidth = width - pad.left - pad.right;
        const plotHeight = height - pad.top - pad.bottom;
        const pointX = (point) => {
          const ratio = visiblePoints.length <= 1
            ? 0.5
            : (point.index - view.start) / Math.max(1, visiblePoints.length - 1);
          return pad.left + ratio * plotWidth;
        };
        const pointY = (value) => pad.top + (max - value) / Math.max(0.000001, max - min) * plotHeight;
        const plotted = sampledPoints.map((point) => ({
          ...point,
          x: Number(pointX(point).toFixed(2)),
          y: Number(pointY(point.value).toFixed(2)),
        }));
        const zeroY = Number(pointY(0).toFixed(2));
        const worstPoint = sourcePoints.reduce((worst, point) => (point.value < worst.value ? point : worst), sourcePoints[0]);
        const visibleWorst = worstPoint && worstPoint.index >= view.start && worstPoint.index <= view.end ? {
          ...worstPoint,
          x: Number(pointX(worstPoint).toFixed(2)),
          y: Number(pointY(worstPoint.value).toFixed(2)),
        } : null;
        const grid = renderDrawdownGrid({
          width,
          height,
          pad,
          min,
          max,
          zeroY,
          visiblePoints,
          pointX,
          displayTimezone: options.displayTimezone,
        });
        const line = drawdownLinePath(plotted);
        const hitNodes = plotted.map((point) => {
          const hitWidth = Math.max(7, Math.min(22, plotWidth / Math.max(1, plotted.length)));
          return `<circle class="drawdown-chart-hit" cx="${point.x}" cy="${point.y}" r="${hitWidth / 2}" fill="transparent" data-drawdown-index="${point.index}" data-drawdown-x="${point.x}" data-drawdown-y="${point.y}"></circle>`;
        }).join("");
        const worstMarker = visibleWorst ? renderDrawdownWorstMarker(visibleWorst) : "";
        const visibleLabel = view.start > 0 || view.end < sourcePoints.length - 1
          ? `${view.start + 1}-${view.end + 1} / ${sourcePoints.length} points`
          : `${sourcePoints.length} points`;
        const crosshair = `<line class="drawdown-chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height - pad.bottom}" visibility="hidden"></line>`;
        svg.innerHTML = `
          ${grid}
          ${line}
          ${hitNodes}
          ${worstMarker}
          ${crosshair}
          <text class="drawdown-chart-status" x="${pad.left}" y="${height - 10}" fill="#6F7682" font-size="12">${escapeHtml(visibleLabel)}</text>`;
        wireDrawdownTooltip(svg, sourcePoints, worstPoint, options.displayTimezone);
        wireDrawdownChartNavigation(svg, selector, curve, options, sourcePoints.length);
      }

      function resetEquityCurveView(selector) {
        chartViews.delete(selector);
      }

      function resetDrawdownCurveView(selector) {
        chartViews.delete(selector);
      }

      function normalizeEquityCurve(curve) {
        if (!Array.isArray(curve)) return [];
        return curve
          .map((point, index) => {
            const value = Number(point?.net_equity ?? point?.equity ?? point?.value ?? point);
            return {
              index,
              time: point?.time || point?.timestamp || point?.open_time || "",
              value,
            };
          })
          .filter((point) => Number.isFinite(point.value));
      }

      function equityChartDataKey(points) {
        const first = points[0] || {};
        const last = points[points.length - 1] || {};
        return [
          "equity",
          first.time || "",
          last.time || "",
          first.value ?? "",
          last.value ?? "",
          points.length,
        ].join("|");
      }

      function drawdownChartDataKey(points) {
        const first = points[0] || {};
        const last = points[points.length - 1] || {};
        return [
          "drawdown",
          first.time || "",
          last.time || "",
          first.value ?? "",
          last.value ?? "",
          points.length,
        ].join("|");
      }

      function aggregateEquityPoints(points, maxPoints = EQUITY_CHART_MAX_POINTS) {
        if (points.length <= maxPoints) return points;
        const baseline = points[0]?.value ?? 0;
        return aggregateExtremePoints(points, maxPoints, baseline);
      }

      function aggregateDrawdownPoints(points, maxPoints = EQUITY_CHART_MAX_POINTS) {
        return aggregateExtremePoints(points, maxPoints, 0);
      }

      function aggregateExtremePoints(points, maxPoints, baseline) {
        if (points.length <= maxPoints) return points;
        const bucketSize = points.length / maxPoints;
        const sampled = [];
        for (let bucket = 0; bucket < maxPoints; bucket += 1) {
          const start = Math.floor(bucket * bucketSize);
          const end = bucket === maxPoints - 1 ? points.length : Math.floor((bucket + 1) * bucketSize);
          const slice = points.slice(start, Math.max(start + 1, end));
          let extreme = slice[0];
          slice.forEach((point) => {
            if (Math.abs(point.value - baseline) > Math.abs(extreme.value - baseline)) {
              extreme = point;
            }
          });
          sampled.push(extreme);
        }
        return sampled;
      }

      function drawdownPointsFromEquityCurve(curve) {
        const points = normalizeEquityCurve(curve);
        let peak = null;
        return points.map((point) => {
          if (!peak || point.value > peak.value) {
            peak = point;
          }
          const value = peak && peak.value !== 0 ? (point.value - peak.value) / peak.value * 100 : 0;
          return {
            index: point.index,
            time: point.time,
            value,
            equity: point.value,
            peakIndex: peak?.index ?? point.index,
            peakTime: peak?.time || point.time,
            peakEquity: peak?.value ?? point.value,
          };
        });
      }

      function renderEquityGrid({width, height, pad, min, max, baselineY, visiblePoints, pointX, displayTimezone}) {
        const yTicks = Array.from({length: 5}, (_, index) => {
          const ratio = index / 4;
          const y = pad.top + ratio * (height - pad.top - pad.bottom);
          const value = max - ratio * (max - min);
          return `
            <line class="equity-grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}"></line>
            <text class="equity-axis-label y" x="${pad.left - 10}" y="${y + 4}" text-anchor="end">${escapeHtml(formatEquityValue(value))}</text>`;
        }).join("");
        const xIndexes = uniqueTickIndexes(visiblePoints.length);
        const xTicks = xIndexes.map((visibleIndex) => {
          const point = visiblePoints[visibleIndex];
          const x = pointX(point);
          return `
            <line class="equity-grid-line vertical" x1="${x}" x2="${x}" y1="${pad.top}" y2="${height - pad.bottom}"></line>
            <text class="equity-axis-label x" x="${x}" y="${height - pad.bottom + 22}" text-anchor="middle">${escapeHtml(compactChartTime(point.time, displayTimezone))}</text>`;
        }).join("");
        return `
          <rect class="equity-chart-plot" x="${pad.left}" y="${pad.top}" width="${width - pad.left - pad.right}" height="${height - pad.top - pad.bottom}"></rect>
          ${yTicks}
          ${xTicks}
          <line class="equity-baseline" x1="${pad.left}" x2="${width - pad.right}" y1="${baselineY}" y2="${baselineY}"></line>`;
      }

      function renderDrawdownGrid({width, height, pad, min, max, zeroY, visiblePoints, pointX, displayTimezone}) {
        const yTicks = Array.from({length: 5}, (_, index) => {
          const ratio = index / 4;
          const y = pad.top + ratio * (height - pad.top - pad.bottom);
          const value = max - ratio * (max - min);
          return `
            <line class="drawdown-grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}"></line>
            <text class="drawdown-axis-label y" x="${pad.left - 10}" y="${y + 4}" text-anchor="end">${escapeHtml(formatSignedPercent(value))}</text>`;
        }).join("");
        const xIndexes = uniqueTickIndexes(visiblePoints.length);
        const xTicks = xIndexes.map((visibleIndex) => {
          const point = visiblePoints[visibleIndex];
          const x = pointX(point);
          return `
            <line class="drawdown-grid-line vertical" x1="${x}" x2="${x}" y1="${pad.top}" y2="${height - pad.bottom}"></line>
            <text class="drawdown-axis-label x" x="${x}" y="${height - pad.bottom + 21}" text-anchor="middle">${escapeHtml(compactChartTime(point.time, displayTimezone))}</text>`;
        }).join("");
        const start = visiblePoints[0];
        const end = visiblePoints[visiblePoints.length - 1];
        return `
          <rect class="drawdown-chart-plot" x="${pad.left}" y="${pad.top}" width="${width - pad.left - pad.right}" height="${height - pad.top - pad.bottom}"></rect>
          ${yTicks}
          ${xTicks}
          <line class="drawdown-zero-line" x1="${pad.left}" x2="${width - pad.right}" y1="${zeroY}" y2="${zeroY}"></line>
          <text class="drawdown-boundary-label start" x="${pad.left}" y="${height - 26}" text-anchor="start">Start ${escapeHtml(compactChartTime(start?.time, displayTimezone))}</text>
          <text class="drawdown-boundary-label end" x="${width - pad.right}" y="${height - 26}" text-anchor="end">End ${escapeHtml(compactChartTime(end?.time, displayTimezone))}</text>`;
      }

      function uniqueTickIndexes(length) {
        if (length <= 1) return [0];
        return [...new Set([0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round((length - 1) * ratio)))];
      }

      function renderEquitySegments(points, baseline, baselineY, colors) {
        if (!points.length) return "";
        if (points.length === 1) {
          const tone = points[0].value >= baseline ? "profit" : "loss";
          const stroke = tone === "profit" ? colors.profit : colors.loss;
          return `<circle class="equity-chart-point ${tone}" cx="${points[0].x}" cy="${points[0].y}" r="3.5" fill="${stroke}"></circle>`;
        }
        return points.slice(1).map((point, index) => {
          const previous = points[index];
          if (previous.value === point.value || (previous.value >= baseline && point.value >= baseline) || (previous.value <= baseline && point.value <= baseline)) {
            return equitySegment(previous, point, point.value >= baseline ? "profit" : "loss", colors);
          }
          const ratio = (baseline - previous.value) / (point.value - previous.value);
          const cross = {
            x: Number((previous.x + (point.x - previous.x) * ratio).toFixed(2)),
            y: baselineY,
            value: baseline,
          };
          return [
            equitySegment(previous, cross, previous.value >= baseline ? "profit" : "loss", colors),
            equitySegment(cross, point, point.value >= baseline ? "profit" : "loss", colors),
          ].join("");
        }).join("");
      }

      function equitySegment(start, end, tone, colors) {
        const stroke = tone === "profit" ? colors.profit : colors.loss;
        return `<path class="equity-chart-segment ${tone}" d="M ${start.x} ${start.y} L ${end.x} ${end.y}" stroke="${stroke}"></path>`;
      }

      function drawdownLinePath(points) {
        if (!points.length) return "";
        if (points.length === 1) {
          return `<circle class="drawdown-chart-point" cx="${points[0].x}" cy="${points[0].y}" r="3.5"></circle>`;
        }
        const d = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
        return `<path class="drawdown-chart-line" d="${d}"></path>`;
      }

      function renderDrawdownWorstMarker(point) {
        const label = formatSignedPercent(point.value);
        const labelX = Math.max(78, Math.min(822, point.x));
        const labelY = Math.max(38, point.y - 18);
        return `
          <g class="drawdown-worst-marker" data-drawdown-index="${point.index}">
            <line x1="${point.x}" x2="${point.x}" y1="${point.y - 2}" y2="${labelY + 9}"></line>
            <circle cx="${point.x}" cy="${point.y}" r="5"></circle>
            <rect x="${labelX - 34}" y="${labelY - 13}" width="68" height="24" rx="5"></rect>
            <text x="${labelX}" y="${labelY + 4}" text-anchor="middle">${escapeHtml(label)}</text>
          </g>
          <circle class="drawdown-worst-hit" cx="${point.x}" cy="${point.y}" r="16" fill="transparent" data-drawdown-index="${point.index}" data-drawdown-x="${point.x}" data-drawdown-y="${point.y}"></circle>`;
      }

      function wireEquityTooltip(svg, sourcePoints, baseline, displayTimezone) {
        const tooltip = ensureTooltip(svg);
        svg.querySelectorAll(".equity-chart-hit").forEach((node) => {
          node.addEventListener("mouseenter", () => {
            showEquityCrosshair(svg, node.dataset.equityX);
          });
          node.addEventListener("mousemove", (event) => {
            const point = sourcePoints[Number(node.dataset.equityIndex)];
            if (!point) return;
            showEquityCrosshair(svg, node.dataset.equityX);
            showTooltip(svg, tooltip, event, equityTooltipHtml(point, baseline, displayTimezone));
          });
          node.addEventListener("mouseleave", () => hideEquityChartHover(svg));
        });
        svg.addEventListener("mouseleave", () => hideEquityChartHover(svg));
      }

      function showEquityCrosshair(svg, x) {
        const crosshair = svg?.querySelector(".equity-chart-crosshair");
        const number = Number(x);
        if (!crosshair || !Number.isFinite(number)) return;
        crosshair.setAttribute("x1", String(number));
        crosshair.setAttribute("x2", String(number));
        crosshair.setAttribute("visibility", "visible");
      }

      function hideEquityCrosshair(svg) {
        const crosshair = svg?.querySelector(".equity-chart-crosshair");
        if (crosshair) crosshair.setAttribute("visibility", "hidden");
      }

      function hideEquityChartHover(svg) {
        hideTooltip(svg);
        hideEquityCrosshair(svg);
      }

      function equityTooltipHtml(point, baseline, displayTimezone) {
        const change = baseline ? (point.value / baseline - 1) * 100 : 0;
        return `
          <div class="chart-tooltip-title">${escapeHtml(point.time ? formatTimestamp(point.time, displayTimezone) : `Point ${point.index + 1}`)}</div>
          <div class="chart-tooltip-grid">
            <span>Equity</span><strong>${escapeHtml(formatEquityValue(point.value))}</strong>
            <span>Change</span><strong>${escapeHtml(formatSignedPercent(change))}</strong>
            <span>Index</span><strong>${escapeHtml(formatNumber(point.index + 1))}</strong>
          </div>`;
      }

      function wireDrawdownTooltip(svg, sourcePoints, worstPoint, displayTimezone) {
        const tooltip = ensureTooltip(svg);
        svg.querySelectorAll(".drawdown-chart-hit, .drawdown-worst-hit").forEach((node) => {
          node.addEventListener("mouseenter", () => {
            showDrawdownCrosshair(svg, node.dataset.drawdownX);
          });
          node.addEventListener("mousemove", (event) => {
            const point = sourcePoints[Number(node.dataset.drawdownIndex)];
            if (!point) return;
            showDrawdownCrosshair(svg, node.dataset.drawdownX);
            showTooltip(svg, tooltip, event, drawdownTooltipHtml(point, worstPoint, displayTimezone));
          });
          node.addEventListener("mouseleave", () => hideDrawdownChartHover(svg));
        });
        svg.addEventListener("mouseleave", () => hideDrawdownChartHover(svg));
      }

      function showDrawdownCrosshair(svg, x) {
        const crosshair = svg?.querySelector(".drawdown-chart-crosshair");
        const number = Number(x);
        if (!crosshair || !Number.isFinite(number)) return;
        crosshair.setAttribute("x1", String(number));
        crosshair.setAttribute("x2", String(number));
        crosshair.setAttribute("visibility", "visible");
      }

      function hideDrawdownCrosshair(svg) {
        const crosshair = svg?.querySelector(".drawdown-chart-crosshair");
        if (crosshair) crosshair.setAttribute("visibility", "hidden");
      }

      function hideDrawdownChartHover(svg) {
        hideTooltip(svg);
        hideDrawdownCrosshair(svg);
      }

      function drawdownTooltipHtml(point, worstPoint, displayTimezone) {
        const title = worstPoint && point.index === worstPoint.index ? "Max drawdown" : "Drawdown";
        return `
          <div class="chart-tooltip-title">${escapeHtml(title)} - ${escapeHtml(point.time ? formatTimestamp(point.time, displayTimezone) : `Point ${point.index + 1}`)}</div>
          <div class="chart-tooltip-grid">
            <span>Drawdown</span><strong>${escapeHtml(formatSignedPercent(point.value))}</strong>
            <span>Peak time</span><strong>${escapeHtml(formatTimestamp(point.peakTime, displayTimezone))}</strong>
            <span>Equity</span><strong>${escapeHtml(formatEquityValue(point.equity))}</strong>
          </div>`;
      }

      function wireEquityChartNavigation(svg, selector, curve, options, totalPoints) {
        svg.classList.toggle("is-draggable", totalPoints > 1);
        if (totalPoints <= 1) return;
        svg.onwheel = (event) => {
          event.preventDefault();
          const view = chartViews.get(selector);
          if (!view) return;
          const rect = svg.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)));
          const visible = view.end - view.start + 1;
          const nextVisible = event.deltaY < 0
            ? Math.max(EQUITY_CHART_MIN_VISIBLE_POINTS, Math.round(visible * 0.74))
            : Math.min(totalPoints, Math.round(visible * 1.36));
          if (nextVisible === visible) return;
          const center = view.start + Math.round((visible - 1) * ratio);
          const start = Math.round(center - (nextVisible - 1) * ratio);
          setViewport(selector, start, start + nextVisible - 1, totalPoints);
          renderEquityCurveSvg(selector, curve, options);
        };
        svg.ondblclick = () => {
          resetEquityCurveView(selector);
          renderEquityCurveSvg(selector, curve, options);
        };
        svg.onpointerdown = (event) => {
          if (event.button !== 0) return;
          const view = chartViews.get(selector);
          if (!view) return;
          view.drag = {
            clientX: event.clientX,
            start: view.start,
            end: view.end,
            lastDeltaPoints: 0,
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
          const pxPerPoint = Math.max(1, rect.width / Math.max(1, visible));
          const deltaPoints = Math.round((drag.clientX - event.clientX) / pxPerPoint);
          if (deltaPoints === drag.lastDeltaPoints) return;
          drag.lastDeltaPoints = deltaPoints;
          setViewport(selector, drag.start + deltaPoints, drag.end + deltaPoints, totalPoints);
          if (!drag.renderFrame) {
            drag.renderFrame = requestAnimationFrame(() => {
              drag.renderFrame = 0;
              renderEquityCurveSvg(selector, curve, options);
            });
          }
        };
        svg.onpointerup = (event) => {
          const view = chartViews.get(selector);
          const drag = view?.drag;
          if (!drag) return;
          const rect = svg.getBoundingClientRect();
          const visible = drag.end - drag.start + 1;
          const pxPerPoint = Math.max(1, rect.width / Math.max(1, visible));
          const deltaPoints = Math.round((drag.clientX - event.clientX) / pxPerPoint);
          setViewport(selector, drag.start + deltaPoints, drag.end + deltaPoints, totalPoints);
          if (drag.renderFrame) {
            cancelAnimationFrame(drag.renderFrame);
          }
          view.drag = null;
          svg.classList.remove("dragging");
          renderEquityCurveSvg(selector, curve, options);
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

      function wireDrawdownChartNavigation(svg, selector, curve, options, totalPoints) {
        svg.classList.toggle("is-draggable", totalPoints > 1);
        if (totalPoints <= 1) return;
        svg.onwheel = (event) => {
          event.preventDefault();
          const view = chartViews.get(selector);
          if (!view) return;
          const rect = svg.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)));
          const visible = view.end - view.start + 1;
          const nextVisible = event.deltaY < 0
            ? Math.max(EQUITY_CHART_MIN_VISIBLE_POINTS, Math.round(visible * 0.74))
            : Math.min(totalPoints, Math.round(visible * 1.36));
          if (nextVisible === visible) return;
          const center = view.start + Math.round((visible - 1) * ratio);
          const start = Math.round(center - (nextVisible - 1) * ratio);
          setViewport(selector, start, start + nextVisible - 1, totalPoints);
          renderDrawdownCurveSvg(selector, curve, options);
        };
        svg.ondblclick = () => {
          resetDrawdownCurveView(selector);
          renderDrawdownCurveSvg(selector, curve, options);
        };
        svg.onpointerdown = (event) => {
          if (event.button !== 0) return;
          const view = chartViews.get(selector);
          if (!view) return;
          view.drag = {
            clientX: event.clientX,
            start: view.start,
            end: view.end,
            lastDeltaPoints: 0,
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
          const pxPerPoint = Math.max(1, rect.width / Math.max(1, visible));
          const deltaPoints = Math.round((drag.clientX - event.clientX) / pxPerPoint);
          if (deltaPoints === drag.lastDeltaPoints) return;
          drag.lastDeltaPoints = deltaPoints;
          setViewport(selector, drag.start + deltaPoints, drag.end + deltaPoints, totalPoints);
          if (!drag.renderFrame) {
            drag.renderFrame = requestAnimationFrame(() => {
              drag.renderFrame = 0;
              renderDrawdownCurveSvg(selector, curve, options);
            });
          }
        };
        svg.onpointerup = (event) => {
          const view = chartViews.get(selector);
          const drag = view?.drag;
          if (!drag) return;
          const rect = svg.getBoundingClientRect();
          const visible = drag.end - drag.start + 1;
          const pxPerPoint = Math.max(1, rect.width / Math.max(1, visible));
          const deltaPoints = Math.round((drag.clientX - event.clientX) / pxPerPoint);
          setViewport(selector, drag.start + deltaPoints, drag.end + deltaPoints, totalPoints);
          if (drag.renderFrame) {
            cancelAnimationFrame(drag.renderFrame);
          }
          view.drag = null;
          svg.classList.remove("dragging");
          renderDrawdownCurveSvg(selector, curve, options);
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

      function renderAverageLine(sourceBars, start, end, x, priceY, windowSize, color) {
        const points = [];
        sourceBars.slice(start, end + 1).forEach((bar, visibleIndex) => {
          const sourceIndex = start + visibleIndex;
          const slice = sourceBars.slice(Math.max(0, sourceIndex - windowSize + 1), sourceIndex + 1);
          const avg = slice.reduce((sum, item) => sum + Number(item.close || 0), 0) / slice.length;
          points.push(`${x(visibleIndex)},${priceY(avg)}`);
        });
        return `<polyline points="${points.join(" ")}" fill="none" stroke="${color}" stroke-width="2" opacity="0.95"></polyline>`;
      }

      function renderTradeMarker(x, y, marker, markerIndex = 0, colors = pnlColors()) {
        const tone = markerTone(marker);
        const exit = tone === "exit" || tone === "short";
        const color = markerColor(tone, colors);
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
        hideEquityCrosshair(svg);
        hideDrawdownCrosshair(svg);
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

      function markerColor(tone, colors = pnlColors()) {
        if (tone === "exit") return colors.down;
        if (tone === "short") return colors.down;
        if (tone === "event") return "#8b5cf6";
        if (tone === "funding") return "#0ea5e9";
        if (tone === "multi-leg") return "#64748b";
        return colors.up;
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

      function formatEquityValue(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return String(value ?? "n/a");
        return number.toLocaleString(undefined, {maximumFractionDigits: 6});
      }

      function formatSignedPercent(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "n/a";
        const sign = number > 0 ? "+" : "";
        return `${sign}${number.toFixed(2)}%`;
      }

      function compactChartTime(value, displayTimezone) {
        const formatted = formatTimestamp(value, displayTimezone);
        if (!formatted || formatted === "n/a") return "n/a";
        const parts = formatted.split(" ");
        return parts.length > 1 ? `${parts[0].slice(5)} ${parts[1]}` : formatted;
      }

      function formatTimestamp(value, displayTimezone) {
        return shared.formatTimestamp(value, displayTimezone);
      }

      window.HalphaDashboardStrategyChart = {
        EQUITY_CHART_MAX_POINTS,
        aggregateEquityPoints,
        aggregateDrawdownPoints,
        quoteAsset,
        renderDrawdownCurveSvg,
        renderEquityCurveSvg,
        resetCandlestickView,
        resetDrawdownCurveView,
        resetEquityCurveView,
        renderCandlestickSvg,
        strategyWindowLabel,
      };
    })();
