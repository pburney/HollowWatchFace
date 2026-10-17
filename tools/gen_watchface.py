#!/usr/bin/env python3
"""
Hollow Watch Face generator -- a graveyard-at-night digital clock.

From Paul's own paper sketch (PXL_20261017_052609523.MACRO_FOCUS.jpg,
2026-10-17): four crenellated stone "tombstone" pillars show HH:MM, a
moon-phase icon sits top-left, a weather complication sits top-right,
ghosts drift out from among the stones and change "each minute", and the
night sky behind it all is scattered with stars.

One layout spec -> two outputs (same convention as every sibling in this
family -- BinaryWatchFace, QuinaryWatchFace, RadixWatchFace):
  * app/src/main/res/raw/watchface.xml   Wear OS Watch Face Format (WFF), v4
  * preview.html                          live browser preview, no build needed

Design decisions made while building this (see the approved plan at
~/.claude/plans/buzzing-riding-babbage.md for the full writeup):
  * Moon phase uses WFF's NATIVE [MOON_PHASE_TYPE] data source directly --
    confirmed via sourceType.xsd (moonPhaseSourceType, already present at
    format version 4, the version every sibling validates against). It is
    NOT a complication provider category (absent from
    defaultProviderPolicyElement.xsd's defaultProviderType enum), so unlike
    weather it needs no ComplicationSlot and no user setup.
  * Weather, by contrast, genuinely has no native on-device data source --
    WEATHER is likewise absent from defaultProviderType -- so it's a real
    ComplicationSlot with no DefaultProviderPolicy, the user assigns a
    provider in the watch face editor. wff_common.wff_complication_weather()
    is ported in UNMODIFIED from RadixWatchFace, already proven there.
  * `==` as a comparison operator is new ground for this family (every
    sibling so far only ever needed `>`/`!=` for cumulative fill-level or
    null checks) -- confirmed as a valid token in
    arithmeticExpressionType.xsd's _operatorType enum, used here for the 8-
    way moon-phase branch and the 6-way [MINUTE] % 6 ghost branch. Per this
    project's established discipline, schema validity alone has twice
    missed real on-device bugs before -- treat this as unverified until
    confirmed on Paul's Pixel Watch 5, not just because the validator
    passed.
  * No custom digit font: closely reading the sketch, the stones' silhouette
    is generic (crenellated rectangle) and only the ink numeral carries the
    actual digit -- so digits are plain <Text>, not hand-drawn glyphs. Saves
    a whole asset pipeline this face doesn't actually need.
  * Paint order matters (Quinary's old lesson, re-confirmed by Radix): the
    background/stars/stones/moon/ghost art is declared BEFORE the
    ComplicationSlots at the bottom of <Scene>, so the weather/date
    complications paint on top of (not under) everything else.
"""

import math
import random
from pathlib import Path

from wff_common import (
    CANVAS, C, WIDGET_W, WIDGET_H, WIDGET_Y, WIDGET_MARGIN_X,
    wff_complication_date, wff_complication_weather, JS_VALUE_FN, css_hex,
)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "app" / "src" / "main" / "res" / "raw" / "watchface.xml"
PREVIEW = ROOT / "preview.html"
PREVIEW_IMG = ROOT / "app" / "src" / "main" / "res" / "drawable" / "preview.png"
DRAWABLE = ROOT / "app" / "src" / "main" / "res" / "drawable"

# -- palette -----------------------------------------------------------
BG = "#FF0A0E1A"            # deep night-blue, not pure black
STONE_FILL = "#FF888C96"    # cool stone gray
STONE_OUTLINE = "#FF4A4D57"
INK = "#FF1C1A22"           # near-black carved numeral
STAR_COLOR = "#FFE8E6D8"
MOON_COLOR = (237, 230, 214, 255)   # warm cream, baked into the PNG directly
PANEL_FILL = "#FF14192A"    # subtle panel behind the moon/weather boxes

