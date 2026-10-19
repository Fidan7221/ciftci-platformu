"""Masaüstü başlatıcısı (Hafta 13): çift tıklayınca sunucuyu başlatır ve uygulamayı açar.

Akış
----
1. Veri klasörünü bul/oluştur (Windows: %LOCALAPPDATA%\\TarladanSofraya). Veri tabanı, yüklenen görseller,
   loglar ve gizli anahtar BURADA durur; .exe'nin yanında değil. Böylece program güncellenince veya
   "Program Files" gibi yazılamayan bir yere kurulunca veriler kaybolmaz.
2. Uygulama zaten açıksa ikinci kopyayı başlatma; açık olanı tarayıcıda göster ve çık.
3. Gizli anahtarı (SECRET_KEY) ilk açılışta rastgele üret, dosyada sakla (oturumlar yeniden başlatmada düşmesin).
4. Flask uygulamasını "desktop" ayarlarıyla kur, veri tabanını hazırla (ilk açılışta demo verileriyle).
5. Sunucuyu YALNIZCA 127.0.0.1 üzerinde boş bir portta başlat (ağdaki başka bilgisayarlar erişemez).
6. Arayüzü aç: küçük kontrol penceresi + tarayıcı (varsayılan) ya da pywebview varsa masaüstü penceresi.
7. Pencere kapanınca sunucuyu düzgün kapat.

Bu modül Flask uygulamasını yalnızca main() içinde içe aktarır; yardımcı fonksiyonlar tek başına test edilebilir.
"""
import argparse
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_ID = "TarladanSofraya"
APP_TITLE = "Tarladan Sofraya"
HOST = "127.0.0.1"                      # asla 0.0.0.0 değil: yalnızca bu bilgisayar
PREFERRED_PORTS = range(5050, 5060)     # 5000 macOS'ta AirPlay'e ayrılmış olabilir
DB_FILE = "veri.db"
SECRET_FILE = "gizli_anahtar.txt"
INSTANCE_FILE = "calisiyor.json"
SECRET_BYTES = 32                       # 64 onaltılık karakter (SECRET_KEY kontrolü >= 32 ister)

log = logging.getLogger("desktop")


# --- Klasörler ve dosyalar ------------------------------------------------------------------

