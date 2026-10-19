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