# -- stone layout --------------------------------------------------------
STONE_W, STONE_H = 72, 160
STONE_TOP_Y = 150
MERLON_DEPTH = 16
GAPS = [12, 24, 12]   # H-H, H-M (wider, reads as a colon gap), M-M
_total_w = 4 * STONE_W + sum(GAPS)
_start_x = C - _total_w / 2
STONE_X = []
_x = _start_x
for i in range(4):
    # Part-level x/y/width/height are xs:integer in the WFF schema (unlike
    # the float-typed x/y on the shape elements inside a PartDraw) --
    # round here once rather than re-discovering the type mismatch at
    # every call site that places a stone.
    STONE_X.append(round(_x))
    _x += STONE_W + (GAPS[i] if i < 3 else 0)

STONE_EXPRS = [
    "floor([HOUR_0_23] / 10)",
    "floor([HOUR_0_23] % 10)",
    "floor([MINUTE] / 10)",
    "floor([MINUTE] % 10)",
]

MOON_BOX_X, WEATHER_BOX_X = WIDGET_MARGIN_X, CANVAS - WIDGET_MARGIN_X - WIDGET_W


def build_stone(x: int, expr: str) -> str:
    seg_w = STONE_W / 5
    notch_y0, notch_y1 = STONE_TOP_Y, STONE_TOP_Y + MERLON_DEPTH
    notches = "".join(
        f'<Rectangle x="{x + seg_w * i:.1f}" y="{notch_y0}" width="{seg_w:.1f}" '
        f'height="{MERLON_DEPTH}"><Fill color="{BG}"/></Rectangle>'
        for i in (1, 3)
    )
    return (
        f'    <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'      <Rectangle x="{x}" y="{STONE_TOP_Y}" width="{STONE_W}" height="{STONE_H}">'
        f'<Stroke color="{STONE_OUTLINE}" thickness="3"/><Fill color="{STONE_FILL}"/></Rectangle>\n'
        f'      {notches}\n'
        f'    </PartDraw>\n'
        f'    <PartText x="{x}" y="{STONE_TOP_Y}" width="{STONE_W}" height="{STONE_H}">\n'
        f'      <Text align="CENTER">\n'
        f'        <Font family="SYNC_TO_DEVICE" size="64" weight="BLACK" color="{INK}">\n'
        f'          <Template>%d<Parameter expression="{expr}"/></Template>\n'
        f'        </Font>\n'
        f'      </Text>\n'
        f'    </PartText>'
    )


def build_stones() -> str:
    return "\n".join(build_stone(x, expr) for x, expr in zip(STONE_X, STONE_EXPRS))


# -- stars -----------------------------------------------------------
# Fixed, hand-scattered (deterministic seed) -- avoids the top widget boxes
# (y 48-116, x 98-218 / 232-352) and the stone band (y 150-310).
def _star_field():
    rnd = random.Random(20261017)
    pts = []
    # upper dome, above the widget boxes
    for _ in range(9):
        pts.append((rnd.uniform(20, 430), rnd.uniform(14, 42), rnd.uniform(1.4, 3.2)))
    # side margins, beside the stones
    for _ in range(8):
        side_x = rnd.choice([rnd.uniform(18, 50), rnd.uniform(400, 432)])
        pts.append((side_x, rnd.uniform(130, 360), rnd.uniform(1.2, 2.8)))
    # between stone band and the date complication
    for _ in range(4):
        pts.append((rnd.uniform(40, 410), rnd.uniform(330, 375), rnd.uniform(1.2, 2.4)))
    return pts


