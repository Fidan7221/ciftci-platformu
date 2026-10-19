"""Masaüstü uygulamasının giriş noktası (Hafta 13).

Geliştirme sırasında:   python desktop_app.py            (kontrol penceresi + tarayıcı)
                        python desktop_app.py --pencere  (pywebview kuruluysa masaüstü penceresi)
                        python desktop_app.py --help
.exe olarak:            python build_exe.py   ->  dist/TarladanSofraya/TarladanSofraya.exe
"""
import os
import sys


def _fix_missing_streams():
    """Konsolsuz (--windowed) derlenen .exe'de sys.stdout / sys.stderr None'dır; print() ve bazı
    kütüphaneler bu yüzden çöker. Yazılanlar boşluğa gider; asıl kayıtlar log dosyalarındadır."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


if __name__ == "__main__":
    _fix_missing_streams()
    # .exe içinde .env dosyası yoktur ve olmamalıdır; masaüstü ayarları launcher'da verilir
    os.environ.setdefault("FLASK_ENV", "desktop")
    from desktop.launcher import main

    raise SystemExit(main())
