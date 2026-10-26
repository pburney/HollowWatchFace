"""Generates HollowWatchFace's Play Store icon + feature graphic.

Reuses the real face's own geometry (_stone_pieces, GHOST_STYLES,
_build_ghost_icon, BG_LOOKUP) rather than redrawing the stone/ghost from
scratch -- the brand mark is the app's own core visual, same approach
RadixWatchFace took with its wedge-split circle.

Usage: python3 tools/gen_store_assets.py
Outputs to /data/BUSINESS/Burnilab/_store-assets/hollowwatchface/
(outside this repo, same convention as every sibling's store assets).
"""
from pathlib import Path
import math
import sys

sys.path.insert(0, str(Path(__file__).parent))
import gen_watchface as wf  # noqa: E402

OUT_DIR = Path("/data/BUSINESS/Burnilab/_store-assets/hollowwatchface")
SS = 4  # supersample factor for clean anti-aliasing, same as _build_ghost_icon


def _draw_stone(draw, scale, origin_x, origin_y):
    """Draws one stone (via the real _stone_pieces geometry) at `scale`,
    with its own top-left at (origin_x, origin_y)."""
    for dx, dy, w, h, color in wf._stone_pieces():
        draw.rectangle(
            [
                origin_x + dx * scale,
                origin_y + dy * scale,
                origin_x + (dx + w) * scale,
                origin_y + (dy + h) * scale,
            ],
            fill=_hex_to_rgb(color),
        )


def _hex_to_rgb(argb_hex: str):
    """WFF's #AARRGGBB -> PIL's (r, g, b)."""
    h = argb_hex.lstrip("#")
    return (int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))


def _stars(draw, w, h, n, rng_seed=7):
    import random

    rng = random.Random(rng_seed)
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.6)
        r = rng.uniform(1.5, 3.5)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 200))


def build_icon():
    from PIL import Image, ImageDraw

    size = 512 * SS
    img = Image.new("RGB", (size, size), _hex_to_rgb(wf.BG_LOOKUP["dark_indigo"]))
    d = ImageDraw.Draw(img)
    _stars(d, size, size, 28)

    scale = size / wf.STONE_W / 2.1  # stone fills a bit less than half the icon width
    stone_w_px = wf.STONE_W * scale
    stone_h_px = wf.STONE_H * scale
    ox = (size - stone_w_px) / 2
    oy = size * 0.56
    _draw_stone(d, scale, ox, oy)

    ghost_size = round(size * 0.46)
    ghost_path = Path("/tmp") / "hollow_icon_ghost.png"
    wf._build_ghost_icon(wf.GHOST_STYLES[1], ghost_path, size=ghost_size)
    ghost = Image.open(ghost_path).convert("RGBA")
    gx = round((size - ghost_size) / 2)
    gy = round(oy - ghost_size * 0.62)
    img.paste(ghost, (gx, gy), ghost)

    img = img.resize((512, 512), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUT_DIR / "icon-512.png")
    print(f"wrote {OUT_DIR / 'icon-512.png'}")


def build_feature_graphic():
    from PIL import Image, ImageDraw

    W, H = 1024 * SS, 500 * SS
    img = Image.new("RGB", (W, H), _hex_to_rgb(wf.BG_LOOKUP["dark_indigo"]))
    d = ImageDraw.Draw(img)
    _stars(d, W, H, 60, rng_seed=11)

    scale = H / wf.STONE_H / 2.6
    stone_w_px = wf.STONE_W * scale
    stone_h_px = wf.STONE_H * scale
    oy = H * 0.52

    # Three stones across the banner, each with its own ghost height --
    # reads as motion/variety across the width rather than one static icon.
    centers_frac = [0.22, 0.5, 0.78]
    rise_fracs = [0.35, 0.75, 0.15]  # how far each ghost has risen, 0=at stone, 1=fully up
    for cx_frac, rise in zip(centers_frac, rise_fracs):
        ox = W * cx_frac - stone_w_px / 2
        _draw_stone(d, scale, ox, oy)

        ghost_size = round(stone_w_px * 1.7)
        ghost_path = Path("/tmp") / "hollow_feature_ghost.png"
        wf._build_ghost_icon(wf.GHOST_STYLES[2], ghost_path, size=ghost_size)
        ghost = Image.open(ghost_path).convert("RGBA")
        gx = round(W * cx_frac - ghost_size / 2)
        start_gy = oy - ghost_size * 0.55
        end_gy = H * 0.04
        gy = round(start_gy + rise * (end_gy - start_gy))
        img.paste(ghost, (gx, gy), ghost)

    img = img.resize((1024, 500), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUT_DIR / "feature-graphic-1024x500.png")
    print(f"wrote {OUT_DIR / 'feature-graphic-1024x500.png'}")


if __name__ == "__main__":
    build_icon()
    build_feature_graphic()
