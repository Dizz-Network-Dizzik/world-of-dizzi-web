"""Erzeugt das Desktop-/App-Icon im Dizzi-Design (Mattmetall + Cyan/Magenta-Glow).

Motiv: ein Planet („the world") mit leuchtendem Orbit-Ring — Cyan-Welt,
Magenta-Orbit, auf gefräster Graphit-Platte mit abgerundeten Ecken.

Ausgabe: assets/dizzi.ico (16–256 px) + assets/dizzi_256.png (+ Favicon-Kopie
nach shell/public/favicon.png, falls der Ordner existiert).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024  # Render-Größe; Downscaling glättet alle Kanten
CY = (47, 231, 255)
MG = (255, 61, 240)

root = Path(__file__).resolve().parents[1]
assets = root / "assets"
assets.mkdir(exist_ok=True)


def _rounded_plate(img: Image.Image) -> None:
    """Matte Metallplatte mit vertikalem Verlauf, Brush-Linien und Kanten."""
    d = ImageDraw.Draw(img)
    r = int(S * 0.22)
    top, bottom = (30, 36, 48), (13, 16, 22)
    for y in range(S):
        t = y / S
        col = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        d.line([(0, y), (S, y)], fill=col)
    # Brush-Textur: feine helle Linien
    for y in range(0, S, 6):
        d.line([(0, y), (S, y)], fill=(255, 255, 255, 4))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=255)
    img.putalpha(mask)
    # gefräste Kanten: helle Ober-, dunkle Unterkante
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    de = ImageDraw.Draw(edge)
    de.rounded_rectangle([2, 2, S - 3, S - 3], radius=r, outline=(255, 255, 255, 34), width=6)
    de.rounded_rectangle([6, 10, S - 7, S - 3], radius=r, outline=(0, 0, 0, 90), width=6)
    img.alpha_composite(edge)


def _glow_layer(draw_fn, blur: int, alpha: float) -> Image.Image:
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    return layer


def main() -> None:
    img = Image.new("RGBA", (S, S))
    _rounded_plate(img)

    cx, cy_, R = S // 2, S // 2, int(S * 0.235)

    def draw_world(d: ImageDraw.ImageDraw) -> None:
        d.ellipse([cx - R, cy_ - R, cx + R, cy_ + R], outline=CY, width=int(S * 0.022))
        # Längen-/Breitengrade (die „Welt")
        d.ellipse([cx - R // 2, cy_ - R, cx + R // 2, cy_ + R], outline=CY, width=int(S * 0.012))
        d.line([cx - R, cy_, cx + R, cy_], fill=CY, width=int(S * 0.012))
        for f in (0.55, -0.55):
            yy = cy_ + int(R * f)
            half = int(R * math.sqrt(max(0.0, 1 - f * f)))
            d.line([cx - half, yy, cx + half, yy], fill=CY, width=int(S * 0.010))

    def draw_orbit(d: ImageDraw.ImageDraw) -> None:
        # Magenta-Orbit als gekippte Ellipse mit Satellit
        w, h = int(R * 1.95), int(R * 0.62)
        orbit = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        do = ImageDraw.Draw(orbit)
        do.ellipse([cx - w, cy_ - h, cx + w, cy_ + h], outline=MG, width=int(S * 0.020))
        rot = orbit.rotate(-24, center=(cx, cy_), resample=Image.BICUBIC)
        d._image.alpha_composite(rot)  # noqa: SLF001 — Komposition in den Ziel-Layer
        # Satellit auf dem Orbit (rechts oben), Position passend zur Rotation
        ang = math.radians(-24)
        px = cx + int(w * 0.92 * math.cos(math.radians(35)))
        py = cy_ - int(h * 0.92 * math.sin(math.radians(35)))
        qx = cx + int((px - cx) * math.cos(ang) - (py - cy_) * math.sin(ang))
        qy = cy_ + int((px - cx) * math.sin(ang) + (py - cy_) * math.cos(ang))
        rr = int(S * 0.030)
        d.ellipse([qx - rr, qy - rr, qx + rr, qy + rr], fill=MG)

    # Glow-Schichten zuerst (Licht), dann scharfe Linien (Lack-frei, nur Leuchten)
    img.alpha_composite(_glow_layer(draw_world, blur=int(S * 0.035), alpha=0.9))
    img.alpha_composite(_glow_layer(draw_orbit, blur=int(S * 0.035), alpha=0.85))
    sharp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sharp)
    draw_world(ds)
    draw_orbit(ds)
    img.alpha_composite(sharp)

    img256 = img.resize((256, 256), Image.LANCZOS)
    img256.save(assets / "dizzi_256.png")
    img256.save(
        assets / "dizzi.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    public = root / "shell" / "public"
    public.mkdir(exist_ok=True)
    img.resize((64, 64), Image.LANCZOS).save(public / "favicon.png")
    print(f"ok: {assets / 'dizzi.ico'}")


if __name__ == "__main__":
    main()
