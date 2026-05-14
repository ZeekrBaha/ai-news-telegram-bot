"""One-shot script to (re)generate the default hero banner PNG.

Run: uv run python -m src.scripts.generate_default_hero
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT_PATH = Path("assets/default_hero.png")
WIDTH, HEIGHT = 1280, 720
# Restrained editorial palette — pretends to be a magazine cover, not a tech demo.
GRADIENT_TOP = (18, 22, 30)      # near-black
GRADIENT_BOTTOM = (38, 46, 60)   # graphite
ACCENT = (210, 195, 140)         # muted gold rule
TITLE = "AI Дайджест"
SUBTITLE = "ежедневная сводка ключевых новостей"


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

    title_font = _load_font(108)
    subtitle_font = _load_font(34)

    title_bbox = draw.textbbox((0, 0), TITLE, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (WIDTH - title_w) // 2
    title_y = (HEIGHT - title_h) // 2 - 60
    draw.text((title_x, title_y), TITLE, fill=(240, 236, 220), font=title_font)

    # Thin accent rule under the title — quietly editorial.
    rule_w = 240
    rule_y = title_y + title_h + 36
    rule_x = (WIDTH - rule_w) // 2
    draw.rectangle((rule_x, rule_y, rule_x + rule_w, rule_y + 3), fill=ACCENT)

    subtitle_bbox = draw.textbbox((0, 0), SUBTITLE, font=subtitle_font)
    subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (WIDTH - subtitle_w) // 2
    subtitle_y = rule_y + 36
    draw.text((subtitle_x, subtitle_y), SUBTITLE, fill=(190, 195, 205), font=subtitle_font)

    image.save(OUTPUT_PATH, "PNG", optimize=True)
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
