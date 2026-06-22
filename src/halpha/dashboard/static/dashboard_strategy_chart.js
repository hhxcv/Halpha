    (function () {
      const shared = window.HalphaDashboardShared;
      if (!shared) {
        throw new Error("Halpha dashboard shared helpers did not load.");
      }
      const {escapeHtml, formatNumber} = shared;

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

      function renderCandlestickSvg(selector, vis) {
        const svg = document.querySelector(selector);
        if (!svg) return;
        const bars = vis.bars || [];
        if (!bars.length) {
          svg.innerHTML = `<text x="490" y="235" fill="#9fb2c7" text-anchor="middle">No backtest visualization available</text>`;
          return;
        }
        const width = 980;
        const height = 470;
        const pad = {left: 44, right: 70, top: 28, bottom: 86};
        const max = Math.max(...bars.map((bar) => Number(bar.high) || 0));
        const min = Math.min(...bars.map((bar) => Number(bar.low) || 0));
        const priceY = (value) => pad.top + (max - value) / Math.max(1, max - min) * (height - pad.top - pad.bottom);
        const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, bars.length - 1));
        const candleWidth = Math.max(3, Math.min(9, (width - pad.left - pad.right) / bars.length * 0.58));
        const maxVolume = Math.max(...bars.map((bar) => Number(bar.volume) || 0), 1);
        const markerByTime = new Map((vis.markers || []).map((marker) => [marker.time, marker]));
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
          const marker = markerByTime.get(bar.time);
          const markerSvg = marker ? renderTradeMarker(cx, priceY(Number(marker.price) || close), marker) : "";
          return `
            <line x1="${cx}" x2="${cx}" y1="${yHigh}" y2="${yLow}" stroke="${color}" stroke-width="1.2"></line>
            <rect x="${cx - candleWidth / 2}" y="${bodyY}" width="${candleWidth}" height="${bodyH}" fill="${color}" rx="1"></rect>
            <rect x="${cx - candleWidth / 2}" y="${volumeY}" width="${candleWidth}" height="${volumeH}" fill="${color}" opacity="0.42"></rect>
            ${markerSvg}`;
        }).join("");
        const grid = Array.from({length: 6}, (_, index) => {
          const y = pad.top + index * ((height - pad.top - pad.bottom) / 5);
          const price = max - index * ((max - min) / 5);
          return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" stroke="rgba(255,255,255,0.07)"></line><text x="${width - pad.right + 12}" y="${y + 4}" fill="#9fb2c7" font-size="12">${formatNumber(Math.round(price))}</text>`;
        }).join("");
        const ma50 = renderAverageLine(bars, x, priceY, 12, "#4f8cff");
        const ma200 = renderAverageLine(bars, x, priceY, 34, "#f59e0b");
        svg.innerHTML = `${grid}${ma50}${ma200}${candleSvg}<text x="54" y="24" fill="#dbe7f3" font-size="13">${escapeHtml([vis.symbol, vis.timeframe].filter(Boolean).join(" - ") || "Backtest")}</text><text x="54" y="44" fill="#9fb2c7" font-size="12">MA 50 close  MA 200 close</text>`;
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

      function renderTradeMarker(x, y, marker) {
        const entry = String(marker.kind || marker.label || "").toLowerCase().includes("entry") || String(marker.label || "").toLowerCase().includes("buy");
        const color = entry ? "#00a88f" : "#f04438";
        const labelText = marker.label || (entry ? "Buy" : "Sell");
        const labelY = entry ? y + 28 : y - 24;
        return `<g><line x1="${x}" x2="${x}" y1="${entry ? y + 4 : y - 4}" y2="${entry ? labelY - 10 : labelY + 10}" stroke="${color}" stroke-width="1.4"></line><rect x="${x - 17}" y="${labelY - 11}" width="34" height="22" rx="4" fill="${color}"></rect><text x="${x}" y="${labelY + 4}" fill="#fff" text-anchor="middle" font-size="11" font-weight="800">${escapeHtml(labelText)}</text></g>`;
      }

      function formatTimestamp(value, displayTimezone) {
        return shared.formatTimestamp(value, displayTimezone);
      }

      window.HalphaDashboardStrategyChart = {
        quoteAsset,
        renderCandlestickSvg,
        strategyWindowLabel,
      };
    })();
