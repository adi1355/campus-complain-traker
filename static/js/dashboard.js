/* Draws the Chart.js charts on the dashboards. Data comes from a JSON endpoint. */
(function () {
  "use strict";

  var BLUES = ["#1f6feb", "#0ea5e9", "#6366f1", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b"];
  var STATUS_COLORS = ["#f59e0b", "#0ea5e9", "#16a34a"];
  var PRIORITY_COLORS = ["#9ca3af", "#38bdf8", "#fb923c", "#ef4444"];

  function showFallback(message) {
    document.querySelectorAll(".chart-box").forEach(function (box) {
      box.innerHTML = '<p class="chart-fallback">' + message + "</p>";
    });
  }

  function make(id, config) {
    var el = document.getElementById(id);
    if (el) { new Chart(el, config); }
  }

  function drawCharts(d) {
    var legendBottom = { legend: { position: "bottom" } };

    make("statusChart", {
      type: "doughnut",
      data: { labels: ["Pending", "In Progress", "Resolved"],
              datasets: [{ data: [d.status.pending, d.status.in_progress, d.status.resolved],
                           backgroundColor: STATUS_COLORS, borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: "62%", plugins: legendBottom }
    });

    make("categoryChart", {
      type: "bar",
      data: { labels: d.by_category.map(function (c) { return c.name; }),
              datasets: [{ label: "Complaints", data: d.by_category.map(function (c) { return c.count; }),
                           backgroundColor: BLUES, borderRadius: 6 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
                 scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    make("monthlyChart", {
      type: "bar",
      data: { labels: d.monthly.labels,
              datasets: [
                { label: "Submitted", data: d.monthly.submitted, backgroundColor: "#1f6feb", borderRadius: 5 },
                { type: "line", label: "Resolved", data: d.monthly.resolved, borderColor: "#16a34a",
                  backgroundColor: "#16a34a", tension: 0.3 }
              ] },
      options: { maintainAspectRatio: false, plugins: legendBottom, interaction: { mode: "index", intersect: false },
                 scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    if (d.priority) {
      make("priorityChart", {
        type: "doughnut",
        data: { labels: d.priority.map(function (p) { return p.name; }),
                datasets: [{ data: d.priority.map(function (p) { return p.count; }),
                             backgroundColor: PRIORITY_COLORS, borderWidth: 0 }] },
        options: { maintainAspectRatio: false, cutout: "62%", plugins: legendBottom }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Ask for confirmation on buttons/forms that carry data-confirm="message"
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (!window.confirm(form.getAttribute("data-confirm"))) { e.preventDefault(); }
      });
    });

    var root = document.getElementById("chart-root");
    if (!root) { return; }
    if (typeof Chart === "undefined") {
      showFallback("Charts could not load (Chart.js needs an internet connection).");
      return;
    }
    fetch(root.getAttribute("data-endpoint"), { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
      .then(drawCharts)
      .catch(function () { showFallback("Could not load chart data. Please refresh the page."); });
  });
})();
