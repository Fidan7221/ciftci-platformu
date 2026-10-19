"""Sistem uç noktaları (Hafta 13).

/saglik            Sağlık kontrolü: uygulama ve veri tabanı ayakta mı? (izleme araçları, masaüstü başlatıcısı)
/medya/<dosya>     Kullanıcıların yüklediği ürün görselleri.

Neden yüklemeler /static altından değil de ayrı bir adresten veriliyor?
static/ uygulamanın kendi dosyalarıdır (CSS, JS) ve .exe paketinde salt-okunur bir klasöre gömülür.
Kullanıcı yüklemeleri ise değişen veridir; masaüstünde kullanıcının veri klasöründe, sunucuda ayrı bir
diskte durabilir. UPLOAD_FOLDER nerede olursa olsun bu adres doğru dosyayı verir.
"""
from flask import Blueprint, abort, current_app, jsonify, send_from_directory
from sqlalchemy import text

from app.extensions import db
from app.utils.uploads import get_extension

system_bp = Blueprint("system", __name__)


@system_bp.route("/saglik")
def health():
    database = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # bağlantı yok, dosya kilitli, disk dolu...
        db.session.rollback()
        current_app.logger.exception("Sağlık kontrolü: veri tabanına ulaşılamadı")
        database = "hata"
    status = 200 if database == "ok" else 503
    response = jsonify({
        "durum": "ok" if status == 200 else "hata",
        "uygulama": current_app.config["APP_NAME"],
        "surum": current_app.config["APP_VERSION"],
        "veritabani": database,
    })
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


@system_bp.route("/medya/<path:filename>")
def media(filename):
    # Yalnızca görsel uzantıları; send_from_directory klasör dışına çıkmayı (../) zaten engeller
    if get_extension(filename) not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, max_age=7 * 24 * 3600)
