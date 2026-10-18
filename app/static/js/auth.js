// Giriş ve kayıt sayfalarının küçük etkileşimleri.
// Not: Bunlar yalnızca kullanım kolaylığıdır. Asıl doğrulama sunucuda (Flask-WTF) yapılır.

document.addEventListener("DOMContentLoaded", function () {
  // 1) Parolayı göster / gizle
  document.querySelectorAll(".toggle-password").forEach(function (button) {
    button.addEventListener("click", function () {
      const input = document.getElementById(button.dataset.target);
      const icon = button.querySelector("i");
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      icon.className = isHidden ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });

  // 2) Kayıt formunda işletme alanlarını yalnızca "Üretici" seçilince göster
  const producerBox = document.getElementById("producer-fields");
  const roleInputs = document.querySelectorAll("#role-choices input[type=radio]");
  if (producerBox && roleInputs.length) {
    const update = function () {
      const selected = document.querySelector("#role-choices input[type=radio]:checked");
      producerBox.hidden = !selected || selected.value !== "producer";
    };
    roleInputs.forEach(function (input) { input.addEventListener("change", update); });
    update();
  }
});
