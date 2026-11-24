#!/usr/bin/env python3
"""Draws the home-screen app icon into site/icons/ (committed; site/build.py copies them).

The same pink pennant as the browser-tab favicon (site/build.py FAVICON), drawn sticker-book
style: ink outline and a hard offset shadow, on a cobalt tile. Phones can't use the SVG
favicon for a home-screen icon (iOS wants a PNG, Android a manifest icon), which is why a
bookmark used to land as a gray box with a letter in it.

The tile is full-bleed and opaque: iOS rounds the corners itself and turns transparency
black, and Android's maskable crop keeps only the centre circle (80% of the width), so all
the artwork sits inside that circle.

Run by hand after changing the design: python3 scripts/make_icons.py (needs Pillow).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "icons"

# Tokens from site/template.html :root
COBALT = "#2e4bf2"
INK = "#151a33"
PINK = "#ff6fb5"
LIME = "#c7f04a"

SIZES = {"apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}
SS = 4  # supersampling for smooth edges


def draw(size):
    n = 512 * SS
    s = n / 512  # design units are on a 512 grid
    img = Image.new("RGB", (n, n), COBALT)
    d = ImageDraw.Draw(img)

    k = 0.84  # shrink toward the centre so the maskable crop never clips the pole's knob

    def pt(x, y, dx=0, dy=0):
        return ((256 + (x + dx - 256) * k) * s, (256 + (y + dy - 256) * k) * s)

    line = round(14 * s * k)
    shadow = 16  # hard offset shadow, down and right

    # Pennant: pole on the left, flag notched on the right (the favicon's shape, scaled up)
    flag = [(150, 130), (390, 130), (322, 248), (390, 366), (150, 366)]
    pole = [(126, 102), (162, 102), (162, 418), (126, 418)]

    for shape in (flag, pole):  # shadows first, so the outlines sit on top
        d.polygon([pt(x, y, shadow, shadow) for x, y in shape], fill=INK)
    d.polygon([pt(x, y) for x, y in flag], fill=PINK, outline=INK, width=line)
    d.polygon([pt(x, y) for x, y in pole], fill=INK)
    # Lime knob on top of the pole
    r, cx, cy = 26, 144, 98
    d.ellipse([pt(cx - r + shadow * 0.6, cy - r + shadow * 0.6), pt(cx + r + shadow * 0.6, cy + r + shadow * 0.6)], fill=INK)
    d.ellipse([pt(cx - r, cy - r), pt(cx + r, cy + r)], fill=LIME, outline=INK, width=round(10 * s * k))

    # A football on the flag, with laces
    fx, fy, fw, fh = 236, 248, 64, 40
    d.ellipse([pt(fx - fw, fy - fh), pt(fx + fw, fy + fh)], fill=INK)
    lace = round(7 * s * k)
    d.line([pt(fx - 32, fy), pt(fx + 32, fy)], fill="white", width=lace)
    for dx in (-19, -6, 6, 19):
        d.line([pt(fx + dx, fy - 13), pt(fx + dx, fy + 13)], fill="white", width=lace)

    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in SIZES.items():
        draw(size).save(OUT / name, optimize=True)
        print(f"wrote site/icons/{name} ({size}x{size})")


if __name__ == "__main__":
    main()
