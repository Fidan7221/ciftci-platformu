"""Ön yüz kütüphanelerini (Bootstrap, Bootstrap Icons, Chart.js) app/static/vendor/ altına indirir (Hafta 13).

Çalıştırma (internet gerekir, bir kez yeterli):
    python scripts/download_assets.py

Sonrasında uygulama bu dosyaları internetsiz kullanır (masaüstü uygulaması, sunum).
Dosyalar zaten varsa yeniden indirilmez; --yeniden ile zorlanır.
Yalnızca Python standart kütüphanesi kullanılır (ek paket gerekmez).
"""
import argparse
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.assets import CDN_BASE, all_files  # noqa: E402

STATIC_DIR = os.path.join(ROOT, "app", "static")
TIMEOUT_SECONDS = 30


def download(url, target):
    request = urllib.request.Request(url, headers={"User-Agent": "TarladanSofraya-build"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec: sabit HTTPS adresi
        data = response.read()
    if not data:
        raise RuntimeError(f"Boş yanıt: {url}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".part"
    with open(temporary, "wb") as handle:     # yarım inen dosya asıl dosyanın yerine geçmesin
        handle.write(data)
    os.replace(temporary, target)
    return len(data)


def ensure_assets(static_dir=STATIC_DIR, force=False, log=print):
    """Eksik dosyaları indirir. İndirilemeyenlerin listesini döndürür (boş liste = tamam)."""
    failed = []
    for cdn_path, local_path in all_files():
        target = os.path.join(static_dir, local_path)
        if os.path.isfile(target) and not force:
            continue
        try:
            size = download(CDN_BASE + cdn_path, target)
            log(f"  indirildi  {local_path}  ({size // 1024} KB)")
        except Exception as error:  # ağ yok, proxy, 404...
            failed.append(local_path)
            log(f"  HATA       {local_path}: {error}")
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yeniden", action="store_true", help="Var olan dosyaları da yeniden indir")
    args = parser.parse_args(argv)
    print("Ön yüz dosyaları kontrol ediliyor...")
    failed = ensure_assets(force=args.yeniden)
    if failed:
        print("Bazı dosyalar indirilemedi. İnternet bağlantınızı kontrol edip tekrar deneyin.")
        return 1
    print("Tamam: tüm dosyalar app/static/vendor/ altında.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
