"""Экспорт иконок SkrepNet из SVG в PNG, favicon и обложку.

Запуск: python brand/export.py
Нужен установленный Chrome (или Edge) — он растрирует SVG в PNG.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DIR = Path(__file__).resolve().parent
SVG_DIR = BRAND_DIR / "svg"
PNG_DIR = BRAND_DIR / "png"

CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

ROUND_ICONS = {
    "skrepnet-plane": [512, 256, 128, 64, 32],
    "skrepnet-clip": [512, 256, 128, 64, 32],
    "skrepnet-samovar": [512, 256, 128, 64, 32],
}
SQUARE_ICONS = {
    "skrepnet-favicon": [512, 256, 192, 180, 128, 64, 32],
    "skrepnet-icon-maskable": [512, 192],
}


def find_browser() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    raise SystemExit("Не найден Chrome или Edge для растрирования SVG.")


def render_svg(browser: Path, svg: Path, out: Path, width: int, height: int) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--default-background-color=00000000",
                f"--window-size={width},{height}",
                f"--screenshot={out}",
                f"--user-data-dir={profile}",
                svg.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def circular_mask(size: int) -> Image.Image:
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def main() -> None:
    browser = find_browser()
    PNG_DIR.mkdir(parents=True, exist_ok=True)

    for name, sizes in {**ROUND_ICONS, **SQUARE_ICONS}.items():
        svg = SVG_DIR / f"{name}.svg"
        with tempfile.TemporaryDirectory() as tmp:
            master_path = Path(tmp) / f"{name}.png"
            render_svg(browser, svg, master_path, 512, 512)
            master = Image.open(master_path).convert("RGBA")
            if master.size != (512, 512):
                master = master.crop((0, 0, 512, 512))
            if name in ROUND_ICONS:
                master.putalpha(circular_mask(512))
            master.save(PNG_DIR / f"{name}-512.png")
            for size in sizes:
                result = master.resize((size, size), Image.LANCZOS)
                result.save(PNG_DIR / f"{name}-{size}.png")

    favicon_source = Image.open(PNG_DIR / "skrepnet-favicon-512.png").convert("RGBA")
    favicon_source.save(
        PNG_DIR / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
    )
    for size in (16, 32, 48):
        favicon_source.resize((size, size), Image.LANCZOS).save(PNG_DIR / f"favicon-{size}.png")

    # Обложка канала 1280x640 и OG-картинка для превью ссылки 1200x630
    cover_svg = SVG_DIR / "skrepnet-cover.svg"
    with tempfile.TemporaryDirectory() as tmp:
        cover_path = Path(tmp) / "cover.png"
        render_svg(browser, cover_svg, cover_path, 1280, 640)
        cover = Image.open(cover_path).convert("RGB")
        cover.save(PNG_DIR / "skrepnet-cover-1280x640.png")
        og = cover.resize((1260, 630), Image.LANCZOS).crop((30, 0, 1230, 630))
        og.save(PNG_DIR / "og-image-1200x630.png")

    print(f"Готово: {PNG_DIR}")


if __name__ == "__main__":
    main()
