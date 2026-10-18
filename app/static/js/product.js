// Ürün formu: seçilen görseli yüklemeden önce önizle.
// Not: Önizleme yalnızca tarayıcıda olur; dosya türü ve boyutu sunucuda tekrar kontrol edilir.

document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("image");
  const preview = document.getElementById("image-preview");
  if (!input || !preview) return;

  input.addEventListener("change", function () {
    const file = input.files && input.files[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      alert("Görsel en fazla 5 MB olabilir.");
      input.value = "";
      return;
    }

    const img = document.createElement("img");
    img.className = "img-fluid rounded-3";
    img.alt = "Seçilen görselin önizlemesi";
    img.src = URL.createObjectURL(file);
    img.onload = function () { URL.revokeObjectURL(img.src); };
    preview.replaceChildren(img);
  });
});
