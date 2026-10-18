"""Uygulama ayarları.

Ayarlar ortama göre üç sınıfa ayrılır:
- DevelopmentConfig: Geliştirme yaparken (hata ayıklama açık)
- TestingConfig:     pytest çalışırken (bellekte geçici veri tabanı)
- ProductionConfig:  Gerçek yayında (hata ayıklama kapalı)
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# .env dosyasındaki değişkenleri ortam değişkeni olarak yükle
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "evet", "on")


class Config:
    """Tüm ortamların ortak ayarları."""

    APP_NAME = "Tarladan Sofraya"
    APP_VERSION = "0.9.0"  # Git etiketiyle aynı tutulur: v0.9.0

    SECRET_KEY = os.environ.get("SECRET_KEY", "gelistirme-icin-gecici-anahtar")

    # Oturum çerezi güvenliği (Hafta 8)
    SESSION_COOKIE_HTTPONLY = True      # JavaScript çereze erişemez (XSS'e karşı)
    SESSION_COOKIE_SAMESITE = "Lax"     # Başka sitelerden gelen POST isteklerinde çerez gönderilmez
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Veri tabanında saatler UTC tutulur, ekranda Türkiye saatiyle (UTC+3) gösterilir.
    # Türkiye 2016'dan beri yaz/kış saati uygulamadığı için sabit fark yeterlidir.
    DISPLAY_UTC_OFFSET_HOURS = 3

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Ürün görseli yükleme (Hafta 6)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Sayfalama
    ITEMS_PER_PAGE = 12

    # --- Harici API ayarları (Hafta 9) -------------------------------------------
    # Anahtarlar ASLA koda yazılmaz; .env dosyasından (ortam değişkeni) okunur.
    # USE_MOCK_APIS=true iken internete hiç çıkılmaz, sahte (test) servisler kullanılır.
    USE_MOCK_APIS = _env_bool("USE_MOCK_APIS", True)

    PRICE_API_URL = os.environ.get("PRICE_API_URL", "")
    PRICE_API_KEY = os.environ.get("PRICE_API_KEY", "")
    PRICE_API_TIMEOUT = float(os.environ.get("PRICE_API_TIMEOUT", "10"))          # saniye
    PRICE_API_RATE_LIMIT_PER_MINUTE = int(os.environ.get("PRICE_API_RATE_LIMIT_PER_MINUTE", "30"))

    PAYMENT_API_URL = os.environ.get("PAYMENT_API_URL", "")
    PAYMENT_API_KEY = os.environ.get("PAYMENT_API_KEY", "")
    PAYMENT_SECRET_KEY = os.environ.get("PAYMENT_SECRET_KEY", "")   # istek imzası (HMAC) için
    PAYMENT_API_TIMEOUT = float(os.environ.get("PAYMENT_API_TIMEOUT", "15"))
    PAYMENT_CURRENCY = "TRY"

    # Kullanıcı tarafı hız sınırları (bizim sitemize gelen istekler)
    PAYMENT_ATTEMPTS_PER_10_MIN = int(os.environ.get("PAYMENT_ATTEMPTS_PER_10_MIN", "5"))
    PRICE_SYNC_PER_MINUTE = 3

    # Ödenmeyen siparişler bu süre sonra iptal edilir (flask cancel-unpaid), stok geri döner
    UNPAID_ORDER_TIMEOUT_HOURS = int(os.environ.get("UNPAID_ORDER_TIMEOUT_HOURS", "24"))


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False  # True yaparsanız üretilen SQL sorguları terminale yazılır


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # Testlerde form göndermeyi kolaylaştırır
    USE_MOCK_APIS = True      # Testler asla gerçek bir API'ye istek atmaz


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True   # Çerez yalnızca HTTPS üzerinden gönderilir
    REMEMBER_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