def build_stars() -> str:
    # Plain filled <Ellipse> -- simpler and more idiomatic than the
    # Arc+WeightedStroke pie-wedge trick used elsewhere in this family
    # (that trick exists specifically to dodge RoundRectangle's
    # corner-radius clamp, a problem a round dot doesn't have; Ellipse
    # supports <Fill> natively, confirmed via ellipseElement.xsd).
    out = []
    for x, y, r in _star_field():
        # Part-level x/y/width/height must be integers (see the STONE_X
        # comment above) -- round the PartDraw box, keep the inner
        # Ellipse's own float precision for the actual dot size/position.
        d = r * 2
        px, py, pw, ph = round(x - r), round(y - r), max(1, round(d)), max(1, round(d))
        out.append(
            f'    <PartDraw x="{px}" y="{py}" width="{pw}" height="{ph}">\n'
            f'      <Ellipse x="0" y="0" width="{d:.1f}" height="{d:.1f}"><Fill color="{STAR_COLOR}"/></Ellipse>\n'
            f'    </PartDraw>'
        )
    return "\n".join(out)


# -- moon phase icons --------------------------------------------------
# 8 buckets matching [MOON_PHASE_TYPE]: New, Waxing Crescent, First
# Quarter, Waxing Gibbous, Full, Waning Gibbous, Last Quarter, Waning
# Crescent. Classic two-overlapping-circles technique: a "light" disc, and
# a same-radius "dark" disc offset horizontally and subtracted from it --
# an approximation (the true terminator is an ellipse, not a circular arc)
# but reads correctly at icon scale, and keeps every phase's rendering
# code identical bar one offset/side parameter.
_MOON_OFFSET_MAG = [0.0, 0.29, 1.0, 1.71, 2.15]   # new..full, units of r


def _build_moon_icon(idx: int, out_path: Path, size: int = 72):
    from PIL import Image, ImageDraw, ImageChops
    SS = 4
    S = size * SS
    cx = cy = S / 2
    r = S * 0.42
    light = Image.new("L", (S, S), 0)
    ImageDraw.Draw(light).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    if idx <= 4:
        mag, side = _MOON_OFFSET_MAG[idx], -1
    else:
        mag, side = _MOON_OFFSET_MAG[8 - idx], 1
    if mag <= 0.001:
        lit = Image.new("L", (S, S), 0)
    elif mag >= 2.0:
        lit = light
    else:
        dark = Image.new("L", (S, S), 0)
        dcx = cx + side * mag * r
        ImageDraw.Draw(dark).ellipse([dcx - r, cy - r, dcx + r, cy + r], fill=255)
        lit = ImageChops.subtract(light, dark)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (S, S), MOON_COLOR), (0, 0), lit)
    # thin outline ring so "new moon" (fully dark) still reads as a shape,
    # not an empty box
    ImageDraw.Draw(img).ellipse([cx - r, cy - r, cx + r, cy + r],
                                 outline=(237, 230, 214, 120), width=int(S * 0.012))
    img.resize((size, size), Image.LANCZOS).save(out_path)


MOON_NAMES = ["new", "waxcres", "firstq", "waxgibb", "full", "wangibb", "lastq", "wancres"]


def build_moon_icons():
    for i, name in enumerate(MOON_NAMES):
        _build_moon_icon(i, DRAWABLE / f"moon_{name}.png")


def build_moon_group() -> str:
    icon = 44
    icon_x = MOON_BOX_X + (WIDGET_W - icon) // 2
    icon_y = WIDGET_Y + (WIDGET_H - icon) // 2
    panel = (
        f'    <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'      <RoundRectangle x="{MOON_BOX_X}" y="{WIDGET_Y}" width="{WIDGET_W}" height="{WIDGET_H}" '
        f'cornerRadiusX="12" cornerRadiusY="12"><Fill color="{PANEL_FILL}"/></RoundRectangle>\n'
        f'    </PartDraw>'
    )
    branches = []
    for i, name in enumerate(MOON_NAMES):
        branches.append(
            f'    <Condition>\n'
            f'      <Expressions>\n'
            f'        <Expression name="moon_{name}"><![CDATA[[MOON_PHASE_TYPE] == {i}]]></Expression>\n'
            f'      </Expressions>\n'
            f'      <Compare expression="moon_{name}">\n'
            f'        <PartImage x="{icon_x}" y="{icon_y}" width="{icon}" height="{icon}">\n'
            f'          <Image resource="moon_{name}"/>\n'
            f'        </PartImage>\n'
            f'      </Compare>\n'
            f'    </Condition>'
        )
    return panel + "\n" + "\n".join(branches)


