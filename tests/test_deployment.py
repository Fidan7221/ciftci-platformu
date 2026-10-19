"""Hafta 13: Dağıtım, paketleme ve sistem entegrasyonu testleri.

Bölüm 1 — masaüstü başlatıcısı ve derleme betiği (uygulama kurulmadan): veri klasörü, gizli anahtar,
          port seçimi, gerçek bir sunucuyu başlatıp durdurma, tek kopya kontrolü, PyInstaller argümanları.
Bölüm 2 — üretim ayarları: log dosyası, istek kimliği, 500 sayfası, sağlık kontrolü, masaüstü ayarları.
Bölüm 3 — kurulum: prepare_database, `flask kurulum` komutu, yüklemelerin /medya adresinden verilmesi.
Bölüm 4 — uçtan uca: masaüstü başlatıcısı gerçek uygulamayla açılır, sağlık kontrolü geçer, düzgün kapanır.
Bölüm 5 — proje dosyaları: sürüm tutarlılığı, gereksinimler, .env.example'da gizli bilgi olmaması.

Çalıştırma: pytest -v tests/test_deployment.py
"""
import logging
import os
import re
import socket
import urllib.request
from pathlib import Path

import pytest

import build_exe
from app.logging_setup import LOG_FILE_NAME, new_request_id
from desktop import launcher
from tests.conftest import login, make_customer, make_product, make_producer

ROOT = Path(__file__).resolve().parent.parent
GOOD_SECRET = "a1" * 32


def text(response):
    return response.get_data(as_text=True)


# =====================================================================================
# 1. Masaüstü başlatıcısı ve derleme betiği
# =====================================================================================

def test_data_dir_per_operating_system(tmp_path):
    windows = launcher.data_dir(env={"LOCALAPPDATA": r"C:\Users\zeynep\AppData\Local"}, platform="win32")
    assert str(windows).replace("\\", "/").endswith("AppData/Local/TarladanSofraya")
    assert launcher.data_dir(env={}, platform="darwin", home=tmp_path) == \
        tmp_path / "Library" / "Application Support" / "TarladanSofraya"
    assert launcher.data_dir(env={}, platform="linux", home=tmp_path) == \
        tmp_path / ".local" / "share" / "tarladan-sofraya"
    assert launcher.data_dir(env={"CIFTCI_DATA_DIR": str(tmp_path)}, platform="win32") == tmp_path


