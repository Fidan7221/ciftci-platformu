// Sitenin ortak küçük davranışları (Hafta 11).
// CSP satır içi olay işleyicilerini (onsubmit="...") engellediği için onay pencereleri
// buradan bağlanır:  <form data-confirm="Emin misiniz?"> ... </form>
document.addEventListener("submit", function (event) {
  const form = event.target.closest("form[data-confirm]");
  if (form && !window.confirm(form.dataset.confirm)) {
    event.preventDefault();
  }
});

// <a data-back> : bir önceki sayfaya dön (javascript: bağlantıları CSP ile engellenir)
document.addEventListener("click", function (event) {
  const link = event.target.closest("a[data-back]");
  if (link && window.history.length > 1) {
    event.preventDefault();
    window.history.back();
  }
});

// Hafta 12 — <select data-autosubmit>: seçim değişince formu gönder (sıralama kutusu).
// CSP satır içi onchange="..." kullanımına izin vermediği için burada bağlanır.
document.addEventListener("change", function (event) {
  const select = event.target.closest("select[data-autosubmit]");
  if (select && select.form) {
    select.form.requestSubmit();
  }
});

// Hafta 12 — İl seçilince ilçe listesinde yalnızca o ilin ilçeleri görünsün.
// JavaScript kapalıysa tüm ilçeler il başlıkları altında görünür; sunucu yanlış eşleşmeyi zaten yok sayar.
(function () {
  function fold(text) {
    return (text || "").replace(/İ/g, "i").replace(/I/g, "ı").toLocaleLowerCase("tr");
  }
  function sync(citySelect, districtSelect, clearSelection) {
    const city = fold(citySelect.value);
    districtSelect.querySelectorAll("optgroup").forEach(function (group) {
      const match = city !== "" && fold(group.dataset.city) === city;
      group.hidden = !match;
      group.disabled = !match;
    });
    if (clearSelection) districtSelect.value = "";
    districtSelect.disabled = city === "";
  }
  document.addEventListener("DOMContentLoaded", function () {
    const citySelect = document.querySelector("select[data-region-city]");
    const districtSelect = document.querySelector("select[data-region-district]");
    if (!citySelect || !districtSelect) return;
    sync(citySelect, districtSelect, false);
    citySelect.addEventListener("change", function () { sync(citySelect, districtSelect, true); });
  });
})();
