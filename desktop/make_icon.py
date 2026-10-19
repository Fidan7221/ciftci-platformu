"""Uygulama ikonunu üretir (Hafta 13): yeşil yuvarlak köşeli kare üzerinde beyaz fide.

Çalıştırma:  python desktop/make_icon.py
Çıktılar:
    desktop/icon.png             256x256 (masaüstü penceresi, belgeler)
    desktop/icon.ico             16-256 px çok boyutlu (Windows .exe ve kısayol ikonu)
    app/static/img/favicon.png   64x64 (tarayıcı sekmesi)
Gereksinim: Pillow (pip install pillow). Görsel kodla çizildiği için telif sorunu yoktur.
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIZE = 1024                      # büyük çizip küçültmek kenarları yumuşatır
TOP, BOTTOM = (61, 150, 66), (31, 90, 35)   # marka yeşili: #3d9642 -> #1f5a23
SOIL = (160, 112, 60)            # toprak: #a0703c (style.css --earth)


def _leaf(base, length, width, angle_deg, steps=60):
    """Tabanı `base` noktasında olan sivri uçlu yaprak çokgeni. Genişlik sin(pi*t) ile değişir."""
    angle = math.radians(angle_deg)
    ux, uy = math.cos(angle), -math.sin(angle)          # yaprak yönü (ekranda y aşağı doğru artar)
    nx, ny = -uy, ux                                     # yaprağa dik yön
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        half = width / 2 * math.sin(math.pi * t) ** 0.8
        cx, cy = base[0] + ux * length * t, base[1] + uy * length * t
        left.append((cx + nx * half, cy + ny * half))
        right.append((cx - nx * half, cy - ny * half))
    return left + right[::-1]


def draw_icon(size=SIZE):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Dikey renk geçişli zemin, yuvarlak köşeli maskeyle kesilir
    gradient = Image.new("RGBA", (size, size))
    pixels = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
        pixels.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    image.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(image)
    s = size / 1024
    white = (255, 255, 255, 255)

    # Toprak tümseği
    draw.pieslice([200 * s, 700 * s, 824 * s, 1000 * s], 180, 360, fill=SOIL)
    # Gövde
    draw.rounded_rectangle([490 * s, 455 * s, 534 * s, 800 * s], radius=22 * s, fill=white)
    # Yapraklar: gövdenin tepesinden çıkan sivri uçlu yaprak şekilleri
    base = (512 * s, 470 * s)
    draw.polygon(_leaf(base, length=300 * s, width=150 * s, angle_deg=150), fill=white)   # sol, yukarı
    draw.polygon(_leaf(base, length=380 * s, width=185 * s, angle_deg=35), fill=white)    # sağ, yukarı
    return image


def main():
    icon = draw_icon()
    os.makedirs(os.path.join(ROOT, "app", "static", "img"), exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "icon.png"))
    icon.resize((256, 256), Image.LANCZOS).save(
        os.path.join(HERE, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, "app", "static", "img", "favicon.png"))
    print("İkonlar üretildi: desktop/icon.png, desktop/icon.ico, app/static/img/favicon.png")


if __name__ == "__main__":
    main()