def test_secret_key_is_created_once_and_reused(tmp_path):
    first = launcher.load_or_create_secret(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert launcher.load_or_create_secret(tmp_path) == first            # yeniden başlatmada oturumlar düşmez
    (tmp_path / launcher.SECRET_FILE).write_text("kisa", encoding="ascii")
    assert launcher.load_or_create_secret(tmp_path) != "kisa"           # bozuk dosya onarılır


def test_desktop_overrides_keep_all_writable_data_in_data_dir(tmp_path):
    settings = launcher.desktop_overrides(tmp_path, GOOD_SECRET)
    assert settings["SQLALCHEMY_DATABASE_URI"] == "sqlite:///" + (tmp_path / "veri.db").as_posix()
    for key in ("UPLOAD_FOLDER", "LOG_DIR"):
        assert Path(settings[key]).parent == tmp_path


def test_free_port_skips_a_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert not launcher.port_is_free(taken)
        chosen = launcher.find_free_port(preferred=[taken])
        assert chosen != taken and launcher.port_is_free(chosen)


def _tiny_app():
    from flask import Flask, jsonify
    tiny = Flask("tiny")
    tiny.add_url_rule("/saglik", "saglik", lambda: jsonify(durum="ok"))
    return tiny


def test_server_thread_starts_on_localhost_and_stops():
    server = launcher.ServerThread(_tiny_app(), launcher.find_free_port()).start()
    try:
        assert server.url.startswith("http://127.0.0.1:")                # yalnızca bu bilgisayar
        assert server.wait_until_ready(timeout=10)
        assert launcher.health_ok(server.url)
    finally:
        server.shutdown()
    assert not launcher.health_ok(server.url)


def test_second_launch_finds_running_instance_and_stale_file_is_cleaned(tmp_path):
    port = launcher.find_free_port()
    server = launcher.ServerThread(_tiny_app(), port).start()
    try:
        server.wait_until_ready(timeout=10)
        launcher.write_instance(tmp_path, port)
        assert launcher.running_instance(tmp_path) == f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()
    assert launcher.running_instance(tmp_path) is None                   # uygulama kapanmış
    assert not (tmp_path / launcher.INSTANCE_FILE).exists()


def test_cli_arguments():
    args = launcher.parse_args(["--pencere", "--port", "5055", "--demo-yok"])
    assert args.pencere and args.port == 5055 and args.demo_yok and not args.sifirla


def test_pyinstaller_arguments():
    args = build_exe.build_args()
    joined = " ".join(args)
    assert args[0] == "desktop_app.py" and "--windowed" in args and "--onedir" in args
    assert "--icon" in args and args[args.index("--icon") + 1].endswith("icon.ico")
    for data in ("app/templates", "app/static", "app/reports/fonts"):
        assert f"{os.pathsep}{data}" in joined                           # şablon, statik, PDF yazı tipi
    assert "sqlalchemy.dialects.sqlite" in args
    for secret_or_data in (".env", "instance", "uploads", "migrations", "tests"):
        assert secret_or_data not in joined                              # gizli/kişisel veri pakete girmez
    onefile = build_exe.build_args(onefile=True, console=True)
    assert "--onefile" in onefile and "--console" in onefile


def test_static_staging_excludes_user_uploads(tmp_path):
    (tmp_path / "app" / "static" / "css").mkdir(parents=True)
    (tmp_path / "app" / "static" / "css" / "style.css").write_text("body{}")
    (tmp_path / "app" / "static" / "uploads" / "products").mkdir(parents=True)
    (tmp_path / "app" / "static" / "uploads" / "products" / "kisisel.png").write_bytes(b"x")
    staged = Path(build_exe.stage_static(root=str(tmp_path), staging="build/_paket"))
    assert (staged / "css" / "style.css").exists()
    assert not (staged / "uploads").exists()


def test_desktop_shortcut_script_quotes_paths():
    script = build_exe.shortcut_script(r"C:\Users\O'Brien\dist\App.exe", r"C:\Users\O'Brien\Desktop\A.lnk",
                                       r"C:\x.exe,0", r"C:\Users\O'Brien\dist")
    assert "'C:\\Users\\O''Brien\\dist\\App.exe'" in script                # PowerShell tırnak kaçışı
    assert "CreateShortcut" in script and script.endswith("$s.Save()")


def test_icon_files_are_valid():
    ico = (ROOT / "desktop" / "icon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00" and int.from_bytes(ico[4:6], "little") >= 5   # çok boyutlu ICO
    assert (ROOT / "desktop" / "icon.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (ROOT / "app" / "static" / "img" / "favicon.png").exists()


def test_request_id_rejects_log_injection():
    assert new_request_id("abc12345-def") == "abc12345-def"
    for bad in ("kisa", "abc12345\nINFO sahte satir", "<script>alert(1)</script>", "x" * 100, None):
        generated = new_request_id(bad)
        assert re.fullmatch(r"[0-9a-f]{12}", generated)


# =====================================================================================
# 2. Üretim ayarları, log ve hata yönetimi
# =====================================================================================

def test_health_endpoint(client):
    response = client.get("/saglik")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    data = response.get_json()
    assert data == {"durum": "ok", "uygulama": "Tarladan Sofraya", "surum": data["surum"], "veritabani": "ok"}
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["surum"])


def test_health_endpoint_reports_database_failure(client, monkeypatch):
    from app.extensions import db

    def broken(*args, **kwargs):
        raise RuntimeError("disk dolu")
    monkeypatch.setattr(db.session, "execute", broken)
    response = client.get("/saglik")
    assert response.status_code == 503 and response.get_json()["veritabani"] == "hata"
    assert "disk dolu" not in text(response)                               # iç ayrıntı sızmaz


def test_every_response_carries_a_request_id(client):
    generated = client.get("/").headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{12}", generated)
    assert client.get("/", headers={"X-Request-ID": "proxy-1234-abcd"}).headers["X-Request-ID"] == "proxy-1234-abcd"
    assert client.get("/", headers={"X-Request-ID": "kötü id!"}).headers["X-Request-ID"] != "kötü id!"


def test_500_page_shows_error_code_but_no_internals(app, client):
    app.config["PROPAGATE_EXCEPTIONS"] = False        # testte hatalar normalde teste fırlatılır

    def explode():
        raise ZeroDivisionError("gizli iç ayrıntı")
    app.add_url_rule("/_hata_testi", "hata_testi", explode)

    response = client.get("/_hata_testi")
    page = text(response)
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] in page                      # kullanıcı bu kodu bildirir
    assert "ZeroDivisionError" not in page and "gizli iç ayrıntı" not in page and "Traceback" not in page


def _app_with_file_log(tmp_path, env="production", **extra):
    from app import create_app
    overrides = {"SECRET_KEY": GOOD_SECRET, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                 "LOG_DIR": str(tmp_path / "logs"), "WTF_CSRF_ENABLED": False, **extra}
    return create_app(env, overrides=overrides, instance_path=str(tmp_path / "instance"))


def _close_file_logs(app):
    from app.logging_setup import _remove_our_handlers
    _remove_our_handlers(app.logger)       # açık dosya kalmasın (Windows'ta geçici klasör silinemez)


def test_production_writes_rotating_log_file_without_query_strings(tmp_path):
    app = _app_with_file_log(tmp_path)
    try:
        with app.app_context():
            from app.extensions import db
            db.create_all()
            response = app.test_client().get("/saglik?q=gizli-arama")
        log_text = (tmp_path / "logs" / LOG_FILE_NAME).read_text(encoding="utf-8")
        request_id = response.headers["X-Request-ID"]
        assert f"[{request_id}]" in log_text and "GET /saglik -> 200" in log_text
        assert "gizli-arama" not in log_text                               # sorgu metni loglanmaz
        handler = next(h for h in app.logger.handlers if getattr(h, "_ciftci_handler", False))
        assert handler.maxBytes == 1_000_000 and handler.backupCount == 5
    finally:
        _close_file_logs(app)


def test_creating_apps_repeatedly_does_not_duplicate_log_handlers(tmp_path):
    first = _app_with_file_log(tmp_path)
    second = _app_with_file_log(tmp_path)
    try:
        ours = [h for h in second.logger.handlers if getattr(h, "_ciftci_handler", False)]
        assert len(ours) == 1
    finally:
        _close_file_logs(first)
        _close_file_logs(second)


def test_unknown_environment_name_is_rejected():
    from app import create_app
    with pytest.raises(ValueError):
        create_app("uretim")


def test_desktop_config(tmp_path):
    from app import create_app
    from app.bootstrap import prepare_database
    from app.extensions import db

    with pytest.raises(RuntimeError):                                     # anahtarsız açılmaz
        create_app("desktop", overrides={"SECRET_KEY": "kisa"})

    overrides = {**launcher.desktop_overrides(tmp_path, GOOD_SECRET), "WTF_CSRF_ENABLED": False}
    app = create_app("desktop", overrides=overrides, instance_path=str(tmp_path))
    try:
        assert not app.debug and app.config["USE_MOCK_APIS"] is True
        assert app.config["SESSION_COOKIE_SECURE"] is False                # http://127.0.0.1 üzerinde giriş çalışsın
        with app.app_context():
            prepare_database()
            make_customer("masaustu@test.com")
            client = app.test_client()
            response = client.post("/auth/login", data={"email": "masaustu@test.com", "password": "Parola123"})
            cookie = response.headers.get("Set-Cookie", "")
            assert "session=" in cookie and "Secure" not in cookie and "HttpOnly" in cookie
            assert "Müşteri Paneli" in text(client.get("/panel", follow_redirects=True))   # oturum çalışıyor
            db.session.remove()
            db.engine.dispose()                                           # veri.db dosyası serbest kalsın
        assert (tmp_path / "veri.db").exists()
    finally:
        _close_file_logs(app)


def test_vendor_assets_local_or_cdn(app, client):
    app.extensions["vendor_local"] = False
    assert "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" in text(client.get("/"))
    app.extensions["vendor_local"] = True
    page = text(client.get("/"))
    assert "/static/vendor/bootstrap/bootstrap.min.css" in page and "cdn.jsdelivr.net/npm/chart.js" not in page


def test_local_only_assets_fail_fast_when_missing(monkeypatch):
    from app import assets, create_app
    monkeypatch.setattr(assets, "missing_files", lambda folder: ["vendor/bootstrap/bootstrap.min.css"])
    with pytest.raises(RuntimeError, match="download_assets"):
        create_app("testing", overrides={"VENDOR_ASSETS": "local"})


# =====================================================================================
# 3. Kurulum ve medya
# =====================================================================================

def test_prepare_database_is_idempotent_and_reset_clears_data(app):
    from app.bootstrap import prepare_database
    from app.models import Category, User

    first = prepare_database()
    assert first["created_tables"] == [] and first["categories"] == Category.query.count() > 0
    make_customer("kalici@test.com")
    assert prepare_database()["users"] == 1                                # tekrar çalıştırmak veri silmez

    after_reset = prepare_database(reset=True)
    assert after_reset["reset"] and after_reset["users"] == 0 and User.query.count() == 0
    assert after_reset["categories"] > 0 and len(after_reset["created_tables"]) >= 14


def test_prepare_database_with_demo_data(app):
    from app.bootstrap import prepare_database
    result = prepare_database(demo=True)
    assert result["demo_accounts"]["Müşteri"] == "musteri@demo.com"
    assert result["orders"] > 10 and result["listings"] >= 5
    again = prepare_database(demo=True)
    assert (again["users"], again["orders"]) == (result["users"], result["orders"])   # kopya yok


def test_cli_kurulum_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["kurulum", "--demo"])
    assert result.exit_code == 0, result.output
    assert "Veri tabanı hazır" in result.output and "musteri@demo.com" in result.output

    refused = runner.invoke(args=["kurulum", "--sifirla"], input="n\n")
    assert refused.exit_code == 1                                          # onay verilmedi: hiçbir şey silinmez
    from app.models import User
    assert User.query.filter_by(email="musteri@demo.com").count() == 1

    result = runner.invoke(args=["kurulum", "--sifirla", "--evet"])
    assert result.exit_code == 0 and "önce tüm veriler silindi" in result.output
    assert User.query.count() == 0