def build_weather_panel() -> str:
    return (
        f'    <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'      <RoundRectangle x="{WEATHER_BOX_X}" y="{WIDGET_Y}" width="{WIDGET_W}" height="{WIDGET_H}" '
        f'cornerRadiusX="12" cornerRadiusY="12"><Fill color="{PANEL_FILL}"/></RoundRectangle>\n'
        f'    </PartDraw>'
    )


# -- ghosts --------------------------------------------------------------
# 6 pre-rasterized poses, one per [MINUTE] % 6 bucket -- changes every
# minute, no two adjacent minutes repeat, no real animation needed (WFF
# has none). Each gets its own fixed (x, y, size) near/above the stones so
# consecutive minutes read as genuinely different, not just a palette swap.
GHOST_PLACEMENTS = [
    (93, 146, 44),
    (177, 143, 38),
    (273, 149, 50),
    (357, 144, 40),
    (135, 147, 46),
    (315, 148, 48),
]


# Hand-tuned per-variant styling rather than pure random jitter -- a first
# pass driven only by a random seed (2-choice wave count, narrow amplitude
# range) produced 6 PNGs that were nearly indistinguishable at icon scale
# (caught by actually rendering a contact sheet of all 6, not just trusting
# "6 different seeds" was enough variety). Each variant now varies wave
# count/amplitude, body width (squish), eye style, and mouth -- enough to
# read as a different ghost at a glance, every minute.
GHOST_STYLES = [
    dict(n_waves=2, amp=0.035, width=1.00, eyes="dot", mouth="none"),
    dict(n_waves=4, amp=0.075, width=0.90, eyes="wide", mouth="o"),
    dict(n_waves=3, amp=0.050, width=1.12, eyes="sleepy", mouth="none"),
    dict(n_waves=5, amp=0.065, width=0.95, eyes="dot", mouth="smile"),
    dict(n_waves=2, amp=0.090, width=1.05, eyes="wide", mouth="none"),
    dict(n_waves=4, amp=0.045, width=0.88, eyes="sleepy", mouth="o"),
]


def _build_ghost_icon(style: dict, out_path: Path, size: int = 96):
    from PIL import Image, ImageDraw
    SS = 4
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = S / 2
    top_r = S * 0.30 * style["width"]
    top_cy = S * 0.33
    body_bottom = S * 0.80
    body_color = (242, 242, 248, 232)
    d.ellipse([cx - top_r, top_cy - top_r, cx + top_r, top_cy + top_r], fill=body_color)
    d.rectangle([cx - top_r, top_cy, cx + top_r, body_bottom], fill=body_color)
    n_waves, amp = style["n_waves"], S * style["amp"]
    pts = []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x = cx - top_r + t * (2 * top_r)
        y = body_bottom + amp * math.sin(t * n_waves * math.pi)
        pts.append((x, y))
    pts = [(cx - top_r, body_bottom)] + pts + [(cx + top_r, body_bottom)]
    d.polygon(pts, fill=body_color)

    ink = (35, 32, 48, 255)
    eye_dx = S * 0.10
    if style["eyes"] == "dot":
        r = S * 0.035
        for ex in (cx - eye_dx, cx + eye_dx):
            d.ellipse([ex - r, top_cy - r, ex + r, top_cy + r], fill=ink)
    elif style["eyes"] == "wide":
        rx, ry = S * 0.05, S * 0.06
        for ex in (cx - eye_dx, cx + eye_dx):
            d.ellipse([ex - rx, top_cy - ry, ex + rx, top_cy + ry], fill=ink)
    elif style["eyes"] == "sleepy":
        w = S * 0.045
        for ex in (cx - eye_dx, cx + eye_dx):
            d.line([ex - w, top_cy, ex + w, top_cy], fill=ink, width=max(2, int(S * 0.012)))

    if style["mouth"] == "o":
        r = S * 0.025
        d.ellipse([cx - r, top_cy + S * 0.09 - r, cx + r, top_cy + S * 0.09 + r], fill=ink)
    elif style["mouth"] == "smile":
        mw = S * 0.055
        d.arc([cx - mw, top_cy + S * 0.04, cx + mw, top_cy + S * 0.14], 20, 160,
              fill=ink, width=max(2, int(S * 0.012)))

    img.resize((size, size), Image.LANCZOS).save(out_path)


