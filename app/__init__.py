"""Uygulama fabrikası (Application Factory).

create_app() her çağrıldığında yeni bir Flask uygulaması üretir.
Testlerde farklı ayarlarla (TestingConfig) uygulama kurmayı sağlar.
"""
import os
from datetime import timedelta, timezone
from urllib.parse import urlparse

import click
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError

from config import DEV_SECRET_KEY, config_by_name
from app.extensions import csrf, db, login_manager, migrate
from app.security import init_security


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    # Hafta 11: Üretimde varsayılan / zayıf gizli anahtarla çalışmayı reddet.
    # SECRET_KEY bilinen bir değerse saldırgan oturum çerezini kendisi imzalayıp istediği kullanıcı olabilir.
    if config_name == "production" and (app.config["SECRET_KEY"] == DEV_SECRET_KEY
                                        or len(app.config["SECRET_KEY"] or "") < 32):
        raise RuntimeError("Üretim ortamında .env içinde en az 32 karakterlik rastgele bir SECRET_KEY tanımlayın.")

    # instance/ klasörü yoksa oluştur (SQLite dosyası burada durur)
    os.makedirs(app.instance_path, exist_ok=True)

    # Eklentileri uygulamaya bağla
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # SQLite'ta ALTER TABLE için gerekli
    login_manager.init_app(app)
    csrf.init_app(app)

    # Modelleri içe aktar: Flask-Migrate tabloları ancak böyle görür
    from app import models  # noqa: F401

    init_security(app)  # Hafta 11: güvenlik başlıkları, CSP nonce, sorgu sayacı
    register_blueprints(app)
    register_error_handlers(app)
    register_template_filters(app)
    register_context(app)
    register_cli_commands(app)

    return app


def register_template_filters(app):
    from app.utils.formatting import format_money, format_qty

    # Şablonda: {{ urun.stock_quantity|qty }} -> "12,5"   {{ siparis.total_amount|money }} -> "1.234,50 ₺"
    app.add_template_filter(format_qty, "qty")
    app.add_template_filter(format_money, "money")

    local_tz = timezone(timedelta(hours=app.config.get("DISPLAY_UTC_OFFSET_HOURS", 3)))

    @app.template_filter("datetime_tr")
    def format_datetime(value):
        """Veri tabanındaki UTC saati Türkiye saatine çevirip gösterir (Hafta 8 düzeltmesi).

        SQLite saat dilimi bilgisini saklamaz; okunan değer 'naive' gelir. Bu değerin
        UTC olduğunu biliyoruz (BaseModel.utcnow), önce UTC olarak işaretleyip sonra çeviriyoruz.
        """
        if not value:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(local_tz).strftime("%d.%m.%Y %H:%M")

    @app.template_filter("date_tr")
    def format_date(value):
        return value.strftime("%d.%m.%Y") if value else ""


def register_context(app):
    @app.context_processor
    def inject_app_info():
        """Tüm şablonlarda kullanılabilen genel bilgiler (alt bilgideki sürüm gibi)."""
        return {"app_name": app.config["APP_NAME"], "app_version": app.config["APP_VERSION"]}


def register_blueprints(app):
    from app.routes.admin_routes import admin_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.cart_routes import cart_bp
    from app.routes.main_routes import main_bp
    from app.routes.market_routes import market_bp
    from app.routes.order_routes import order_bp
    from app.routes.payment_routes import payment_bp
    from app.routes.price_routes import price_bp
    from app.routes.producer_routes import producer_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(producer_bp)  # Hafta 6-7
    app.register_blueprint(admin_bp)     # Hafta 6, 8
    app.register_blueprint(market_bp)    # Hafta 7: pazar vitrini
    app.register_blueprint(cart_bp)      # Hafta 7: sepet
    app.register_blueprint(order_bp)     # Hafta 7: siparişler
    app.register_blueprint(payment_bp)   # Hafta 9: ödeme
    app.register_blueprint(price_bp)     # Hafta 9: hal fiyatları


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        # MAX_CONTENT_LENGTH (5 MB) aşıldığında Flask 413 döndürür
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def too_many_requests(error):
        retry_after = error.description if isinstance(error.description, int) else 60
        response = app.make_response((render_template("errors/429.html", retry_after=retry_after), 429))
        response.headers["Retry-After"] = str(retry_after)
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        # Sayfa uzun süre açık kalınca CSRF anahtarının süresi dolar (Hafta 8).
        # Ham "400 Bad Request" yerine kullanıcıyı formun olduğu sayfaya geri gönderiyoruz.
        flash("Güvenlik anahtarının süresi doldu. Lütfen sayfayı yenileyip tekrar deneyin.", "warning")
        referrer = request.referrer or ""
        same_site = urlparse(referrer).netloc == request.host  # Yalnızca kendi sitemize geri dön
        return redirect(referrer if same_site else url_for("main.index"))

    @app.errorhandler(500)
    def server_error(error):
        # Yarım kalan bir veri tabanı işlemi sonraki istekleri bozmasın
        db.session.rollback()
        app.logger.exception("Beklenmeyen sunucu hatası: %s", request.path)
        return render_template("errors/500.html"), 500


