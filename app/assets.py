"""Ön yüz kütüphaneleri: yerel kopya mı, CDN mi? (Hafta 13)

Bootstrap, Bootstrap Icons ve Chart.js normalde CDN'den (cdn.jsdelivr.net) yüklenir. Masaüstü uygulaması
sunumda internetsiz açılabilir; o zaman sayfalar stilsiz, grafikler boş kalır. Bu yüzden:

- `python scripts/download_assets.py` dosyaları bir kez app/static/vendor/ altına indirir
  (build_exe.py bunu derlemeden önce kendisi çalıştırır).
- Şablonlar `{{ vendor_url("bootstrap_css") }}` kullanır: dosya yerelde varsa yerel adres, yoksa CDN adresi.
- VENDOR_ASSETS ayarı: "auto" (varsayılan), "local" (yalnızca yerel), "cdn" (yalnızca CDN).

Sürümler sabittir (5.3.3, 1.11.3, 4.4.1): yeni bir sürüm sessizce gelip arayüzü bozmasın.
"""
import os

from flask import url_for

CDN_BASE = "https://cdn.jsdelivr.net/npm/"
VENDOR_DIR = "vendor"   # app/static/vendor

# anahtar: (CDN'deki yol, static/ altındaki yerel yol)
ASSETS = {
    "bootstrap_css": ("bootstrap@5.3.3/dist/css/bootstrap.min.css", "vendor/bootstrap/bootstrap.min.css"),
    "bootstrap_js": ("bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js", "vendor/bootstrap/bootstrap.bundle.min.js"),
    "icons_css": ("bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
                  "vendor/bootstrap-icons/bootstrap-icons.min.css"),
    "chart_js": ("chart.js@4.4.1/dist/chart.umd.min.js", "vendor/chartjs/chart.umd.min.js"),
}

# Şablonda doğrudan kullanılmayan ama CSS'in göreli yolla istediği dosyalar (ikon yazı tipleri)
EXTRA_FILES = {
    "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2": "vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
    "bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff": "vendor/bootstrap-icons/fonts/bootstrap-icons.woff",
}


def all_files():
    """[(CDN yolu, yerel yol), ...] — indirilmesi gereken her şey."""
    return list(ASSETS.values()) + list(EXTRA_FILES.items())


def missing_files(static_folder):
    return [local for _, local in all_files() if not os.path.isfile(os.path.join(static_folder, local))]


def init_assets(app):
    mode = app.config.get("VENDOR_ASSETS", "auto")
    missing = missing_files(app.static_folder)
    if mode == "local" and missing:
        raise RuntimeError("Yerel ön yüz dosyaları eksik: " + ", ".join(missing) +
                           " — önce 'python scripts/download_assets.py' çalıştırın.")
    use_local = mode == "local" or (mode == "auto" and not missing)
    app.extensions["vendor_local"] = use_local

    def vendor_url(key):
        cdn_path, local_path = ASSETS[key]
        if app.extensions.get("vendor_local"):
            return url_for("static", filename=local_path)
        return CDN_BASE + cdn_path

    app.jinja_env.globals["vendor_url"] = vendor_url
