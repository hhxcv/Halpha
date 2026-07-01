    (function () {
      function escapeHtml(value) {
        return String(value ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
      }

      function text(value, fallback = "n/a") {
        if (value === null || value === undefined || value === "") {
          return fallback;
        }
        return String(value);
      }

      function statusClass(status) {
        const normalized = String(status || "unknown").toLowerCase();
        if (["ok", "available", "succeeded", "success", "completed", "running", "collected", "no_data"].includes(normalized)) {
          return normalized;
        }
        if (["failed", "error", "degraded", "blocked", "cancelled"].includes(normalized)) {
          return normalized;
        }
        if (["disabled", "not_generated", "not_run", "unsupported"].includes(normalized)) {
          return "skipped";
        }
        if (["insufficient_data", "unavailable"].includes(normalized)) {
          return "partial";
        }
        if (["created", "creating", "queued"].includes(normalized)) {
          return "pending";
        }
        if (["warning", "partial", "missing", "skipped", "pending", "not_collected", "stale"].includes(normalized)) {
          return normalized;
        }
        return "unknown";
      }

      function formatNumber(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) {
          return text(value);
        }
        return new Intl.NumberFormat("en-US").format(number);
      }

      const pnlColorSchemeDefaults = {
        scheme: "green_profit_red_loss",
      };

      function normalizePnlColorScheme(value) {
        return value === "red_profit_green_loss" ? "red_profit_green_loss" : "green_profit_red_loss";
      }

      function configurePnlColorScheme(value) {
        pnlColorSchemeDefaults.scheme = normalizePnlColorScheme(value);
      }

      function pnlColors(value = pnlColorSchemeDefaults.scheme) {
        const scheme = normalizePnlColorScheme(value);
        if (scheme === "red_profit_green_loss") {
          return {
            scheme,
            profit: "#c92a2a",
            loss: "#087f5b",
            profitSoft: "#fff1ef",
            lossSoft: "#eef7f3",
            up: "#c92a2a",
            down: "#087f5b",
          };
        }
        return {
          scheme,
          profit: "#087f5b",
          loss: "#c92a2a",
          profitSoft: "#eef7f3",
          lossSoft: "#fff1ef",
          up: "#087f5b",
          down: "#c92a2a",
        };
      }

      function pnlNumber(value) {
        if (typeof value === "number") {
          return Number.isFinite(value) ? value : null;
        }
        const textValue = String(value ?? "").trim();
        if (!textValue || textValue.toLowerCase() === "n/a") {
          return null;
        }
        const match = textValue.replace(/,/g, "").match(/[-+]?\d*\.?\d+/);
        if (!match) {
          return null;
        }
        const number = Number(match[0]);
        return Number.isFinite(number) ? number : null;
      }

      function pnlClass(value) {
        const number = pnlNumber(value);
        if (number === null || number === 0) {
          return "pnl-neutral";
        }
        return number > 0 ? "pnl-positive" : "pnl-negative";
      }

      const timestampFormatDefaults = {
        timeZone: "Asia/Shanghai",
        hourCycle: "24h",
        dateOrder: "year_first",
      };

      function configureTimestampFormat(options = {}) {
        const normalized = timestampFormatOptions(options);
        timestampFormatDefaults.timeZone = normalized.timeZone;
        timestampFormatDefaults.hourCycle = normalized.hourCycle;
        timestampFormatDefaults.dateOrder = normalized.dateOrder;
      }

      function timestampFormatOptions(timeZoneOrOptions = {}, overrides = {}) {
        const base = typeof timeZoneOrOptions === "string"
          ? {timeZone: timeZoneOrOptions, ...overrides}
          : {...timeZoneOrOptions, ...overrides};
        const timeZone = typeof base.timeZone === "string" && base.timeZone.trim()
          ? base.timeZone.trim()
          : timestampFormatDefaults.timeZone;
        const hourCycle = base.hourCycle === "12h" ? "12h" : base.hourCycle === "24h" ? "24h" : timestampFormatDefaults.hourCycle;
        const dateOrder = base.dateOrder === "year_last" ? "year_last" : base.dateOrder === "year_first" ? "year_first" : timestampFormatDefaults.dateOrder;
        return {timeZone, hourCycle, dateOrder};
      }

      function formatTimestamp(value, timeZoneOrOptions = {}, overrides = {}) {
        if (!value) {
          return "n/a";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
          return String(value);
        }
        const options = timestampFormatOptions(timeZoneOrOptions, overrides);
        try {
          const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: options.timeZone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: options.hourCycle === "12h",
            hourCycle: options.hourCycle === "12h" ? "h12" : "h23",
          }).formatToParts(date).reduce((memo, part) => {
            if (part.type !== "literal") {
              memo[part.type] = part.value;
            }
            return memo;
          }, {});
          const year = parts.year || "0000";
          const month = parts.month || "00";
          const day = parts.day || "00";
          const hour = options.hourCycle === "24h" && parts.hour === "24" ? "00" : parts.hour || "00";
          const minute = parts.minute || "00";
          const dayPeriod = parts.dayPeriod ? ` ${parts.dayPeriod}` : "";
          const dateText = options.dateOrder === "year_last" ? `${month}/${day}/${year}` : `${year}-${month}-${day}`;
          return `${dateText} ${hour}:${minute}${options.hourCycle === "12h" ? dayPeriod : ""}`;
        } catch (_error) {
          return date.toISOString();
        }
      }

      function joinPath(base, path) {
        const left = String(base || "").replace(/\/$/, "");
        const right = String(path || "").replace(/^\//, "");
        return left && right ? `${left}/${right}` : right || left;
      }

      function markdownToHtml(markdown, searchTerm = "") {
        const lines = String(markdown || "").split(/\r?\n/);
        const html = [];
        let listOpen = false;
        let tableLines = [];
        const closeList = () => {
          if (listOpen) {
            html.push("</ul>");
            listOpen = false;
          }
        };
        const flushTable = () => {
          if (!tableLines.length) return;
          const rows = tableLines.map((line) => line.split("|").slice(1, -1).map((cell) => cell.trim()));
          const header = rows[0] || [];
          const body = rows.slice(2);
          html.push(`<div class="markdown-table-wrap"><table><thead><tr>${header.map((cell) => `<th>${renderInline(cell, searchTerm)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell, searchTerm)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
          tableLines = [];
        };
        lines.forEach((raw) => {
          if (/^\|.*\|$/.test(raw.trim())) {
            closeList();
            tableLines.push(raw.trim());
            return;
          }
          flushTable();
          if (!raw.trim()) {
            closeList();
            return;
          }
          if (raw.startsWith("# ")) {
            closeList();
            html.push(`<h1>${renderInline(raw.slice(2), searchTerm)}</h1>`);
          } else if (raw.startsWith("## ")) {
            closeList();
            html.push(`<h2>${renderInline(raw.slice(3), searchTerm)}</h2>`);
          } else if (raw.startsWith("### ")) {
            closeList();
            html.push(`<h3>${renderInline(raw.slice(4), searchTerm)}</h3>`);
          } else if (raw.startsWith("- ")) {
            if (!listOpen) {
              html.push("<ul>");
              listOpen = true;
            }
            html.push(`<li>${renderInline(raw.slice(2), searchTerm)}</li>`);
          } else {
            closeList();
            html.push(`<p>${renderInline(raw, searchTerm)}</p>`);
          }
        });
        closeList();
        flushTable();
        return html.join("");
      }

      function renderInline(value, searchTerm = "") {
        const escaped = escapeHtml(value);
        const query = String(searchTerm || "").trim();
        if (!query) return escaped;
        const escapedQuery = escapeHtml(query);
        const pattern = new RegExp(escapeRegExp(escapedQuery), "gi");
        return escaped.replace(pattern, (match) => `<mark>${match}</mark>`);
      }

      function escapeRegExp(value) {
        return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }

      window.HalphaDashboardShared = {
        configureTimestampFormat,
        configurePnlColorScheme,
        escapeHtml,
        text,
        statusClass,
        formatNumber,
        formatTimestamp,
        normalizePnlColorScheme,
        pnlClass,
        pnlColors,
        pnlNumber,
        joinPath,
        markdownToHtml,
        renderInline,
        escapeRegExp,
      };
    })();