def register_cli_commands(app):
    """Terminalden çalıştırılacak özel komutlar."""

    @app.cli.command("seed-db")
    def seed_db():
        """Rolleri ve temel kategorileri veri tabanına ekler."""
        from scripts.seed_data import seed_all

        seed_all()
        print("Başlangıç verileri eklendi.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Vize sunumu için demo hesapları, ürünleri ve ilanları ekler (Hafta 8)."""
        from scripts.demo_data import DEMO_PASSWORD, seed_demo as run

        accounts = run()
        print("Demo verileri hazır. Tüm hesapların parolası:", DEMO_PASSWORD)
        for role, email in accounts.items():
            print(f"  {role:<10} {email}")

    @app.cli.command("fetch-prices")
    @click.option("--days", default=1, show_default=True, help="Bugün dahil kaç günlük fiyat çekilsin")
    def fetch_prices(days):
        """Hal fiyatlarını sağlayıcıdan çekip market_prices tablosuna yazar (Hafta 9).

        Örnek: flask fetch-prices --days 60   (Hafta 10'daki tahmin modeli için geçmiş veri)
        """
        from app.services import price_service
        from app.services.errors import ServiceError

        try:
            result = price_service.backfill(days)
        except ServiceError as error:
            print(f"Hata: {error.message}")
            raise SystemExit(1)
        print(f"{result['days']} gün işlendi: {result['inserted']} yeni, {result['updated']} güncellenen, "
              f"{result['invalid']} hatalı satır.")

    @app.cli.command("predict-prices")
    def predict_prices():
        """Satıştaki tüm ürünler için 7 günlük yapay zekâ fiyat tahmini üretir (Hafta 10)."""
        from app.services import prediction_service

        result = prediction_service.generate_predictions()
        print(f"{result['products']} ürün incelendi: {result['saved']} tahmin kaydedildi, "
              f"{result['skipped']} ürün için yeterli fiyat verisi yok.")

    @app.cli.command("cancel-unpaid")
    @click.option("--hours", type=int, default=None, help="Varsayılan: UNPAID_ORDER_TIMEOUT_HOURS")
    def cancel_unpaid(hours):
        """Uzun süredir ödenmemiş siparişleri iptal eder, stokları serbest bırakır (Hafta 9)."""
        from app.services import order_service

        hours = hours or app.config["UNPAID_ORDER_TIMEOUT_HOURS"]
        count = order_service.cancel_unpaid_orders(hours)
        print(f"{hours} saatten eski {count} ödenmemiş sipariş iptal edildi.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Ad Soyad")
    @click.option("--email", prompt="E-posta")
    @click.password_option(prompt="Parola", confirmation_prompt="Parola (tekrar)")
    def create_admin(name, email, password):
        """Yönetici hesabı oluşturur (kayıt formundan yönetici açılamaz)."""
        from app.services.auth_service import AuthError, create_admin_user

        if len(password) < 8:
            print("Hata: Parola en az 8 karakter olmalıdır.")
            return
        try:
            create_admin_user(name, email, password)
        except AuthError as error:
            print(f"Hata: {error.message}")
        else:
            print(f"Yönetici hesabı oluşturuldu: {email}")