def data_dir(env=None, platform=None, home=None):
    """Kullanıcıya özel, yazılabilir veri klasörü. CIFTCI_DATA_DIR ile değiştirilebilir."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    home = Path(home) if home else Path.home()
    if env.get("CIFTCI_DATA_DIR"):
        return Path(env["CIFTCI_DATA_DIR"])
    if platform.startswith("win"):
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_ID
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_ID
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / "tarladan-sofraya"


def ensure_layout(base):
    base = Path(base)
    for sub in ("", "uploads", "logs"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def load_or_create_secret(base):
    """Dosyadaki anahtarı döndürür; yoksa ya da bozuksa yenisini üretip kaydeder."""
    path = Path(base) / SECRET_FILE
    try:
        value = path.read_text(encoding="ascii").strip()
        if len(value) >= 2 * SECRET_BYTES and all(c in "0123456789abcdef" for c in value):
            return value
    except (OSError, UnicodeDecodeError):
        pass
    value = secrets.token_hex(SECRET_BYTES)
    path.write_text(value, encoding="ascii")
    try:
        os.chmod(path, 0o600)           # Linux/macOS: yalnızca sahibi okuyabilir
    except OSError:
        pass
    return value


def desktop_overrides(base, secret):
    """create_app(..., overrides=...) için veri klasörüne işaret eden ayarlar."""
    base = Path(base)
    return {
        "SECRET_KEY": secret,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (base / DB_FILE).as_posix(),
        "UPLOAD_FOLDER": str(base / "uploads"),
        "LOG_DIR": str(base / "logs"),
    }


def resource_path(*parts):
    """Paket içindeki bir dosyanın yolu. PyInstaller dosyaları sys._MEIPASS altına açar."""
    root = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return Path(root).joinpath(*parts)


# --- Port ve tek kopya kontrolü -------------------------------------------------------------

def port_is_free(port, host=HOST):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(preferred=PREFERRED_PORTS, host=HOST):
    for port in preferred:
        if port_is_free(port, host):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:   # işletim sistemi boş port seçsin
        sock.bind((host, 0))
        return sock.getsockname()[1]


def health_ok(url, timeout=1.0):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/saglik", timeout=timeout) as response:
            return response.status == 200 and json.load(response).get("durum") == "ok"
    except Exception:
        return False


def running_instance(base):
    """Açık bir kopya varsa adresini, yoksa None döndürür. Eski (kapanmış) kayıt dosyası temizlenir."""
    path = Path(base) / INSTANCE_FILE
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        url = f"http://{HOST}:{int(info['port'])}/"
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if health_ok(url):
        return url
    path.unlink(missing_ok=True)
    return None


def write_instance(base, port):
    (Path(base) / INSTANCE_FILE).write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")


def remove_instance(base):
    (Path(base) / INSTANCE_FILE).unlink(missing_ok=True)


# --- Sunucu ------------------------------------------------------------------------------

class ServerThread:
    """WSGI sunucusunu arka planda çalıştırır. waitress kuruluysa onu (üretime uygun, çok iş parçacıklı),
    değilse Werkzeug'un sunucusunu kullanır. Flask'ın app.run() geliştirme sunucusu KULLANILMAZ."""

    def __init__(self, app, port, host=HOST):
        self.app, self.host, self.port = app, host, port
        self.url = f"http://{host}:{port}/"
        self.engine = None
        self._server = None
        self._thread = None

    def start(self):
        try:
            from waitress.server import create_server
            self._server = create_server(self.app, host=self.host, port=self.port, threads=6,
                                         ident=APP_TITLE)
            self.engine = "waitress"
            target = self._server.run
        except ImportError:
            from werkzeug.serving import make_server
            self._server = make_server(self.host, self.port, self.app, threaded=True)
            self.engine = "werkzeug"
            target = self._server.serve_forever
        self._thread = threading.Thread(target=target, name="wsgi-server", daemon=True)
        self._thread.start()
        return self

    def wait_until_ready(self, timeout=15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if health_ok(self.url, timeout=0.5):
                return True
            time.sleep(0.1)
        return False

    def shutdown(self):
        if self._server is None:
            return
        if self.engine == "waitress":
            self._server.task_dispatcher.shutdown(timeout=3)   # açık istekleri bitir, iş parçacıklarını durdur
            self._server.close()                               # dinlemeyi bırak; döngü sona erer
        else:
            self._server.shutdown()
        self._thread.join(timeout=5)
        self._server = None


# --- Arayüz ------------------------------------------------------------------------------

def open_ui(url, mode, base, on_reset=None):
    """mode: "pencere" (pywebview), "kontrol" (tkinter kontrol penceresi + tarayıcı), "konsol"."""
    if mode == "pencere":
        try:
            import webview  # pywebview: isteğe bağlı paket
        except ImportError:
            log.warning("pywebview kurulu değil; tarayıcı kullanılacak.")
        else:
            webview.create_window(APP_TITLE, url, width=1280, height=820, min_size=(900, 600))
            webview.start()
            return
    if mode in ("pencere", "kontrol"):
        try:
            from desktop.control_window import run_control_window
        except ImportError:                 # tkinter yok (bazı Linux kurulumları)
            log.warning("tkinter bulunamadı; konsol modunda devam ediliyor.")
        else:
            webbrowser.open(url)
            run_control_window(url, base)
            return
    webbrowser.open(url)
    print(f"{APP_TITLE} çalışıyor: {url}\nKapatmak için Ctrl+C.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def show_error(message):
    """Pencereli .exe'de konsol yoktur; hata kullanıcıya bir ileti kutusuyla gösterilir."""
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_TITLE} masaüstü uygulaması")
    parser.add_argument("--pencere", action="store_true", help="pywebview kuruluysa uygulamayı masaüstü penceresinde aç")
    parser.add_argument("--konsol", action="store_true", help="Kontrol penceresi olmadan, terminalde çalış")
    parser.add_argument("--port", type=int, default=None, help="Belirli bir port kullan")
    parser.add_argument("--demo-yok", action="store_true", help="İlk açılışta demo verisi ekleme")
    parser.add_argument("--sifirla", action="store_true", help="Tüm verileri silip temiz (demo) kurulum yap")
    parser.add_argument("--veri-klasoru", default=None, help="Veri klasörü (varsayılan: kullanıcı klasörü)")
    return parser.parse_args(argv)


def _setup_startup_log(base):
    handler = logging.FileHandler(Path(base) / "logs" / "baslatma.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    return handler


def main(argv=None):
    args = parse_args(argv)
    base = ensure_layout(Path(args.veri_klasoru) if args.veri_klasoru else data_dir())
    handler = _setup_startup_log(base)
    try:
        return _run(args, base)
    finally:
        log.removeHandler(handler)   # dosya açık kalmasın (Windows'ta açık dosya silinemez)
        handler.close()


def _run(args, base):
    log.info("Başlatılıyor. Veri klasörü: %s", base)

    url = running_instance(base)
    if url and args.sifirla:
        show_error("Uygulama şu anda açık. Verileri sıfırlamadan önce kontrol penceresinden kapatın.")
        return 1
    if url:
        log.info("Zaten açık: %s", url)
        webbrowser.open(url)
        return 0

    first_run = not (base / DB_FILE).exists()
    try:
        from app import create_app
        from app.bootstrap import prepare_database

        app = create_app("desktop", overrides=desktop_overrides(base, load_or_create_secret(base)),
                         instance_path=str(base))
        with app.app_context():
            summary = prepare_database(reset=args.sifirla, demo=(first_run or args.sifirla) and not args.demo_yok)
        log.info("Veri tabanı hazır: %s kullanıcı, %s ilan", summary["users"], summary["listings"])

        port = args.port or find_free_port()
        server = ServerThread(app, port).start()
        if not server.wait_until_ready():
            raise RuntimeError("Sunucu 15 saniye içinde yanıt vermedi.")
        write_instance(base, port)
        log.info("Sunucu hazır (%s): %s", server.engine, server.url)
    except Exception as error:
        log.exception("Başlatma hatası")
        show_error(f"{APP_TITLE} başlatılamadı:\n\n{error}\n\nAyrıntılar: {base / 'logs' / 'baslatma.log'}")
        return 1

    try:
        mode = "konsol" if args.konsol else ("pencere" if args.pencere else "kontrol")
        open_ui(server.url, mode, base)
    finally:
        remove_instance(base)
        server.shutdown()
        log.info("Kapatıldı.")
    return 0
