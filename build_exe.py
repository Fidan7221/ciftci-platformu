"""Masaüstü uygulamasını Windows .exe olarak derler (Hafta 13) — PyInstaller.

Kullanım (proje klasöründe, sanal ortam etkinken):
    pip install -r requirements-desktop.txt
    python build_exe.py                 # dist/TarladanSofraya/TarladanSofraya.exe  (önerilen: klasör)
    python build_exe.py --tek-dosya     # dist/TarladanSofraya.exe (tek dosya; ilk açılış daha yavaş)
    python build_exe.py --konsol        # hata ayıklama: siyah konsol penceresi de açılır
    python build_exe.py --kisayol       # derledikten sonra masaüstüne kısayol oluşturur (Windows)

Adımlar:
1. Ön yüz dosyalarını (Bootstrap, ikonlar, Chart.js) indir — uygulama internetsiz çalışsın.
2. İkon yoksa üret.
3. static/ klasörünü KULLANICI YÜKLEMELERİ HARİÇ bir hazırlık klasörüne kopyala.
4. PyInstaller'ı çalıştır.
Pakete ASLA girmeyenler: .env (gizli anahtarlar), instance/ (geliştirme veri tabanı), static/uploads/,
tests/, migrations/. Masaüstü uygulaması kendi gizli anahtarını ve veri tabanını ilk açılışta üretir.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "TarladanSofraya"
ENTRY = "desktop_app.py"
ICON = os.path.join("desktop", "icon.ico")
STAGING = os.path.join("build", "_paket")
SEP = os.pathsep                      # PyInstaller --add-data ayırıcısı: Windows ";", diğerleri ":"

# Kodda dinamik (import ifadesi olmadan) yüklenen ya da PyInstaller'ın göremediği modüller
HIDDEN_IMPORTS = [
    "sqlalchemy.dialects.sqlite",
    "waitress",
    "email_validator",
    "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes",
]
# Pakete gerek olmayan, boyutu büyüten modüller
EXCLUDES = ["pytest", "_pytest", "matplotlib", "IPython", "notebook", "alembic.testing"]


def build_args(onefile=False, console=False, static_dir=None, icon=ICON, name=NAME):
    """PyInstaller argüman listesi (saf fonksiyon: testlerde kontrol edilir)."""
    static_dir = static_dir or os.path.join(STAGING, "static")
    args = [
        ENTRY,
        "--name", name,
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
        "--icon", icon,
        # Flask şablon ve statik dosyaları kodla aynı yerde arar: app/templates, app/static
        "--add-data", f"app/templates{SEP}app/templates",
        "--add-data", f"{static_dir}{SEP}app/static",
        "--add-data", f"app/reports/fonts{SEP}app/reports/fonts",   # PDF için Türkçe yazı tipi
        "--add-data", f"desktop/icon.png{SEP}desktop",
        "--collect-submodules", "app",
        "--collect-submodules", "scripts",
        "--collect-data", "reportlab",
    ]
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    return args


def stage_static(root=ROOT, staging=STAGING):
    """app/static -> build/_paket/static (uploads/ ve geçici dosyalar hariç)."""
    target = os.path.join(root, staging, "static")
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(os.path.join(root, "app", "static"), target,
                    ignore=shutil.ignore_patterns("uploads", "*.part", ".DS_Store", "Thumbs.db"))
    return target


def shortcut_script(target, shortcut, icon, workdir):
    """Masaüstü kısayolu oluşturan PowerShell komutu (Windows Script Host COM nesnesi)."""
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    return (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quote(shortcut)}); "
            f"$s.TargetPath = {quote(target)}; $s.WorkingDirectory = {quote(workdir)}; "
            f"$s.IconLocation = {quote(icon)}; $s.Description = 'Tarladan Sofraya'; $s.Save()")


def create_desktop_shortcut(exe_path):
    if not sys.platform.startswith("win"):
        print("Kısayol yalnızca Windows'ta otomatik oluşturulur.")
        return None
    desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    shortcut = os.path.join(desktop, "Tarladan Sofraya.lnk")
    command = shortcut_script(exe_path, shortcut, exe_path + ",0", os.path.dirname(exe_path))
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], check=True)
    return shortcut


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tarladan Sofraya .exe derleyici")
    parser.add_argument("--tek-dosya", action="store_true", help="Tek bir .exe dosyası üret")
    parser.add_argument("--konsol", action="store_true", help="Konsol penceresi de açılsın (hata ayıklama)")
    parser.add_argument("--kisayol", action="store_true", help="Derleme sonrası masaüstüne kısayol koy")
    parser.add_argument("--cdn", action="store_true", help="Ön yüz dosyalarını indirme (internet gerektirir)")
    args = parser.parse_args(argv)
    os.chdir(ROOT)

    if sys.version_info < (3, 10):
        print("Python 3.10 veya üstü gerekir.")
        return 1
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller kurulu değil:  pip install -r requirements-desktop.txt")
        return 1

    print("1/4 Ön yüz dosyaları (Bootstrap, ikonlar, Chart.js)...")
    if not args.cdn:
        from scripts.download_assets import ensure_assets
        if ensure_assets():
            print("    İndirilemedi. İnternet bağlantısını kontrol edin ya da --cdn ile derleyin "
                  "(o zaman uygulama internetsiz stilsiz görünür).")
            return 1

    print("2/4 İkon...")
    if not os.path.isfile(ICON):
        from desktop.make_icon import main as make_icon
        make_icon()

    print("3/4 Statik dosyalar hazırlanıyor (kullanıcı yüklemeleri hariç)...")
    static_dir = stage_static()

    print("4/4 PyInstaller çalışıyor (birkaç dakika sürebilir)...")
    pyinstaller.run(build_args(onefile=args.tek_dosya, console=args.konsol, static_dir=static_dir))

    exe = os.path.join(ROOT, "dist", f"{NAME}.exe" if args.tek_dosya else os.path.join(NAME, f"{NAME}.exe"))
    if not sys.platform.startswith("win"):
        exe = exe[:-4]
    print(f"\nHazır: {exe}")
    if args.kisayol:
        print(f"Masaüstü kısayolu: {create_desktop_shortcut(exe)}")
    else:
        print("Masaüstü kısayolu için: python build_exe.py --kisayol  (ya da .exe'ye sağ tık > Gönder > Masaüstü)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
