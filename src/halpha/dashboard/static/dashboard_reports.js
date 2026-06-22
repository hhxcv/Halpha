    (function () {
      function createReportHelpers(deps) {
        const joinPath = deps.joinPath;
        const unique = deps.unique;

        function isAvailableReport(run) {
          const reportState = run?.report_state || {};
          return reportState.status === "available" && Boolean(run?.report || reportState.artifact);
        }

        function reportType(run) {
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
          if (type === "Monitor-triggered") return `Monitor Report ${run.run_id}`;
          if (type === "Manual") return `Manual Research Report ${run.run_id}`;
          return `Daily Market Brief ${run.run_id}`;
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
          (detail?.source_artifacts || []).forEach((ref) => refs.push(ref));
          (detail?.artifacts || []).forEach((artifact) => {
            const path = artifact.path || artifact.ref || artifact.artifact;
            if (path) refs.push(path);
          });
          return unique(refs);
        }

        return {
          isAvailableReport,
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