def build_ghost_icons():
    for i, style in enumerate(GHOST_STYLES):
        _build_ghost_icon(style, DRAWABLE / f"ghost_{i}.png")


def build_ghosts() -> str:
    out = []
    for i, (gx, gy, size) in enumerate(GHOST_PLACEMENTS):
        half = round(size / 2)
        out.append(
            f'    <Condition>\n'
            f'      <Expressions>\n'
            f'        <Expression name="ghost_{i}"><![CDATA[floor([MINUTE] % 6) == {i}]]></Expression>\n'
            f'      </Expressions>\n'
            f'      <Compare expression="ghost_{i}">\n'
            f'        <PartImage x="{gx - half}" y="{gy - half}" width="{size}" height="{size}">\n'
            f'          <Image resource="ghost_{i}"/>\n'
            f'        </PartImage>\n'
            f'      </Compare>\n'
            f'    </Condition>'
        )
    return "\n".join(out)


# -- preview thumbnail (gallery/picker) -----------------------------------
def build_preview_image():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (CANVAS, CANVAS), (10, 14, 26))
    d = ImageDraw.Draw(img)
    for x, y, r in _star_field():
        d.ellipse([x - r, y - r, x + r, y + r], fill=(232, 230, 216))
    for x in STONE_X:
        d.rectangle([x, STONE_TOP_Y, x + STONE_W, STONE_TOP_Y + STONE_H], fill=(136, 140, 150))
        d.rectangle([x, STONE_TOP_Y, x + STONE_W, STONE_TOP_Y + STONE_H], outline=(74, 77, 87), width=3)
        seg_w = STONE_W / 5
        for i in (1, 3):
            d.rectangle([x + seg_w * i, STONE_TOP_Y, x + seg_w * (i + 1), STONE_TOP_Y + MERLON_DEPTH],
                        fill=(10, 14, 26))
    digits = "1031"   # "a great time" per sibling precedent -- lively thumbnail
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
    except OSError:
        font = None
    for x, ch in zip(STONE_X, digits):
        d.text((x + STONE_W / 2, STONE_TOP_Y + STONE_H / 2), ch, fill=(28, 26, 34),
                anchor="mm", font=font)
    # a small full-moon + one ghost for a recognizable thumbnail
    d.ellipse([MOON_BOX_X + 38, WIDGET_Y + 12, MOON_BOX_X + 38 + 44, WIDGET_Y + 12 + 44],
               fill=(237, 230, 214))
    PREVIEW_IMG.parent.mkdir(parents=True, exist_ok=True)
    img.save(PREVIEW_IMG)


