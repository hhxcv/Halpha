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
        if (["ok", "available", "succeeded", "success", "completed", "running"].includes(normalized)) {
          return normalized;
        }
        if (["failed", "error", "degraded", "blocked"].includes(normalized)) {
          return normalized;
        }
        if (["disabled", "not_generated", "not_run"].includes(normalized)) {
          return "skipped";
        }
        if (["insufficient_data", "unavailable"].includes(normalized)) {
          return "partial";
        }
        if (["warning", "partial", "missing", "skipped", "pending"].includes(normalized)) {
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

      function formatTimestamp(value, timeZone = "Asia/Shanghai") {
        if (!value) {
          return "n/a";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
          return String(value);
        }
        try {
          return new Intl.DateTimeFormat("en-US", {
            timeZone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          }).format(date);
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
        escapeHtml,
        text,
        statusClass,
        formatNumber,
        formatTimestamp,
        joinPath,
        markdownToHtml,
        renderInline,
        escapeRegExp,
      };
    })();
