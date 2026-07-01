    (function () {
      function createReportHelpers(deps) {
        const joinPath = deps.joinPath;
        const unique = deps.unique;

        function isAvailableReport(run) {
          const reportState = run?.report_state || {};
          return reportState.status === "available" && Boolean(run?.report || reportState.artifact);
        }

        function reportType(run) {
          if (String(run.status || "").toLowerCase() === "failed") {
            return "Failed";
          }
          const source = `${run.run_dir || ""} ${run.run_id || ""}`.toLowerCase();
          if (source.includes("monitor") || source.includes("cycle")) {
            return "Monitor-triggered";
          }
          if (String(run.codex_status || "").toLowerCase() === "skipped") {
            return "Manual";
          }
          return "Daily";
        }

        function reportTitle(run, type) {
          if (type === "Failed") return "Report Exception Record";
          if (type === "Monitor-triggered") return "Monitor Report";
          if (type === "Manual") return "Manual Research Report";
          return "Daily Market Brief";
        }

        function reportPath(run) {
          if (!run) return "";
          const report = String(run.report || run.report_state?.artifact || "");
          if (report.startsWith("runs/") || report.startsWith("data/")) return report;
          if (report) return joinPath(run.run_dir, report);
          return joinPath(run.run_dir, "report/report.md");
        }

        function reportRecords(runs) {
          return (Array.isArray(runs) ? runs : []).filter((run) => isAvailableReport(run)).map((run) => {
            const type = reportType(run);
            return {
              ...run,
              type,
              title: reportTitle(run, type),
              report_path: reportPath(run),
            };
          });
        }

        function reportSourceRefs(run, detail) {
          const refs = [];
          if (run?.manifest) refs.push(run.manifest);
          if (run?.report_path) refs.push(run.report_path);
          (detail?.report_files || []).forEach((file) => {
            const path = file?.ref || file?.path;
            if (path) refs.push(path);
          });
          (detail?.source_artifacts || []).forEach((ref) => refs.push(ref));
          (detail?.artifacts || []).forEach((artifact) => {
            const path = artifact.path || artifact.ref || artifact.artifact;
            if (path) refs.push(path);
          });
          return unique(refs);
        }

        function reportArtifactFiles(run, detail) {
          const files = Array.isArray(detail?.report_files) ? detail.report_files : [];
          if (files.length) {
            return files.map((file) => normalizeReportArtifact(file, run)).filter((file) => file.ref);
          }
          const reportRef = run?.report_path || reportPath(run);
          return reportRef ? [normalizeReportArtifact({
            ref: reportRef,
            path: reportRef,
            name: "report.md",
            title: "Report",
            category: "report",
            category_label: "Report",
            preview_kind: "markdown",
            pinned: true,
          }, run)] : [];
        }

        function normalizeReportArtifact(file, run) {
          const ref = String(file?.ref || file?.path || "").trim();
          const path = String(file?.path || ref).trim();
          const category = String(file?.category || reportArtifactCategory(path)).trim() || "other";
          return {
            ref,
            path,
            name: String(file?.name || path.split("/").pop() || ref.split("/").pop() || "artifact"),
            title: String(file?.title || reportArtifactTitle(path, category)),
            category,
            category_label: String(file?.category_label || reportArtifactCategoryLabel(category)),
            preview_kind: String(file?.preview_kind || reportArtifactPreviewKind(path)),
            size_bytes: Number(file?.size_bytes || 0),
            pinned: Boolean(file?.pinned || (category === "report" && ref === (run?.report_path || reportPath(run)))),
          };
        }

        function reportArtifactCategory(path) {
          if (path === "run_manifest.json" || path.endsWith("/run_manifest.json")) return "run_metadata";
          if (path.includes("/report/") || path.startsWith("report/")) return "report";
          if (path.includes("/analysis/") || path.startsWith("analysis/")) return "analysis";
          if (path.includes("/codex_context/") || path.startsWith("codex_context/")) return "codex_context";
          if (path.includes("/raw/") || path.startsWith("raw/")) return "raw_input";
          return "other";
        }

        function reportArtifactCategoryLabel(category) {
          return {
            report: "Report",
            analysis: "Analysis",
            codex_context: "Codex context",
            raw_input: "Raw inputs",
            run_metadata: "Run metadata",
            other: "Other",
          }[category] || "Other";
        }

        function reportArtifactTitle(path, category) {
          if (category === "report") return "Report";
          if (category === "run_metadata") return "Run manifest";
          const name = String(path || "").split("/").pop() || "artifact";
          const stem = name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
          return stem ? stem.replace(/\b\w/g, (char) => char.toUpperCase()) : name;
        }

        function reportArtifactPreviewKind(path) {
          const suffix = String(path || "").toLowerCase().split(".").pop();
          if (["md", "markdown"].includes(suffix)) return "markdown";
          if (suffix === "json") return "json";
          if (suffix === "jsonl") return "jsonl";
          if (suffix === "csv") return "csv";
          if (["txt", "log", "yaml", "yml"].includes(suffix)) return "text";
          return "unsupported";
        }

        function reportArtifactGroups(files) {
          const groups = [];
          const byCategory = new Map();
          files.filter((file) => !file.pinned).forEach((file) => {
            if (!byCategory.has(file.category)) {
              byCategory.set(file.category, []);
            }
            byCategory.get(file.category).push(file);
          });
          ["analysis", "codex_context", "raw_input", "run_metadata", "other", "report"].forEach((category) => {
            const items = byCategory.get(category) || [];
            if (items.length) groups.push({category, label: reportArtifactCategoryLabel(category), items});
          });
          return groups;
        }

        return {
          isAvailableReport,
          reportArtifactFiles,
          reportArtifactGroups,
          reportPath,
          reportRecords,
          reportSourceRefs,
          reportTitle,
          reportType,
        };
      }

      window.HalphaDashboardReports = {
        createReportHelpers,
      };
    })();
