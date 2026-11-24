#!/usr/bin/env python3
"""Draws the home-screen app icon into site/icons/ (committed; site/build.py copies them).

A pink pennant flying at a tilt with a tangerine football on it, drawn sticker-book style
(ink outline, hard offset shadow) on a cobalt tile. Phones can't use the SVG
favicon for a home-screen icon (iOS wants a PNG, Android a manifest icon), which is why a
bookmark used to land as a gray box with a letter in it.

The tile is full-bleed and opaque: iOS rounds the corners itself and turns transparency
black, and Android's maskable crop keeps only the centre circle (80% of the width), so all
the artwork sits inside that circle.

Run by hand after changing the design: python3 scripts/make_icons.py (needs Pillow).
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "icons"

# Tokens from site/template.html :root
COBALT = "#2e4bf2"
INK = "#151a33"
PINK = "#ff6fb5"
LIME = "#c7f04a"
TANGERINE = "#ff7a1a"

SIZES = {"apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}
SS = 4  # supersampling for smooth edges
TILT = 10  # degrees the flag leans back, like it's flying


def football_outline(cx, cy, length, height, steps=60):
    """A football's pointed-lens silhouette: two circular arcs meeting at the tips."""
    r = (length * length / 4 + height * height / 4) / height
    off = r - height / 2
    a = math.asin(length / 2 / r)
    top = [(cx + r * math.sin(t), cy - (r * math.cos(t) - off)) for t in (-a + 2 * a * i / steps for i in range(steps + 1))]
    bottom = [(cx + r * math.sin(t), cy + (r * math.cos(t) - off)) for t in (a - 2 * a * i / steps for i in range(steps + 1))]
    return top + bottom


def draw_art(n):
    """The pennant, pole and football on a transparent layer (512-unit grid, scaled to n)."""
    s = n / 512
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    xy = lambda pts: [(x * s, y * s) for x, y in pts]

    # Long triangular pennant; joint="curve" keeps the outline's corners solid
    flag = xy([(150, 95), (490, 250), (150, 405)])
    d.polygon(flag, fill=PINK)
    d.line(flag + flag[:2], fill=INK, width=round(14 * s), joint="curve")
    d.rectangle(xy([(124, 110), (160, 440)]), fill=INK)

    # Football toward the pennant's wide end, with laces and end stripes
    cx, cy, length, height = 248, 250, 148, 90
    d.polygon(xy(football_outline(cx, cy, length, height)), fill=TANGERINE, outline=INK, width=round(11 * s))
    w = round(height * 0.10 * s)
    for sx in (-0.30, 0.30):
        x = cx + sx * length
        d.line(xy([(x, cy - height * 0.27), (x, cy + height * 0.27)]), fill="white", width=w)
    lace = length * 0.24
    d.line(xy([(cx - lace, cy), (cx + lace, cy)]), fill="white", width=w)
    for i in range(4):
        x = cx - lace * 0.75 + i * lace * 0.5
        d.line(xy([(x, cy - height * 0.15), (x, cy + height * 0.15)]), fill="white", width=w)

    # Lime knob on top of the pole
    r, kx, ky = 26, 142, 104
    d.ellipse(xy([(kx - r, ky - r), (kx + r, ky + r)]), fill=LIME, outline=INK, width=round(10 * s))
    return layer.rotate(TILT, resample=Image.BICUBIC, center=(n / 2, n / 2))


def draw(size):
    n = 512 * SS
    art = draw_art(n)
    art = art.crop(art.getbbox())
    # Fit the art in a 290-unit box: inside Android's maskable circle, shadow included
    k = min(290 * SS / art.width, 290 * SS / art.height)
    art = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)

    img = Image.new("RGBA", (n, n), COBALT)
    ox, oy = (n - art.width) // 2 - 8 * SS, (n - art.height) // 2 - 8 * SS
    shadow = Image.new("RGBA", art.size, INK)  # hard offset shadow, down and right
    shadow.putalpha(art.split()[3])
    img.alpha_composite(shadow, (ox + 16 * SS, oy + 16 * SS))
    img.alpha_composite(art, (ox, oy))
    return img.convert("RGB").resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in SIZES.items():
        draw(size).save(OUT / name, optimize=True)
        print(f"wrote site/icons/{name} ({size}x{size})")


if __name__ == "__main__":
    main()