def test_media_route_serves_uploads_and_blocks_traversal(app, client):
    folder = Path(app.config["UPLOAD_FOLDER"]) / "products"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "domates.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (folder / "not.txt").write_text("gizli")

    response = client.get("/medya/products/domates.png")
    assert response.status_code == 200 and response.data.startswith(b"\x89PNG")
    assert client.get("/medya/products/not.txt").status_code == 404        # yalnızca görsel uzantıları
    assert client.get("/medya/../config.py").status_code == 404
    assert client.get("/medya/products/..%2F..%2Fconfig.py").status_code == 404
    assert client.get("/medya/products/yok.png").status_code == 404


def test_product_images_use_media_url(client):
    from app.extensions import db
    profile = make_producer("ciftci@test.com")
    product = make_product(profile)
    product.image_path = "products/abc.png"
    db.session.commit()
    login(client, "ciftci@test.com")
    page = text(client.get("/uretici/urunler"))
    assert 'src="/medya/products/abc.png"' in page and "/static/uploads/" not in page


# =====================================================================================
# 4. Uçtan uca: masaüstü başlatıcısı
# =====================================================================================

def test_desktop_launcher_end_to_end(tmp_path, monkeypatch):
    """Gerçek uygulama, gerçek sunucu: başlat -> sağlık kontrolü -> pencere kapanır -> düzgün kapan."""
    seen = {}

    def fake_ui(url, mode, base, on_reset=None):        # kontrol penceresi yerine: kontrol et ve "kapat"
        seen["url"], seen["mode"] = url, mode
        seen["healthy"] = launcher.health_ok(url)
        seen["instance_file"] = (tmp_path / launcher.INSTANCE_FILE).exists()
        with urllib.request.urlopen(url + "pazar/", timeout=5) as response:
            seen["market_status"] = response.status
    monkeypatch.setattr(launcher, "open_ui", fake_ui)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: None)

    try:
        code = launcher.main(["--veri-klasoru", str(tmp_path), "--demo-yok", "--konsol"])
    finally:
        from app.logging_setup import _remove_our_handlers
        _remove_our_handlers(logging.getLogger("app"))

    assert code == 0
    assert seen["healthy"] and seen["instance_file"] and seen["market_status"] == 200
    assert seen["url"].startswith("http://127.0.0.1:") and seen["mode"] == "konsol"
    assert not (tmp_path / launcher.INSTANCE_FILE).exists()                # kapanınca kayıt silinir
    assert not launcher.health_ok(seen["url"])                             # sunucu durdu
    for name in ("veri.db", launcher.SECRET_FILE, "logs/baslatma.log", "logs/uygulama.log"):
        assert (tmp_path / name).exists(), name
    assert "Sunucu hazır" in (tmp_path / "logs" / "baslatma.log").read_text(encoding="utf-8")