# -- assembly --------------------------------------------------------------
def build_wff() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_watchface.py - do not hand-edit. -->
<WatchFace width="{CANVAS}" height="{CANVAS}" clipShape="CIRCLE">
  <Metadata key="CLOCK_TYPE" value="DIGITAL"/>
  <Metadata key="PREVIEW_TIME" value="22:17:00"/>

  <Scene>
    <Group name="background" x="0" y="0" width="{CANVAS}" height="{CANVAS}">
      <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">
        <Rectangle x="0" y="0" width="{CANVAS}" height="{CANVAS}"><Fill color="{BG}"/></Rectangle>
      </PartDraw>
{build_stars()}
{build_stones()}
{build_ghosts()}
{build_moon_group()}
{build_weather_panel()}
    </Group>

    <!-- ComplicationSlots are direct Scene children, declared AFTER all
         the art above (Quinary's document-order lesson, re-confirmed in
         Radix: a background drawn after a ComplicationSlot silently
         paints over it). -->
{wff_complication_weather(WEATHER_BOX_X)}
{wff_complication_date()}
  </Scene>
</WatchFace>
"""


JS_MOON_FN = r"""function moonPhaseIndex(now) {
  // Standard synodic-month approximation (known new moon reference:
  // 2000-01-06 18:14 UTC), bucketed into the same 8 phases as
  // [MOON_PHASE_TYPE] on-device. Only used for the live browser preview --
  // the watch face itself reads the native WFF data source.
  const synodic = 29.530588853;
  const known = Date.UTC(2000, 0, 6, 18, 14, 0);
  const days = (now.getTime() - known) / 86400000;
  const phase = ((days % synodic) + synodic) % synodic / synodic;
  return Math.floor(phase * 8) % 8;
}"""

MOON_JS_NAMES = str(MOON_NAMES)


def build_html() -> str:
    stones_js = ",\n    ".join(
        f'{{x: {x}, expr: "{expr}"}}' for x, expr in zip(STONE_X, STONE_EXPRS)
    )
    ghosts_js = ",\n    ".join(
        f'{{x: {gx}, y: {gy}, size: {size}}}' for gx, gy, size in GHOST_PLACEMENTS
    )
    stars_js = ",\n    ".join(f'[{x:.1f}, {y:.1f}, {r:.2f}]' for x, y, r in _star_field())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hollow preview</title>
<style>
  body {{ background: #11131a; color: #ddd; font-family: sans-serif; text-align: center; }}
  canvas {{ background: {css_hex(BG)}; border-radius: 50%; margin-top: 1rem; }}
</style>
</head>
<body>
<h2>Hollow</h2>
<canvas id="c" width="{CANVAS}" height="{CANVAS}"></canvas>
<p id="readout"></p>
<script>
{JS_VALUE_FN}
{JS_MOON_FN}

const STONES = [
    {stones_js}
];
const GHOSTS = [
    {ghosts_js}
];
const STARS = [
    {stars_js}
];
const MOON_NAMES = {MOON_JS_NAMES};

const ctx = document.getElementById('c').getContext('2d');

function draw(now) {{
  const H = now.getHours(), M = now.getMinutes();
  ctx.clearRect(0, 0, {CANVAS}, {CANVAS});
  ctx.fillStyle = "{css_hex(BG)}";
  ctx.fillRect(0, 0, {CANVAS}, {CANVAS});

  ctx.fillStyle = "{css_hex(STAR_COLOR)}";
  for (const [x, y, r] of STARS) {{
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
  }}

  for (const s of STONES) {{
    ctx.fillStyle = "{css_hex(STONE_FILL)}";
    ctx.fillRect(s.x, {STONE_TOP_Y}, {STONE_W}, {STONE_H});
    ctx.strokeStyle = "{css_hex(STONE_OUTLINE)}"; ctx.lineWidth = 3;
    ctx.strokeRect(s.x, {STONE_TOP_Y}, {STONE_W}, {STONE_H});
    const segW = {STONE_W} / 5;
    ctx.fillStyle = "{css_hex(BG)}";
    for (const i of [1, 3]) {{
      ctx.fillRect(s.x + segW * i, {STONE_TOP_Y}, segW, {MERLON_DEPTH});
    }}
    ctx.fillStyle = "{css_hex(INK)}";
    ctx.font = "bold 56px sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const v = Math.floor(value(s.expr, now));
    ctx.fillText(String(v), s.x + {STONE_W} / 2, {STONE_TOP_Y} + {STONE_H} / 2);
  }}

  // ghost: minute-keyed, simple drawn silhouette (placement mirrors the
  // real asset's baked positions; shape is a quick canvas approximation,
  // not pixel-identical to the rasterized PNG -- fine for a layout check)
  const gi = Math.floor(M % 6);
  const g = GHOSTS[gi];
  ctx.fillStyle = "rgba(242,242,248,0.9)";
  ctx.beginPath();
  ctx.arc(g.x, g.y - g.size * 0.15, g.size * 0.3, Math.PI, 0);
  ctx.lineTo(g.x + g.size * 0.3, g.y + g.size * 0.3);
  ctx.lineTo(g.x, g.y + g.size * 0.2);
  ctx.lineTo(g.x - g.size * 0.3, g.y + g.size * 0.3);
  ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#282038";
  ctx.beginPath(); ctx.arc(g.x - g.size * 0.1, g.y - g.size * 0.15, g.size * 0.035, 0, 2 * Math.PI); ctx.fill();
  ctx.beginPath(); ctx.arc(g.x + g.size * 0.1, g.y - g.size * 0.15, g.size * 0.035, 0, 2 * Math.PI); ctx.fill();

  // moon + weather panels
  ctx.fillStyle = "{css_hex(PANEL_FILL)}";
  ctx.fillRect({MOON_BOX_X}, {WIDGET_Y}, {WIDGET_W}, {WIDGET_H});
  ctx.fillRect({WEATHER_BOX_X}, {WIDGET_Y}, {WIDGET_W}, {WIDGET_H});
  const mi = moonPhaseIndex(now);
  ctx.fillStyle = "#ede6d6";
  ctx.beginPath();
  ctx.arc({MOON_BOX_X} + {WIDGET_W} / 2, {WIDGET_Y} + {WIDGET_H} / 2, 18, 0, 2 * Math.PI);
  ctx.fill();
  ctx.fillStyle = "#999"; ctx.font = "10px sans-serif";
  ctx.fillText(MOON_NAMES[mi], {MOON_BOX_X} + {WIDGET_W} / 2, {WIDGET_Y} + {WIDGET_H} - 8);
  ctx.fillStyle = "#9ab"; ctx.font = "26px sans-serif";
  ctx.fillText("\\u2601", {WEATHER_BOX_X} + {WIDGET_W} / 2, {WIDGET_Y} + {WIDGET_H} / 2 - 4);
  ctx.font = "10px sans-serif"; ctx.fillStyle = "#999";
  ctx.fillText("(mock -- real device shows your weather provider)", {WEATHER_BOX_X} + {WIDGET_W} / 2, {WIDGET_Y} + {WIDGET_H} - 6);

  document.getElementById('readout').textContent =
    now.toTimeString().slice(0, 8) + "  ghost#" + gi + "  moon:" + MOON_NAMES[mi];
}}

function tick() {{ draw(window.__now ? window.__now() : new Date()); }}
tick();
setInterval(tick, 1000);
</script>
</body>
</html>
"""


def main():
    RAW.parent.mkdir(parents=True, exist_ok=True)
    DRAWABLE.mkdir(parents=True, exist_ok=True)
    build_moon_icons()
    build_ghost_icons()
    build_preview_image()
    RAW.write_text(build_wff(), encoding="utf-8")
    PREVIEW.write_text(build_html(), encoding="utf-8")
    print(f"wrote {len(MOON_NAMES)} moon icons, {len(GHOST_PLACEMENTS)} ghost icons")
    print(f"wrote {PREVIEW_IMG.relative_to(ROOT)}")
    print(f"wrote {RAW.relative_to(ROOT)}  ({len(RAW.read_text())} bytes)")
    print(f"wrote {PREVIEW.relative_to(ROOT)}   (open in a browser)")


if __name__ == "__main__":
    main()
