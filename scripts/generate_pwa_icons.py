#!/usr/bin/env python3
"""Generate PWA / favicon assets from assets/neo/neo_head.png."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "neo" / "neo_head.png"
OUT_DIR = ROOT / "web" / "public" / "icons"
NEO_PUBLIC = ROOT / "web" / "public" / "neo"
APP_DIR = ROOT / "web" / "app"
PUBLIC_DIR = ROOT / "web" / "public"


def remove_black_background(img: Image.Image, threshold: int = 28) -> Image.Image:
    """Make near-black pixels transparent (keeps dark face screen)."""
    rgba = img.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if r <= threshold and g <= threshold and b <= threshold:
                pixels[x, y] = (r, g, b, 0)
    return rgba


def fit_on_canvas(logo: Image.Image, size: int, padding_ratio: float = 0.08) -> Image.Image:
    pad = int(size * padding_ratio)
    inner = size - 2 * pad
    icon_src = logo.copy()
    icon_src.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - icon_src.width) // 2
    y = (size - icon_src.height) // 2
    canvas.paste(icon_src, (x, y), icon_src)
    return canvas


def make_icon(logo: Image.Image, size: int, filename: Path, padding_ratio: float = 0.08) -> None:
    canvas = fit_on_canvas(logo, size, padding_ratio)
    filename.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(filename, "PNG")
    print(f"wrote {filename}")


def make_favicon(logo: Image.Image) -> None:
    sizes = [16, 32, 48]
    frames = [fit_on_canvas(logo, s, padding_ratio=0.06) for s in sizes]
    APP_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = APP_DIR / "favicon.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"wrote {ico_path}")


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"source not found: {SRC}")

    logo = remove_black_background(Image.open(SRC))
    NEO_PUBLIC.mkdir(parents=True, exist_ok=True)
    logo.save(NEO_PUBLIC / "neo-head.png", "PNG")
    print(f"wrote {NEO_PUBLIC / 'neo-head.png'}")

    for size, name in [
        (32, "icon-32.png"),
        (180, "apple-touch-icon.png"),
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ]:
        make_icon(logo, size, OUT_DIR / name)

    make_favicon(logo)

    # Next.js App Router file-based metadata (auto-served, no 404 on /favicon.ico)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    fit_on_canvas(logo, 32).save(APP_DIR / "icon.png", "PNG")
    print(f"wrote {APP_DIR / 'icon.png'}")
    shutil.copy2(OUT_DIR / "apple-touch-icon.png", APP_DIR / "apple-icon.png")
    print(f"wrote {APP_DIR / 'apple-icon.png'}")


if __name__ == "__main__":
    main()
