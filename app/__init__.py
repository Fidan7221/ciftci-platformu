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

from config import config_by_name
from app.extensions import csrf, db, login_manager, migrate


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    # instance/ klasörü yoksa oluştur (SQLite dosyası burada durur)
    os.makedirs(app.instance_path, exist_ok=True)

    # Eklentileri uygulamaya bağla
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # SQLite'ta ALTER TABLE için gerekli
    login_manager.init_app(app)
    csrf.init_app(app)

    # Modelleri içe aktar: Flask-Migrate tabloları ancak böyle görür
    from app import models  # noqa: F401

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
    from app.routes.producer_routes import producer_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(producer_bp)  # Hafta 6-7
    app.register_blueprint(admin_bp)     # Hafta 6, 8
    app.register_blueprint(market_bp)    # Hafta 7: pazar vitrini
    app.register_blueprint(cart_bp)      # Hafta 7: sepet
    app.register_blueprint(order_bp)     # Hafta 7: siparişler


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