# =====================================================================================
# 5. Proje dosyaları
# =====================================================================================

def test_version_is_consistent_everywhere():
    from config import Config
    version = Config.APP_VERSION
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M).group(1) == version
    assert f"`v{version}`" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_requirements_cover_runtime_and_build():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for package in ("flask", "waitress", "reportlab", "scikit-learn"):
        assert package in runtime
    assert "pyinstaller" in (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8").lower()
    assert "pyinstaller" not in runtime                                    # sunucuda derleyici gerekmez


def test_env_example_contains_no_real_secrets():
    values = dict(line.split("=", 1) for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#") and "=" in line)
    assert values["SECRET_KEY"].startswith("buraya")
    for key in ("PRICE_API_KEY", "PAYMENT_API_KEY", "PAYMENT_SECRET_KEY"):
        assert values[key] == ""


def test_gitignore_keeps_secrets_and_build_outputs_out():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for entry in (".env", "instance/", "logs/", "build/", "dist/", "*.spec", "app/static/uploads/"):
        assert entry in ignored, entry


def test_final_documents_exist():
    for name in ("FINAL_RAPORU.md", "FINAL_SOZLU_HAZIRLIK.md", "MASAUSTU_KILAVUZU.md"):
        assert len((ROOT / "docs" / name).read_text(encoding="utf-8")) > 1500, name
