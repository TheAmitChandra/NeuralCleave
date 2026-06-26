(() => {
  "use strict";

  if (typeof Chart === "undefined") return;

  Chart.defaults.color = "#9a9aa5";
  Chart.defaults.font.family =
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

  const gridColor = "rgba(154, 154, 165, 0.12)";

  // ── Radar: CortexFlow vs OpenClaw, scored 1-5 per dimension ─────────
  const radarEl = document.getElementById("comparisonRadarChart");
  if (radarEl) {
    new Chart(radarEl, {
      type: "radar",
      data: {
        labels: [
          "Memory",
          "LLM Routing",
          "Voice",
          "Web UI",
          "Config",
          "Observability",
          "Plugin Security",
        ],
        datasets: [
          {
            label: "OpenClaw",
            data: [2, 2, 2, 1, 2, 1, 1],
            backgroundColor: "rgba(154, 154, 165, 0.12)",
            borderColor: "#9a9aa5",
            pointBackgroundColor: "#9a9aa5",
            borderWidth: 2,
          },
          {
            label: "CortexFlow",
            data: [5, 5, 4, 5, 5, 5, 5],
            backgroundColor: "rgba(99, 102, 241, 0.25)",
            borderColor: "#6366f1",
            pointBackgroundColor: "#a855f7",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          r: {
            min: 0,
            max: 5,
            ticks: { display: false, stepSize: 1 },
            grid: { color: gridColor },
            angleLines: { color: gridColor },
            pointLabels: { font: { size: 11 } },
          },
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } },
        },
      },
    });
  }

  // ── Bar: scale numbers (channels, providers, tests, coverage) ──────
  const scaleEl = document.getElementById("scaleBarChart");
  if (scaleEl) {
    new Chart(scaleEl, {
      type: "bar",
      data: {
        labels: ["Channels", "LLM Providers", "CLI Commands", "Doc Pages"],
        datasets: [
          {
            label: "CortexFlow",
            data: [14, 5, 20, 7],
            backgroundColor: "#6366f1",
            borderRadius: 6,
            maxBarThickness: 40,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, grid: { color: gridColor } },
          x: { grid: { display: false } },
        },
      },
    });
  }
})();
