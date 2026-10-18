// Hal fiyatı + yapay zekâ tahmini grafiği (Hafta 10)
// Kullanım: <canvas data-price-chart="veri-script-id"></canvas>
//           <script type="application/json" id="veri-script-id">{...}</script>
// Tek varlık (bir ürünün fiyatı) çizilir: geçmiş düz çizgi, tahmin kesikli çizgi,
// %95 tahmin aralığı açık renkli alan. Tek eksen (TL).

(function () {
  const BRAND = "#2f7d32";
  const BAND_FILL = "rgba(47, 125, 50, 0.12)";
  const GRID = "rgba(0, 0, 0, 0.06)";
  const MUTED = "#6c757d";

  const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });

  function draw(canvas) {
    const source = document.getElementById(canvas.dataset.priceChart);
    if (!source || typeof Chart === "undefined") return;
    const data = JSON.parse(source.textContent);

    new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          { label: "Hal fiyatı", data: data.actual, borderColor: BRAND, backgroundColor: BRAND,
            borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, spanGaps: true, tension: 0.2 },
          { label: "Tahmin", data: data.predicted, borderColor: BRAND, backgroundColor: BRAND,
            borderDash: [6, 4], borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
          // Aralık: alt sınır görünmez çizgi, üst sınır alt sınıra kadar dolgulu
          { label: "Alt sınır", data: data.lower, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0 },
          { label: "Tahmin aralığı (%95)", data: data.upper, borderWidth: 0, pointRadius: 0,
            pointHoverRadius: 0, backgroundColor: BAND_FILL, fill: "-1" },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },   // dikey çizgi boyunca tüm değerler
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 18, boxHeight: 2, color: MUTED, filter: (item) => item.text !== "Alt sınır" },
          },
          tooltip: {
            filter: (item) => item.raw !== null && item.dataset.label !== "Alt sınır",
            callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${money.format(ctx.raw)}` },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: MUTED, maxTicksLimit: 8, autoSkip: true } },
          y: { grid: { color: GRID }, ticks: { color: MUTED, callback: (v) => money.format(v) } },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("canvas[data-price-chart]").forEach(draw);
  });
})();
