// Satış raporu grafiği (Hafta 12): dönem cirosu sütunları + sipariş sayısı çizgisi (ikinci eksen).
// Kullanım: <canvas data-report-chart="veri-script-id"></canvas>
//           <script type="application/json" id="veri-script-id">{"labels": [...], "revenue": [...], "orders": [...]}</script>
// Veri JSON olarak gömülür; satır içi çalıştırılabilir betik olmadığı için CSP'ye takılmaz.

(function () {
  const BRAND = "#2f7d32";
  const EARTH = "#a0703c";
  const GRID = "rgba(0, 0, 0, 0.06)";
  const MUTED = "#6c757d";
  const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });

  function draw(canvas) {
    const source = document.getElementById(canvas.dataset.reportChart);
    if (!source || typeof Chart === "undefined") return;
    const data = JSON.parse(source.textContent);

    new Chart(canvas, {
      data: {
        labels: data.labels,
        datasets: [
          { type: "bar", label: "Ciro", data: data.revenue, backgroundColor: BRAND, borderRadius: 3,
            maxBarThickness: 28, yAxisID: "y" },
          { type: "line", label: "Sipariş", data: data.orders, borderColor: EARTH, backgroundColor: EARTH,
            borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.25, yAxisID: "y2" },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 14, color: MUTED } },
          tooltip: {
            callbacks: {
              label: (ctx) => ctx.dataset.yAxisID === "y"
                ? ` Ciro: ${money.format(ctx.raw)}`
                : ` Sipariş: ${ctx.raw}`,
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: MUTED, maxTicksLimit: 12, autoSkip: true } },
          y: { beginAtZero: true, grid: { color: GRID }, ticks: { color: MUTED, callback: (v) => money.format(v) } },
          y2: { beginAtZero: true, position: "right", grid: { display: false },
                ticks: { color: MUTED, precision: 0 } },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("canvas[data-report-chart]").forEach(draw);
  });
})();
