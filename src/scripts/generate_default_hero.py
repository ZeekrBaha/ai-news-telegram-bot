"""One-shot script to (re)generate the default hero banner PNG.

Run: uv run python -m src.scripts.generate_default_hero
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT_PATH = Path("assets/default_hero.png")
WIDTH, HEIGHT = 1280, 720
GRADIENT_TOP = (12, 18, 38)      # deep navy
GRADIENT_BOTTOM = (45, 78, 142)  # cobalt
TITLE = "🤖 AI Дайджест"
SUBTITLE = "ainewsdigestme"


def _vertical_gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), GRADIENT_TOP)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(GRADIENT_TOP[0] + (GRADIENT_BOTTOM[0] - GRADIENT_TOP[0]) * ratio)
        g = int(GRADIENT_TOP[1] + (GRADIENT_BOTTOM[1] - GRADIENT_TOP[1]) * ratio)
        b = int(GRADIENT_TOP[2] + (GRADIENT_BOTTOM[2] - GRADIENT_TOP[2]) * ratio)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return image


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = _vertical_gradient(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(96)
    subtitle_font = _load_font(40)

    title_bbox = draw.textbbox((0, 0), TITLE, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (WIDTH - title_w) // 2
    title_y = (HEIGHT - title_h) // 2 - 40
    draw.text((title_x, title_y), TITLE, fill=(255, 255, 255), font=title_font)

    subtitle_bbox = draw.textbbox((0, 0), SUBTITLE, font=subtitle_font)
    subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (WIDTH - subtitle_w) // 2
    subtitle_y = title_y + title_h + 40
    draw.text((subtitle_x, subtitle_y), SUBTITLE, fill=(200, 215, 240), font=subtitle_font)

    image.save(OUTPUT_PATH, "PNG", optimize=True)
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
