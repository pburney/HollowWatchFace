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

import colorsys
import math
import random
from pathlib import Path

from wff_common import (
    CANVAS, C, WIDGET_W, WIDGET_H, WIDGET_Y, WIDGET_MARGIN_X,
    wff_complication_date, wff_complication_weather, JS_VALUE_FN, css_hex,
    COMPLICATION_TINT,
)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "app" / "src" / "main" / "res" / "raw" / "watchface.xml"
PREVIEW = ROOT / "preview.html"
PREVIEW_IMG = ROOT / "app" / "src" / "main" / "res" / "drawable" / "preview.png"
DRAWABLE = ROOT / "app" / "src" / "main" / "res" / "drawable"

# -- palette -----------------------------------------------------------
BG = "#FF0A0E1A"            # deep night-blue, not pure black
GROUND_COLOR = "#FF000000"  # flat black ground band, bottom of the face
STONE_FILL = "#FF888C96"    # cool stone gray
# Edge lighting: a narrow highlight on the LEFT, a narrow shadow on the
# RIGHT -- Paul: "let's flip the two sides (light left, dark right)
# because of the moon position where it might actually cast the shadow"
# (the moon sits top-left of the face, so light hits the stones from the
# left, casting shadow on their right side).
STONE_HIGHLIGHT = "#FFB9BBC1"  # lighter gray, same hue/saturation as
                                # STONE_FILL (223deg/0.06) at L=0.74 vs.
                                # STONE_FILL's 0.56.
STONE_SHADOW = "#FF5E6169"  # darker gray, same hue/saturation at L=0.39.
STONE_DEEP_SHADOW = "#FF3A3C41"  # Paul: "one more band to the left of the
                                   # right dark band, even darker than the
                                   # one on the right" -- same hue/
                                   # saturation at L=0.24, sits between
                                   # STONE_FILL and STONE_SHADOW (which
                                   # stays the narrow strip right at the
                                   # edge).
STONE_OUTLINE = "#FF4A4D57"  # no longer drawn as a Stroke (Paul: remove the
                              # outlines) -- kept as a named constant in case
                              # it's wanted back, just unused below.
# History: ink used to track [CONFIGURATION.bgColor] (Paul: "make the text
# on the stones the sky 'black'" -- a "cutout showing the sky" effect).
# That broke once gradient backgrounds existed (no single scalar color to
# track), which got solved with a hand-picked ink per gradient -- then
# Paul's own follow-up replaced the whole mechanism: "use a dark gray for
# the numbers in general," for every bgColor/bgGradient option alike. One
# fixed, same-family-as-the-stone dark gray, not tied to any configuration.
DIGIT_INK = "#FF2A2C30"
STAR_COLOR = "#FFE8E6D8"
MOON_COLOR = (237, 230, 214, 255)   # warm cream, baked into the PNG directly

# Paul: "can the night background be user configurable?" -> v1 ported
# BinaryWatchFace's 16-option LED list (ANCHOR_COLORS), all forced to BG's
# own dark/muted lightness+saturation. On-device check ("try some brighter
# options too, maybe red and yellow") found that reads too washed-out --
# tried full brightness (too bright, read as daytime), then S/L=0.5/0.5
# (better, dusk-like). Paul's follow-up redesigns the whole list from
# scratch: "do .25 each and then have the full ROYGBIV spectrum named from
# the top: Red, Dark Red (.12 each), Orange, Dark Orange, etc, and at the
# end have Brown, Dark Brown, and then Gray Light (85%), Gray Medium (50%),
# Gray Dark (15%), Midnight (0,0,0)". Replaces ANCHOR_COLORS/_night_variant
# entirely -- no more "match BG's own darkness", every hue now gets an
# explicit hand-picked S/L.
#
# Reading of the spec: each ROYGBIV hue gets a normal entry at S=L=0.25 and
# a "Dark" entry 0.12 lower on both (S=L=0.13). Hue values are the standard
# color-wheel degrees for each ROYGBIV letter (R0/O30/Y60/G120/B240/I275/
# V300) rather than reused from the old anchor list, since that list is
# gone. "Brown" isn't a ROYGBIV hue -- no number was given for it, so it
# follows the same 0.25/0.13 S/L pattern as everything else, just at a
# distinct earthy hue (25 deg, between red and orange) so it doesn't read
# as a duplicate of Orange. Grays are S=0 at the literal percentages given;
# Midnight is literal RGB(0,0,0) -- pure black.
#
# Follow-up round (same session): "17 and 18 should be removed" (by
# position in this list -- Gray Light and Gray Medium) -- kept Gray Dark
# and Midnight, the two that actually read as "night". "For the 'dark'
# option increase the saturation to .25" -- only S moves, back up to match
# the normal entries' 0.25; L stays at 0.13, so the dark variants are still
# darker, just no longer desaturated/muddy. Briefly tried real color names
# per hue's dark entry (Maroon, Rust, Olive, Forest, Navy, Ink, Plum,
# Umber); walked back -- "change it from the actual color name with the
# dark modifier if it's the dark version" -- back to a plain "Dark {Hue}"
# label, S/L values unchanged from that round.
_ROYGBIV = [
    ("red", "Red", 0),
    ("orange", "Orange", 30),
    ("yellow", "Yellow", 60),
    ("green", "Green", 120),
    ("blue", "Blue", 240),
    ("indigo", "Indigo", 275),
    ("violet", "Violet", 300),
]
_BROWN_HUE = 25
_SPECTRUM_L, _SPECTRUM_S = 0.25, 0.25
_DARK_STEP_L = 0.12
_DARK_S = 0.25


def _hls_hex(hue_deg: float, lightness: float, saturation: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360, lightness, saturation)
    return "#FF" + "".join(f"{round(c * 255):02X}" for c in (r, g, b))


BG_OPTIONS = []
for _key, _display, _hue in _ROYGBIV + [("brown", "Brown", _BROWN_HUE)]:
    BG_OPTIONS.append((_key, _display, _hls_hex(_hue, _SPECTRUM_L, _SPECTRUM_S)))
    BG_OPTIONS.append((
        f"dark_{_key}", f"Dark {_display}",
        _hls_hex(_hue, _SPECTRUM_L - _DARK_STEP_L, _DARK_S),
    ))
# Paul: "make the current dark gray option to 'Grey' and then make a Grey
# Dark option that's like 85% gray" -- clarified via AskUserQuestion: the
# existing entry keeps its exact value (0.15 lightness), just renamed;
# "85%" means 85% darker than that, not 85% lightness -- GREY_DARK_L =
# GREY_L * (1 - 0.85), landing near-black but one step above Midnight.
_GREY_L = 0.15
_GREY_DARK_L = _GREY_L * (1 - 0.85)
BG_OPTIONS += [
    ("grey", "Grey", _hls_hex(0, _GREY_L, 0)),
    ("grey_dark", "Grey Dark", _hls_hex(0, _GREY_DARK_L, 0)),
    ("midnight", "Midnight", "#FF000000"),
]

# Default: closest to the original hand-picked night-blue (#FF0A0E1A) in
# this new list is the darkest indigo entry -- not pixel-identical (that
# guarantee only applied to the old anchor-list scheme), just the nearest
# available match.
BG_DEFAULT_INDEX = next(i for i, (key, _, _) in enumerate(BG_OPTIONS) if key == "dark_indigo")

# -- bgGradient (Paul: "is it possible to have a gradient option? Like a
# purple into black? Or a full dark rainbow?") ---------------------------
# A real WFF gradient (<LinearGradient> with 2-5 stops) exists and
# validates, but a gradient needs a *list* of color stops where bgColor's
# own picker only ever resolves to ONE scalar hex -- so bgGradient is a
# SEPARATE ListConfiguration (none/gradient/dark_rainbow, default "none"),
# layered on top of bgColor: when it's not "none" it visually overrides
# whatever bgColor is set to.
#
# Original (v1-v3) layout had bgGradient as the Scene's OUTER switch, with
# bgColor consumed inside via a `[CONFIGURATION.bgColor]` Fill expression
# -- simple, and it's how "none"/"gradient" still render conceptually.
# That inverted to bgColor-outer/bgGradient-inner (v4) once Dark Rainbow
# needed to know WHICH swatch was picked to rotate its color order --
# full history, including the on-device bugs each version hit, is in
# build_bg_switch's docstring below.
#
# Digit ink used to need per-branch handling here too (a gradient's stop
# list can't double as a scalar ink color the way bgColor's flat hex
# could) -- moot now that ink is a fixed dark gray regardless of which
# bgColor/bgGradient option is picked (Paul: "use a dark gray for the
# numbers in general"), so this block only has to solve the background
# fill, not ink.
BG_LOOKUP = {key: hex_ for key, _, hex_ in BG_OPTIONS}

_PURPLE_HUE = 285

# "Gradient" used to be a single fixed Purple Night option (one hardcoded
# top color fading to black). Paul: "could it take their selected color
# and use that as the top color then do the gradient down like the
# purple night one does now" -- so this is now DYNAMIC, keyed off
# whichever bgColor the user already picked, not a hardcoded hue. Every
# branch still just fades that color to pure black at the full canvas
# span (positions 0..1), which is why Purple Night never needed the
# GROUND_Y clipping fix Dark Rainbow needed below -- the gradient's own
# endpoint color already matches GROUND_COLOR, so there's no seam to hide.
GRADIENT_POSITIONS = [0.0, 1.0]

# Reuses the ALREADY-computed dark ROYGBIV hexes from BG_OPTIONS (not new
# colors) -- consistent "night" darkness, one spectrum feeding two
# features. All 7 ROYGBIV hues now (not a 5-stop subset -- see the
# rotation note below for why going back to 7 mattered).
# Paul: "we need to get to purple on dark rainbow" -- the night-palette
# dark_violet (S=0.25/L=0.13, same muted darkness as every other bgColor
# "Dark X" entry) doesn't read as clearly purple. Swapped the Violet slot
# to a dedicated, more saturated/lighter purple (_DARK_RAINBOW_PURPLE)
# instead of the bgColor dark_violet entry -- Paul's follow-up, once he
# saw it in person on the real OLED, "try to make the bottom purple pop",
# needed something more vivid than the deliberately muted "night" S/L
# values every bgColor option uses.
_DARK_RAINBOW_PURPLE = _hls_hex(_PURPLE_HUE, 0.42, 0.75)

# Paul: "use the initial hue as the rainbow start color? Like we do for
# the night gradient" -> shipped as a top-color tint fading into a FIXED
# R-Y-G-B-V order. Paul's follow-up made the actual ask explicit: "if I
# picked, e.g., Blue, I would get B-I-V-R-O-Y-G" -- a real rotation of the
# full ROYGBIV wheel, starting at whichever hue the user already picked,
# not just a tinted top stop over a fixed tail. _WHEEL_HUES is R-O-Y-G-B-
# I-V in canonical order (indices 0-6); _RAINBOW_WHEEL is the matching
# dark hex for each (Violet replaced with the more-saturated
# _DARK_RAINBOW_PURPLE per the "make it pop" fix above). A bgColor swatch
# whose own hue is on that wheel (its key, or its key with a leading
# "dark_" stripped) rotates the wheel to start there; an off-wheel swatch
# (brown/grey/midnight -- not a ROYGBIV hue) has no natural rotation, so
# it falls back to 0 (starts at Red, same as the un-rotated case).
_WHEEL_HUES = ["red", "orange", "yellow", "green", "blue", "indigo", "violet"]
_RAINBOW_WHEEL = [
    BG_LOOKUP["dark_red"], BG_LOOKUP["dark_orange"], BG_LOOKUP["dark_yellow"],
    BG_LOOKUP["dark_green"], BG_LOOKUP["dark_blue"], BG_LOOKUP["dark_indigo"],
    _DARK_RAINBOW_PURPLE,
]


def _rainbow_rotation_index(bgcolor_key: str) -> int:
    base = bgcolor_key[len("dark_"):] if bgcolor_key.startswith("dark_") else bgcolor_key
    return _WHEEL_HUES.index(base) if base in _WHEEL_HUES else 0


def _rotated_rainbow_colors(bgcolor_key: str):
    """7 dark ROYGBIV hexes, rotated to start at this swatch's own hue,
    plus a trailing duplicate of the last color -- the same explicit
    "never rely on gradient-stop extension" anchor fix as
    DARK_RAINBOW_POSITIONS below, so every rotation gets a real solid
    tail stop, not an inferred one."""
    r = _rainbow_rotation_index(bgcolor_key)
    rotated = _RAINBOW_WHEEL[r:] + _RAINBOW_WHEEL[:r]
    return rotated + [rotated[-1]]
# DARK_RAINBOW_POSITIONS is assembled further down, right after GROUND_Y
# is known -- see that comment for why.


def _gradient_fill_xml(colors, positions) -> str:
    colors_attr = " ".join(colors)
    positions_attr = " ".join(f"{p:.2f}" for p in positions)
    return (
        f'<LinearGradient startX="{C}" startY="0" endX="{C}" endY="{CANVAS}" '
        f'colors="{colors_attr}" positions="{positions_attr}"/>'
    )


# Declaration-only ids for the bgGradient picker (UserConfigurations) --
# the actual per-swatch rendering lives in _bg_color_gradient_branches,
# nested inside the bgColor Scene switch now (see build_bg_switch).
BG_GRADIENT_IDS = ["none", "gradient", "dark_rainbow"]


def build_bg_gradient_configuration() -> str:
    options = "\n".join(
        f'      <ListOption id="{key}" displayName="bggradient_{key}"/>'
        for key in BG_GRADIENT_IDS
    )
    return (
        f'    <ListConfiguration id="bgGradient" displayName="cfg_bggradient" defaultValue="none">\n'
        f'{options}\n'
        f'    </ListConfiguration>'
    )


def _flat_fill_group(name: str, fill: str, indent: str = "      ") -> str:
    return (
        f'{indent}<Group name="{name}" x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'{indent}  <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'{indent}    <Rectangle x="0" y="0" width="{CANVAS}" height="{CANVAS}">{fill}</Rectangle>\n'
        f'{indent}  </PartDraw>\n'
        f'{indent}</Group>'
    )


def _dynamic_overlay_group(key: str, base_fill: str, overlay_colors, positions) -> str:
    """Flat base_fill Rectangle, then a static LinearGradient overlay
    (transparent first stop, opaque after) composited on top -- shared by
    both the "gradient" (fade to black) and "dark_rainbow" (fade through
    rotated rainbow hues) branches of _bg_color_gradient_branches below.
    base_fill used to always be [CONFIGURATION.bgColor] (one flat
    expression reused across every swatch); now that bgColor itself is
    the OUTER Scene switch (see build_bg_switch), each swatch bakes in its
    own literal hex here instead. The overlay's Fill fallback color is its
    own last (opaque) stop, never the transparent first one -- see
    build_bg_switch's docstring for the on-device bug that requires
    this."""
    overlay = _gradient_fill_xml(overlay_colors, positions)
    return (
        f'          <Group name="bg_{key}" x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'            <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'              <Rectangle x="0" y="0" width="{CANVAS}" height="{CANVAS}"><Fill color="{base_fill}"/></Rectangle>\n'
        f'              <Rectangle x="0" y="0" width="{CANVAS}" height="{CANVAS}"><Fill color="{overlay_colors[-1]}">{overlay}</Fill></Rectangle>\n'
        f'            </PartDraw>\n'
        f'          </Group>'
    )


def _bg_color_gradient_branches(bgcolor_key: str, hex_: str) -> str:
    """One bgColor swatch's inner bgGradient switch (none/gradient/
    dark_rainbow), with this swatch's own literal hex baked into every
    branch -- see build_bg_switch for why bgColor had to become the outer
    switch to make "rotate the rainbow to start at my picked hue" possible
    at all.

    Wrapped in a <Group>: a <ListOption> can only hold ONE of
    {PartText/PartImage/PartAnimatedImage/PartDraw, Group, Condition,
    AnalogClock, DigitalClock} per listConfigurationElement.xsd --
    <ListConfiguration> itself isn't in that list, so nesting one
    directly inside a <ListOption> fails XSD validation outright (caught
    offline this time, not just on-device). <Group> IS in that list, and
    groupElement.xsd confirms <Group> can itself hold a <ListConfiguration>
    -- so the inner switch has to go through a Group wrapper."""
    none_content = _flat_fill_group(f"bg_{bgcolor_key}_none", f'<Fill color="{hex_}"/>',
                                     indent="          ")
    gradient_content = _dynamic_overlay_group(
        f"{bgcolor_key}_gradient", hex_, ["#00000000", "#FF000000"], GRADIENT_POSITIONS,
    )
    rainbow_colors = _rotated_rainbow_colors(bgcolor_key)
    rainbow_overlay = ["#00000000"] + rainbow_colors[1:]
    rainbow_content = _dynamic_overlay_group(
        f"{bgcolor_key}_dark_rainbow", hex_, rainbow_overlay, DARK_RAINBOW_POSITIONS,
    )
    inner_switch = (
        f'          <ListConfiguration id="bgGradient">\n'
        f'            <ListOption id="none">\n{none_content}\n            </ListOption>\n'
        f'            <ListOption id="gradient">\n{gradient_content}\n            </ListOption>\n'
        f'            <ListOption id="dark_rainbow">\n{rainbow_content}\n            </ListOption>\n'
        f'          </ListConfiguration>'
    )
    return (
        f'        <Group name="bg_{bgcolor_key}_switch" x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'{inner_switch}\n'
        f'        </Group>'
    )


def build_bg_switch() -> str:
    """Scene-level ListConfiguration switch for the background Rectangle --
    placed where the old unconditional background Rectangle used to sit,
    BEFORE stars/stones/ghosts so it still paints first.

    The OUTER switch here is bgColor (one branch per swatch), with
    bgGradient (none/gradient/dark_rainbow) nested inside EACH -- inverted
    from the original layout (outer bgGradient, flat [CONFIGURATION.
    bgColor] expression inside). History of why:

    v1: bgGradient outer, bgColor as a plain ColorConfiguration consumed
    via [CONFIGURATION.bgColor] Fill expressions -- worked fine for "none"
    and the "gradient" (one dynamic top color fading to black) branches.

    v2 attempt, for "Dark Rainbow, starting at my picked hue": tried
    nesting a SECOND ListConfiguration inside the "gradient" branch, keyed
    id="bgColor" (same id as the top-level ColorConfiguration), one
    ListOption per swatch -- valid per the offline WFF v4 XSD validator
    (ListConfiguration is a legal Group child) but WRONG on the real
    device: Paul reported the gradient area rendered solid black
    everywhere, with the selected color only visible at the stone notches.
    Root cause: the real renderer doesn't bind a Scene-level
    ListConfiguration to a configuration that was declared as
    ColorConfiguration, not ListConfiguration, in UserConfigurations --
    the XSD doesn't encode that constraint, so it validates clean while
    doing nothing at runtime.

    v2 real fix (shipped, still true for "none"/"gradient" conceptually):
    don't branch on bgColor at all -- paint the selected color FLAT via
    [CONFIGURATION.bgColor], then composite a SECOND, fully static
    Rectangle on top with a literal transparent-to-black LinearGradient
    (#00000000 -> #FF000000, no data source involved) to fade it toward
    the ground. Alpha-over-flat-color is the same compositing technique
    the ghosts already use for their body transparency.

    v2's own on-device bug, found immediately after: the overlay showed
    nothing at all -- Paul reported "just showing the first color all
    through", i.e. uniformly, no fade anywhere, as if the overlay
    Rectangle weren't drawn. Its `Fill`'s REQUIRED fallback `color` was
    "#00000000" (fully transparent, matching the gradient's own first
    stop). Likely cause: the renderer treats a fully transparent fallback
    as "nothing to draw" and skips the shape entirely, LinearGradient
    child included. Fix: give the fallback the gradient's own OPAQUE end
    stop instead -- still in place in _dynamic_overlay_group above.

    v3 ("use the initial hue as the rainbow start color?"): tinted just
    the TOP stop with the picked color, kept a FIXED tail order
    underneath. Worked, but Paul's real ask was a true rotation ("if I
    picked Blue, I'd get B-I-V-R-O-Y-G") -- the tail order itself has to
    depend on which swatch was picked, which v2's architecture can't do
    (bgColor was still a flat-color ColorConfiguration expression, not
    something Scene logic can branch on -- that's exactly what v2 attempt
    above found doesn't bind).

    v4 (this version): since the ONLY proven way to branch Scene content
    on a picked value is a ListConfiguration whose id/type matches its
    UserConfigurations declaration exactly (confirmed by what went wrong
    in the v2 attempt), bgColor itself becomes a ListConfiguration (see
    the UserConfigurations builder) instead of a ColorConfiguration. That
    makes [CONFIGURATION.bgColor] stop being a usable literal-color
    expression entirely, so EVERY branch that used it (not just Dark
    Rainbow) now needs its own swatch's hex baked in directly at build
    time -- hence bgColor has to be the OUTER switch, with the existing
    bgGradient 3-way logic nested inside each of its 19 branches instead
    of the other way around. Mechanically generated (_bg_color_gradient_
    branches), not hand-duplicated, but it is new, bigger structure (19x3
    branches instead of 1x3) with its own on-device risk, same as every
    other "validates clean, real behavior unverified" change this
    project's hit before -- needs the same real-device check."""
    branches = []
    for key, _display, hex_ in BG_OPTIONS:
        inner = _bg_color_gradient_branches(key, hex_)
        branches.append(f'      <ListOption id="{key}">\n{inner}\n      </ListOption>')
    return '    <ListConfiguration id="bgColor">\n' + "\n".join(branches) + '\n    </ListConfiguration>'

# -- stone layout --------------------------------------------------------
# Dimensions first, independent of ground position -- GROUND_Y below now
# needs STONE_H.
STONE_W, STONE_H = 72, 80

# -- ground --------------------------------------------------------------
# History: v1 a plain band at the bottom; v2 "extend up another third of
# the way up the screen" -> top edge raised by CANVAS/3; v3 "bring
# horizon line down one tombstone height" -> += STONE_H.
_GROUND_Y_V2 = 390 - round(CANVAS / 3)
GROUND_Y = _GROUND_Y_V2 + STONE_H
GROUND_H = CANVAS - GROUND_Y

# Dark Rainbow's positions depend on GROUND_Y, so they're assembled here,
# not back with _RAINBOW_WHEEL -- found via two rounds of on-device
# feedback:
# 1. The background LinearGradient spans the FULL canvas height (0-450),
#    but the opaque black ground Rectangle covers y>=GROUND_Y (320) --
#    stops placed in that bottom ~29% were never visible at all. Paul's
#    "get to purple" swap of the last stop landed exactly there --
#    invisible regardless of color. Fix (still in place): positions are
#    defined 0..1 across the VISIBLE sky only, then scaled by GROUND_Y/
#    CANVAS, so every stop -- including the final purple -- actually
#    lands above the ground line.
# 2. With that fixed, Paul: "looks too green somehow" -- correctly called
#    out before I'd even finished explaining why (red/yellow/green sit
#    next to each other on the color wheel, plus the eye is most sensitive
#    to green, so an even split reads green-dominant). Tried compressing
#    red/yellow/green into a short band to give blue/purple more room --
#    Paul's own side-by-side verdict once fix #1 alone was visible: the
#    plain EVEN split actually reads better ("I love this one now") -- the
#    compression was solving a problem that turned out to be fix #1's bug,
#    not the spacing itself. Reverted to even spacing, kept the GROUND_Y
#    scaling.
# 3. "try to make the bottom purple pop" (and when a more saturated purple
#    alone still "didn't work... still seems like all purple is below
#    horizon"): fix #1's scaling put the LAST stop at exactly 1.0 * (GROUND
#    _Y/CANVAS) == GROUND_Y itself -- the first row the ground Rectangle
#    paints over. Full purple only ever existed on a single row before
#    being swallowed; there was never a visible solid band, satisfying
#    "landed above the ground line" (fix #1's actual bug) while still
#    reading as "below the horizon" in practice. Pulled the whole scale in
#    by a margin (_RAINBOW_MARGIN_FRAC) so the last stop lands comfortably
#    short of GROUND_Y, leaving a real solid-purple strip (not a hairline)
#    in the open sky just above the stones.
# 4. Still on-device ("blue part is just starting at the horizon... big
#    purple part hidden under the black") even though the preview shows a
#    wide, correctly-placed solid purple band (verified by sampling pixels
#    down the preview canvas). The preview's canvas gradient CLAMPS/
#    extends the last color for every position beyond the final explicit
#    stop (standard canvas/SVG behavior) -- fix #3's margin relies on
#    exactly that extension. The real WFF renderer has already shown once
#    before (the zero-alpha Fill fallback bug in build_bg_switch) that it
#    does NOT reliably do the standard thing with "undefined past the last
#    explicit value" -- plausibly here too, nothing is painted past the
#    last explicit stop, so that whole intended purple band was actually
#    unpainted/transparent on-device. Fix: never rely on extension at all
#    -- append an explicit duplicate stop at position 1.0 (same color as
#    the real last stop) so the renderer has a real, defined stop spanning
#    the whole tail, not an inferred one. _rotated_rainbow_colors above
#    already does this (its trailing duplicate), so this fix now lives
#    once, per-rotation, instead of once globally.
_RAINBOW_MARGIN_FRAC = 0.20   # last stop lands at 80% of the way to GROUND_Y
_RAINBOW_VISIBLE_FRAC = (GROUND_Y * (1 - _RAINBOW_MARGIN_FRAC)) / CANVAS
# 7 evenly-spaced raw stops (one per ROYGBIV hue) plus the trailing
# duplicate-anchor position (matches _rotated_rainbow_colors' 8-element
# color lists above) -- same position list for every rotation, only the
# colors rotate per bgColor swatch.
_RAINBOW_RAW_POSITIONS = [i / 6 for i in range(7)]
DARK_RAINBOW_POSITIONS = [p * _RAINBOW_VISIBLE_FRAC for p in _RAINBOW_RAW_POSITIONS] + [1.0]

# History: v1 "about half that height"; v2 "align the tombstones to that
# new black bit at the bottom" (flush with the v2 ground's top edge); v2.1
# "bring the stones down about half way down between where it is now and"
# the bottom of the face (sunk into the ground); v3 "move tombstones up
# one half tombstone height" -> -= STONE_H/2. Each step built on the
# previous resolved value rather than re-deriving from scratch, since
# every one of Paul's asks here has been relative ("bring down", "move
# up"), not an absolute position.
_STONE_TOP_Y_FLUSH = _GROUND_Y_V2 - STONE_H
_STONE_TOP_Y_SUNK = round((_STONE_TOP_Y_FLUSH + CANVAS) / 2)
STONE_TOP_Y = round(_STONE_TOP_Y_SUNK - STONE_H / 2)
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

# -- middle-lane complications -------------------------------------------
# Paul: "add some complications in the middle... three complications
# across the middle lane would work for most people." The open sky
# between the top widget row (ends y=116) and the stone tops (starts
# y=265, see STONE_TOP_Y below -- this constant block sits above the
# stone-layout block it depends on, so the numbers here are precomputed
# by hand and cross-checked against STONE_TOP_Y once defined) is 149px
# tall. Sized at the SAME 120x68 as the existing weather/heart-style
# widgets (WIDGET_W/WIDGET_H) for visual consistency with the rest of the
# family, not a separate smaller size -- checked against the circle
# clipShape first: this lane sits closer to the face's vertical center
# than the top row does, so at this box height the margin needed to stay
# inside the circle is only ~11px (vs. the top row's 98px margin at its
# much-higher, more-clipped position) -- there's room to spare.
# 3x120 + 2x20 gap + 2x25 margin = 450 exactly.
MID_W, MID_H = WIDGET_W, WIDGET_H
MID_GAP, MID_MARGIN = 20, 25
MID_Y = 156   # vertically centered in the 116-265 lane (40/41px clearance
              # each side) -- verified against STONE_TOP_Y below via an
              # assert rather than trusting the hand computation silently.
MID_X = [MID_MARGIN, MID_MARGIN + MID_W + MID_GAP, MID_MARGIN + 2 * (MID_W + MID_GAP)]
assert MID_Y + MID_H < STONE_TOP_Y, (
    "middle-lane complications would overlap the stone tops -- "
    f"MID_Y+MID_H={MID_Y + MID_H}, STONE_TOP_Y={STONE_TOP_Y}"
)


# Edge lighting: narrow lit/shadow strips flush against the stone's own
# left/right edges, not a single wide segment sitting mid-stone (that was
# the original 1-of-5-segments shadow, STONE_W/5 ~= 14.4px wide). Both
# strips share one width.
_EDGE_W = 6

# Paul: "round off the tombstones a bit" -> first pass used 2 coarse steps
# (3/11 raised at the very top, 5/11 the row below); Paul's follow-up:
# "my numbers were off... stretch out the pixels in the middle... make the
# whole top seem more rounded." Replaced with many fine steps (not just 2)
# whose cut width follows a quarter-circle curve -- wide/narrow-raised at
# the very top, flat near the bottom where it rejoins full stone width --
# instead of a straight linear taper, so it actually reads as round rather
# than conical. _NOTCH_MAX_CUT_FRAC (per side, at y=0) keeps the same
# starting narrowness as the original 3/11-raised top row.
_NOTCH_N_STEPS = 8
_NOTCH_MAX_CUT_FRAC = (1 - 3 / 11) / 2   # ~0.364


def _notch_row_cuts():
    """(y, cut_w, step_h) for every notch row, cut_w possibly 0 near the
    bottom of the curve -- the shared geometry source for both the
    thumbnail's paint-over boxes and the real stone body's kept-width rows
    below."""
    step_h = MERLON_DEPTH / _NOTCH_N_STEPS
    max_cut = _NOTCH_MAX_CUT_FRAC * STONE_W
    rows = []
    for i in range(_NOTCH_N_STEPS):
        t_mid = (i + 0.5) / _NOTCH_N_STEPS
        cut_w = max_cut * math.sqrt(max(0.0, 1 - t_mid ** 2))
        rows.append((i * step_h, cut_w, step_h))
    return rows


def _notch_cut_boxes():
    """(dx, dy, w, h) cut rectangles, relative to a stone's (x, STONE_TOP_Y)
    -- used only by the baked gallery thumbnail (PIL), which paints a flat
    approximation over the corners. The real stone body (build_stone_body)
    no longer paints over these at all -- see its own comment for why."""
    return [
        box
        for y, cut_w, step_h in _notch_row_cuts()
        if cut_w >= 0.5
        for box in ((0.0, y, cut_w, step_h), (STONE_W - cut_w, y, cut_w, step_h))
    ]


# Paul: "make the font size a bit bigger aligned top from where it
# currently is." Text has no vertical-align attribute in WFF (confirmed
# via textElement.xsd/alignmentAttribute.xsd -- `align` is START/CENTER/
# END, horizontal only), so "top aligned" is achieved the only way WFF
# supports it: making the PartText box itself short and placing it near
# the stone's top (just under the shoulder notches) rather than spanning
# (and so vertically centering within) the stone's full height.
DIGIT_FONT_SIZE = 44
_TEXT_BOX_Y = STONE_TOP_Y + MERLON_DEPTH + 2
_TEXT_BOX_H = 52


# Split from a single build_stone() (body + text together) into a body-only
# builder and a separately-parameterized ink builder -- needed once the
# night background gained a second, gradient-based picker (see "bgGradient"
# below): the gradient/flat choice decides BOTH the background Rectangle's
# fill AND the digit ink, but those two need to sit at opposite ends of the
# paint order (background first, ink last, on top of the stone body) so
# they can't share one inline <PartText color="..."> the way a single flat
# [CONFIGURATION.bgColor] could. The stone body itself (gray, unrelated to
# either picker) stays unconditional either way.
#
# Paul: "is it possible to make the cutouts around the tombstone edges
# transparent?" -- the shoulder notches used to be faked by painting a
# flat background-colored patch OVER a full rectangular stone (first
# [CONFIGURATION.bgColor], later a hardcoded GROUND_COLOR). That only ever
# approximated a flat color -- it couldn't show stars, or either bgGradient
# option's actual gradient, because it never looked at what was really
# behind the stone. Real fix: paint the stone's TRUE silhouette only --
# each notch row is drawn at its already-narrowed kept width (never the
# cut corners at all) -- so the sky/stars/gradient already painted earlier
# in the Scene simply shows through natively. No "cut color" needed
# anywhere; _row_pieces below also carves the left/right edge strips out
# of each row's kept width so they can't overshoot a narrowed corner
# either. Shared between the real XML body and the JS preview mirror so
# both silhouettes stay identical.
def _row_pieces(y: float, x0: float, x1: float, h: float):
    """(dx, dy, w, h, color) pieces covering the kept range [x0, x1) at this
    row, splitting out the left-highlight/right-deep-shadow/right-shadow
    edge strips where they overlap."""
    lx1 = _EDGE_W
    dx0 = STONE_W - 2 * _EDGE_W   # deep shadow band, left of the edge strip
    dx1 = STONE_W - _EDGE_W
    pieces = []
    for a, b, color in (
        (x0, min(x1, lx1), STONE_HIGHLIGHT),
        (max(x0, lx1), min(x1, dx0), STONE_FILL),
        (max(x0, dx0), min(x1, dx1), STONE_DEEP_SHADOW),
        (max(x0, dx1), x1, STONE_SHADOW),
    ):
        if b - a >= 0.05:
            pieces.append((a, y, b - a, h, color))
    return pieces


def _stone_pieces():
    """All (dx, dy, w, h, color) pieces for one stone, relative to its own
    (x, STONE_TOP_Y) origin -- the notch rows plus the unnotched body below
    them."""
    pieces = [
        piece
        for y, cut_w, step_h in _notch_row_cuts()
        for piece in _row_pieces(y, cut_w, STONE_W - cut_w, step_h)
    ]
    pieces += _row_pieces(MERLON_DEPTH, 0, STONE_W, STONE_H - MERLON_DEPTH)
    return pieces


def build_stone_body(x: int) -> str:
    rects = "".join(
        f'<Rectangle x="{x + dx:.2f}" y="{STONE_TOP_Y + dy:.2f}" width="{w:.2f}" '
        f'height="{h:.2f}"><Fill color="{color}"/></Rectangle>'
        for dx, dy, w, h, color in _stone_pieces()
    )
    return (
        f'    <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">\n'
        f'      {rects}\n'
        f'    </PartDraw>'
    )


def build_stones() -> str:
    return "\n".join(build_stone_body(x) for x in STONE_X)


def build_digit_text(x: int, expr: str, ink: str) -> str:
    return (
        f'    <PartText x="{x}" y="{_TEXT_BOX_Y}" width="{STONE_W}" height="{_TEXT_BOX_H}">\n'
        f'      <Text align="CENTER">\n'
        f'        <Font family="serif" size="{DIGIT_FONT_SIZE}" weight="BOLD" color="{ink}">\n'
        f'          <Template>%d<Parameter expression="{expr}"/></Template>\n'
        f'        </Font>\n'
        f'      </Text>\n'
        f'    </PartText>'
    )


def build_digit_texts(ink: str) -> str:
    return "\n".join(
        build_digit_text(x, expr, ink) for x, expr in zip(STONE_X, STONE_EXPRS)
    )


# -- stars -----------------------------------------------------------
# Fixed, hand-scattered (deterministic seed) -- avoids the complication row
# (y 48-116) and stays entirely above GROUND_Y so none land on the black
# ground strip Paul asked for. The stones now sit flush against the
# ground (Paul: "align the tombstones to that new black bit"), so there's
# no more open-sky band between them worth a separate star group -- that
# space folded into the other two.
# Paul: "add stars into the background" -- with the stones now sunk way
# down near the ground (see STONE_TOP_Y above), the open night sky
# between the complication row and the stones is much bigger than it used
# to be, so this covers that whole area densely rather than a few
# narrow bands. Complications are transparent now too (no opaque panel to
# avoid), so stars are free to fall anywhere in the open sky, including
# near/behind the moon and weather icons.
_STAR_MAX_Y = STONE_TOP_Y - 15


def _star_field():
    rnd = random.Random(20261017)
    pts = []
    for _ in range(34):
        pts.append((rnd.uniform(18, 432), rnd.uniform(16, _STAR_MAX_Y), rnd.uniform(1.1, 3.0)))
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
    # Paul: "Is there a way to have the complications transparent?" --
    # dropped the RoundRectangle panel that used to sit behind this icon
    # (and the matching one that used to sit behind the weather slot).
    # Just the icon over the night sky now.
    icon = 44
    icon_x = MOON_BOX_X + (WIDGET_W - icon) // 2
    icon_y = WIDGET_Y + (WIDGET_H - icon) // 2
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
    return "\n".join(branches)


# -- ghosts --------------------------------------------------------------
# 6 pre-rasterized poses, one per [MINUTE] % 6 bucket -- changes every
# minute, no two adjacent minutes repeat. Paul: "about twice as big"
# (sizes doubled from the first pass) -- repositioned slightly lower/
# further apart than before so the bigger sprites still clear the
# (now-transparent, but still visually occupied by icon/text) complication
# row above them, per (gx, gy, size) = rest position.
# Paul: "we have 4 ghost shapes? Can they start second 1 by the stone and
# then over 15 seconds make their way off the top of the screen?" -- one
# ghost per tombstone now (4, not 6), each anchored to its own stone's
# center x. Sizes carried over from the previous 6-entry list, just
# trimmed to 4.
GHOST_SIZES = [88, 76, 82, 80]


# Hand-tuned per-variant styling rather than pure random jitter -- a first
# pass driven only by a random seed (2-choice wave count, narrow amplitude
# range) produced near-identical PNGs (caught by actually rendering a
# contact sheet, not just trusting "different seeds" was enough variety).
# Trimmed from 6 to 4 (one per stone, see GHOST_SIZES above) -- kept the 4
# most visually distinct of the original set.
GHOST_STYLES = [
    dict(n_waves=2, amp=0.035, width=1.00, eyes="dot", mouth="none"),
    dict(n_waves=4, amp=0.075, width=0.90, eyes="wide", mouth="none"),
    dict(n_waves=3, amp=0.050, width=1.12, eyes="wide", mouth="none"),
    dict(n_waves=5, amp=0.065, width=0.95, eyes="dot", mouth="smile"),
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
    body_color = (242, 242, 248, 170)
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

    # Paul: "make each have bigger eyes" -- scaled up from the original
    # 0.035/0.05x0.06/0.045 radii.
    ink = (35, 32, 48, 255)
    eye_dx = S * 0.10
    if style["eyes"] == "dot":
        r = S * 0.052
        for ex in (cx - eye_dx, cx + eye_dx):
            d.ellipse([ex - r, top_cy - r, ex + r, top_cy + r], fill=ink)
    elif style["eyes"] == "wide":
        rx, ry = S * 0.07, S * 0.085
        for ex in (cx - eye_dx, cx + eye_dx):
            d.ellipse([ex - rx, top_cy - ry, ex + rx, top_cy + ry], fill=ink)
    elif style["eyes"] == "sleepy":
        w = S * 0.065
        for ex in (cx - eye_dx, cx + eye_dx):
            d.line([ex - w, top_cy, ex + w, top_cy], fill=ink, width=max(2, int(S * 0.018)))
    elif style["eyes"] == "googly":
        # Big white sclera + a smaller dark pupil pushed off-center (and
        # mirrored between the two eyes) for a cross-eyed, cartoon-googly
        # look rather than a plain stare.
        outer_r = S * 0.095
        pupil_r = S * 0.045
        pupil_off = S * 0.025
        for side, ex in ((-1, cx - eye_dx), (1, cx + eye_dx)):
            d.ellipse([ex - outer_r, top_cy - outer_r, ex + outer_r, top_cy + outer_r],
                      fill=(250, 250, 252, 255), outline=ink, width=max(2, int(S * 0.01)))
            px = ex + side * pupil_off
            d.ellipse([px - pupil_r, top_cy - pupil_r, px + pupil_r, top_cy + pupil_r], fill=ink)

    if style.get("cheeks"):
        cheek_r = S * 0.05
        cheek_y = top_cy + S * 0.09
        cheek_color = (247, 165, 178, 180)
        for ex in (cx - eye_dx * 1.9, cx + eye_dx * 1.9):
            d.ellipse([ex - cheek_r, cheek_y - cheek_r, ex + cheek_r, cheek_y + cheek_r], fill=cheek_color)

    if style["mouth"] == "o":
        r = S * 0.025
        d.ellipse([cx - r, top_cy + S * 0.09 - r, cx + r, top_cy + S * 0.09 + r], fill=ink)
    elif style["mouth"] == "smile":
        mw = S * 0.055
        d.arc([cx - mw, top_cy + S * 0.04, cx + mw, top_cy + S * 0.14], 20, 160,
              fill=ink, width=max(2, int(S * 0.012)))

    img.resize((size, size), Image.LANCZOS).save(out_path)


def build_ghost_icons():
    # Rasterized a bit larger than the old 96px base now that these
    # display up to 100px on the face (Paul: "about twice as big") --
    # avoids visibly softening at the bigger on-screen size.
    for i, style in enumerate(GHOST_STYLES):
        _build_ghost_icon(style, DRAWABLE / f"ghost_{i}.png", size=160)


# History: earlier rounds had the ghosts either cycling pose-by-minute
# with a small 10/60s burst-dance, or a continuous every-6s wander loop.
# Paul redirected to the original sketch's own concept instead ("each
# minute random ghosts come from the stones"): once a minute, a ghost
# rises out of its own stone and drifts up off the top of the face, then
# isn't drawn again until its next rise.
#
# Then three refinements:
#   - "vary the exit points for each, it's not straight line motion" --
#     each ghost now has its own horizontal drift + a sine wobble on top
#     (GHOST_PATHS below), so the 4 climb-outs look like 4 different
#     flight paths, not 4 parallel vertical lines.
#   - "1 start on the 1, 2 start on the 16, 3 start on the 31, 4 on the
#     46, so they are always in motion" -- staggered starts, each 15
#     seconds apart. Since the rise itself takes exactly 15 seconds and
#     4 x 15 = 60, this tiles the entire minute with no gap AND no
#     overlap: at any given second exactly one ghost is mid-rise. Ghost
#     3's window (46 -> 60) wraps past 59 back to 0 -- handled by taking
#     the actual rendered second mod 60, not by anything minute-aware (the
#     animation only ever looks at [SECOND], so it just keeps looping).
#   - "let's reassign the stone and also make the paths and move more
#     horizontally back and forth while they rise" -- WFF has no native
#     random source (checked the v4 schema directly), so "reassign" means
#     deterministic-but-varying: which of the 4 ghost identities (style +
#     size + flight path) rises from a given stone now rotates with
#     [HOUR_0_23] % 4, so the pairing changes hour to hour instead of
#     being fixed for the app's lifetime. The stone SLOT keeps its own
#     fixed start_second (GHOST_START_SECONDS below) so the "always
#     exactly one ghost mid-rise" tiling guarantee still holds regardless
#     of which identity is currently assigned to it. Cost: this turns each
#     (stone, second) branch into a (stone, hour-bucket, second) branch --
#     4 slots x 4 hour-buckets x 15 steps = 240 Condition blocks, up from
#     60. One accepted rough edge: right at the top of an hour, a ghost
#     already mid-rise can visibly swap identity/path mid-flight, since
#     the hour-bucket used by its Condition flips under it.
_RISE_SECONDS = 15   # length of one ghost's climb, in seconds
GHOST_START_SECONDS = [1, 16, 31, 46]   # fixed per STONE SLOT, not per identity
_HOUR_BUCKETS = 4

# Per-ghost-identity flight path: (exit_dx, wobble_amp_frac, wobble_cycles)
# -- hand-picked for visible variety rather than randomized, so each
# path is easy to reason about/re-tune individually. wobble_amp is a
# fraction of the ghost's own size. Paul: "make the paths ... move more
# horizontally back and forth while they rise" -- bigger amplitudes and
# more cycles than the original pass, and smaller net exit_dx, so the
# dominant motion is the side-to-side swing rather than a one-way drift.
GHOST_PATHS = [
    (30, 0.35, 2.5),
    (-20, 0.30, 3.0),
    (15, 0.40, 2.0),    # the googly-eyed one -- the jitteriest, goofiest swing
    (-35, 0.28, 3.5),
]


def _ghost_rise_pos(step: int, start_x: float, start_y: float, size: int,
                     exit_dx: float, wobble_amp_frac: float, wobble_cycles: float):
    """step 0 = at the stone; step _RISE_SECONDS-1 = fully off the top of
    the circular face. x drifts toward start_x+exit_dx with a sine wobble
    layered on top so the path curves instead of running straight up;
    y still climbs linearly (see _RISE_SECONDS)."""
    end_y = -(size + 10)   # bounding box entirely above y=0 -> clipped by
                            # the CIRCLE clipShape regardless of x
    t = step / (_RISE_SECONDS - 1)
    y = round(start_y + t * (end_y - start_y))
    wobble = size * wobble_amp_frac * math.sin(t * wobble_cycles * 2 * math.pi)
    x = round(start_x + t * exit_dx + wobble)
    return x, y


def build_ghosts() -> str:
    # s = stone slot (fixed position + start_second); h = hour bucket;
    # g = (s + h) % _HOUR_BUCKETS is the ghost identity (style/size/path)
    # currently assigned to slot s during hour-bucket h. See the history
    # comment above GHOST_PATHS for why this rotation exists.
    out = []
    for s in range(_HOUR_BUCKETS):
        cx = STONE_X[s] + STONE_W / 2
        start_second = GHOST_START_SECONDS[s]
        for h in range(_HOUR_BUCKETS):
            g = (s + h) % _HOUR_BUCKETS
            size = GHOST_SIZES[g]
            half = round(size / 2)
            start_y = STONE_TOP_Y - size * 0.25   # "by the stone"
            exit_dx, wobble_amp_frac, wobble_cycles = GHOST_PATHS[g]
            for step in range(_RISE_SECONDS):
                sec = (start_second + step) % 60
                x, y = _ghost_rise_pos(step, cx, start_y, size, exit_dx, wobble_amp_frac, wobble_cycles)
                name = f"ghost_s{s}_h{h}_t{step}"
                out.append(
                    f'    <Condition>\n'
                    f'      <Expressions>\n'
                    f'        <Expression name="{name}"><![CDATA[floor([HOUR_0_23]) % {_HOUR_BUCKETS} == {h} '
                    f'&& floor([SECOND]) == {sec}]]></Expression>\n'
                    f'      </Expressions>\n'
                    f'      <Compare expression="{name}">\n'
                    f'        <PartImage x="{x - half}" y="{y}" width="{size}" height="{size}">\n'
                    f'          <Image resource="ghost_{g}"/>\n'
                    f'        </PartImage>\n'
                    f'      </Compare>\n'
                    f'    </Condition>'
                )
    return "\n".join(out)


# -- middle-lane complications -------------------------------------------
# Three generic, user-assignable slots (slotId 3/4/5 -- 1/2 are already
# weather/date). No DefaultProviderPolicy, same call Paul's weather slot
# already makes: "most people" won't agree on what belongs here (steps,
# battery, heart rate, next event...), so rather than guess, every slot
# ships empty and the user assigns a provider per-slot in the watch face
# editor -- same icon+text SHORT_TEXT layout as wff_complication_weather,
# just not forced to any one data source. Local to Hollow for now (not
# promoted to wff_common.py, which only hosts builders at least one other
# sibling already uses -- Paul can ask to port it later if a sibling wants
# the same generic slot).
MID_SLOT_IDS = [3, 4, 5]
MID_DISPLAY_NAMES = ["slot_mid1", "slot_mid2", "slot_mid3"]


def wff_complication_generic(x: int, y: int, w: int, h: int, slot_id: int, display_name: str) -> str:
    icon = 36
    text_w = w - icon
    icon_y = (h - icon) // 2
    return (
        f'    <ComplicationSlot x="{x}" y="{y}" width="{w}" height="{h}" '
        f'slotId="{slot_id}" displayName="{display_name}" supportedTypes="SHORT_TEXT EMPTY">\n'
        f'      <BoundingRoundBox x="0" y="0" width="{w}" height="{h}" cornerRadius="12"/>\n'
        f'      <Complication type="SHORT_TEXT">\n'
        f'        <Condition>\n'
        f'          <Expressions>\n'
        f'            <Expression name="mid{slot_id}_icon_text"><![CDATA['
        f'[COMPLICATION.TEXT] != null && [COMPLICATION.MONOCHROMATIC_IMAGE] != null]]></Expression>\n'
        f'            <Expression name="mid{slot_id}_text"><![CDATA['
        f'[COMPLICATION.TEXT] != null && [COMPLICATION.MONOCHROMATIC_IMAGE] == null]]></Expression>\n'
        f'          </Expressions>\n'
        f'          <Compare expression="mid{slot_id}_icon_text">\n'
        f'            <PartText x="0" y="0" width="{text_w}" height="{h}">\n'
        f'              <Text align="CENTER" ellipsis="TRUE">\n'
        f'                <Font family="SYNC_TO_DEVICE" size="26" weight="NORMAL" color="{COMPLICATION_TINT}">\n'
        f'                  <Template>%s<Parameter expression="[COMPLICATION.TEXT]"/></Template>\n'
        f'                </Font>\n'
        f'              </Text>\n'
        f'            </PartText>\n'
        f'            <PartImage x="{text_w}" y="{icon_y}" width="{icon}" height="{icon}" tintColor="{COMPLICATION_TINT}">\n'
        f'              <Image resource="[COMPLICATION.MONOCHROMATIC_IMAGE]"/>\n'
        f'            </PartImage>\n'
        f'          </Compare>\n'
        f'          <Compare expression="mid{slot_id}_text">\n'
        f'            <PartText x="0" y="0" width="{w}" height="{h}">\n'
        f'              <Text align="CENTER" ellipsis="TRUE">\n'
        f'                <Font family="SYNC_TO_DEVICE" size="26" weight="NORMAL" color="{COMPLICATION_TINT}">\n'
        f'                  <Template>%s<Parameter expression="[COMPLICATION.TEXT]"/></Template>\n'
        f'                </Font>\n'
        f'              </Text>\n'
        f'            </PartText>\n'
        f'          </Compare>\n'
        f'        </Condition>\n'
        f'      </Complication>\n'
        f'    </ComplicationSlot>')


def build_mid_complications() -> str:
    return "\n".join(
        wff_complication_generic(x, MID_Y, MID_W, MID_H, slot_id, display_name)
        for x, slot_id, display_name in zip(MID_X, MID_SLOT_IDS, MID_DISPLAY_NAMES)
    )


# -- preview thumbnail (gallery/picker) -----------------------------------
def build_preview_image():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (CANVAS, CANVAS), (10, 14, 26))
    d = ImageDraw.Draw(img)
    for x, y, r in _star_field():
        d.ellipse([x - r, y - r, x + r, y + r], fill=(232, 230, 216))
    d.rectangle([0, GROUND_Y, CANVAS, CANVAS], fill=(0, 0, 0))
    for x in STONE_X:
        d.rectangle([x, STONE_TOP_Y, x + STONE_W, STONE_TOP_Y + STONE_H], fill=(136, 140, 150))
        d.rectangle([x, STONE_TOP_Y, x + _EDGE_W, STONE_TOP_Y + STONE_H], fill=(185, 187, 193))
        d.rectangle([x + STONE_W - 2 * _EDGE_W, STONE_TOP_Y,
                     x + STONE_W - _EDGE_W, STONE_TOP_Y + STONE_H], fill=(58, 60, 65))
        d.rectangle([x + STONE_W - _EDGE_W, STONE_TOP_Y,
                     x + STONE_W, STONE_TOP_Y + STONE_H], fill=(94, 97, 105))
        for dx, dy, w, h in _notch_cut_boxes():
            d.rectangle([x + dx, STONE_TOP_Y + dy, x + dx + w, STONE_TOP_Y + dy + h],
                        fill=(0, 0, 0))
    digits = "1031"   # "a great time" per sibling precedent -- lively thumbnail
    try:
        font = ImageFont.truetype("DejaVuSerif-Bold.ttf", int(DIGIT_FONT_SIZE * 0.9))
    except OSError:
        font = None
    for x, ch in zip(STONE_X, digits):
        d.text((x + STONE_W / 2, _TEXT_BOX_Y + _TEXT_BOX_H / 2), ch, fill=(10, 14, 26),
                anchor="mm", font=font)
    # a small full-moon + one ghost for a recognizable thumbnail
    d.ellipse([MOON_BOX_X + 38, WIDGET_Y + 12, MOON_BOX_X + 38 + 44, WIDGET_Y + 12 + 44],
               fill=(237, 230, 214))
    PREVIEW_IMG.parent.mkdir(parents=True, exist_ok=True)
    img.save(PREVIEW_IMG)


# -- assembly --------------------------------------------------------------
def build_wff() -> str:
    # displayName must be the NAME of a string resource (res/values/strings.xml),
    # not inline literal text -- same gotcha already documented in Binary's
    # memory ("displayName attributes use bare string-resource names, not
    # @string/ syntax") but missed here when bgColor was first added. Paul,
    # on-device: "it still reads 1st setting, then 1st option, 2nd option" --
    # confirms the host picker silently falls back to generic ordinal labels
    # when it can't resolve the literal text as a resource name (space in
    # "Dark Red" made it an invalid resource name regardless of what text we
    # put there, which is why renaming the literal string earlier changed
    # nothing on-device). Fix: reference color_{key} / cfg_bgcolor, defined
    # in strings.xml, same pattern Binary already uses correctly.
    #
    # bgColor is a ListConfiguration here, not a ColorConfiguration --
    # changed so Dark Rainbow's rotation could branch Scene content on
    # which swatch is picked (see build_bg_switch's docstring for the full
    # history/why). Trade-off: the watch face editor will show this as a
    # plain list rather than a dedicated color-swatch grid.
    bg_options = "\n".join(
        f'      <ListOption id="{key}" displayName="color_{key}"/>'
        for key, display, hex_ in BG_OPTIONS
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_watchface.py - do not hand-edit. -->
<WatchFace width="{CANVAS}" height="{CANVAS}" clipShape="CIRCLE">
  <Metadata key="CLOCK_TYPE" value="DIGITAL"/>
  <Metadata key="PREVIEW_TIME" value="22:17:00"/>

  <UserConfigurations>
    <ListConfiguration id="bgColor" displayName="cfg_bgcolor" defaultValue="{BG_OPTIONS[BG_DEFAULT_INDEX][0]}">
{bg_options}
    </ListConfiguration>
{build_bg_gradient_configuration()}
  </UserConfigurations>

  <Scene>
    <!-- Background fill: a Scene-level ListConfiguration switch, outer on
         bgColor (one branch per swatch) with bgGradient (none/gradient/
         dark_rainbow) nested inside each; see build_bg_switch's
         docstring for why bgColor had to become the outer switch. Placed
         first so it still paints first. -->
{build_bg_switch()}
    <Group name="background" x="0" y="0" width="{CANVAS}" height="{CANVAS}">
      <PartDraw x="0" y="0" width="{CANVAS}" height="{CANVAS}">
        <Rectangle x="0" y="{GROUND_Y}" width="{CANVAS}" height="{GROUND_H}"><Fill color="{GROUND_COLOR}"/></Rectangle>
      </PartDraw>
{build_stars()}
{build_stones()}
{build_digit_texts(DIGIT_INK)}
{build_ghosts()}
{build_moon_group()}
    </Group>

    <!-- ComplicationSlots are direct Scene children, declared AFTER all
         the art above (Quinary's document-order lesson, re-confirmed in
         Radix: a background drawn after a ComplicationSlot silently
         paints over it). -->
{wff_complication_weather(WEATHER_BOX_X)}
{build_mid_complications()}
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
    ghost_slots_js = ",\n    ".join(
        f'{{x: {STONE_X[s] + STONE_W / 2:.1f}, startSecond: {GHOST_START_SECONDS[s]}}}'
        for s in range(_HOUR_BUCKETS)
    )
    ghost_identities_js = ",\n    ".join(
        f'{{size: {size}, startY: {STONE_TOP_Y - size * 0.25:.1f}, '
        f'exitDx: {GHOST_PATHS[g][0]}, wobbleAmp: {GHOST_PATHS[g][1]}, wobbleCycles: {GHOST_PATHS[g][2]}}}'
        for g, size in enumerate(GHOST_SIZES)
    )
    stars_js = ",\n    ".join(f'[{x:.1f}, {y:.1f}, {r:.2f}]' for x, y, r in _star_field())
    stone_pieces_js = ",\n    ".join(
        f'[{dx:.2f}, {dy:.2f}, {w:.2f}, {h:.2f}, "{css_hex(color)}"]'
        for dx, dy, w, h, color in _stone_pieces()
    )
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
<p>
  <label>night color <select id="bg"></select></label>
  (mock -- on a real watch this is the editor's list picker for
  <code>bgColor</code>, a WFF <code>ListConfiguration</code>)
</p>
<p>
  <label>night gradient <select id="bgGradient"></select></label>
  (mock -- overrides night color above when not "None", same mechanism as
  the WFF <code>bgGradient</code> ListConfiguration)
</p>
<p id="readout"></p>
<script>
{JS_VALUE_FN}
{JS_MOON_FN}

const STONES = [
    {stones_js}
];
// GHOST_SLOTS = the 4 stones (fixed position + start_second); GHOST_
// IDENTITIES = the 4 style/size/path variants. Which identity rises from
// which slot rotates with the hour -- mirrors the real face's
// (stone, hour-bucket, second) Condition branches (see build_ghosts()).
const HOUR_BUCKETS = {_HOUR_BUCKETS};
const GHOST_SLOTS = [
    {ghost_slots_js}
];
const GHOST_IDENTITIES = [
    {ghost_identities_js}
];
const STARS = [
    {stars_js}
];
// One stone's (dx, dy, w, h, color) paint pieces, relative to its own
// (x, STONE_TOP_Y) origin -- mirrors _stone_pieces() in the generator
// exactly, so the preview's notch corners are genuinely unpainted (the
// background/stars already drawn show through) instead of patched with a
// flat color, same fix as the real face.
const STONE_PIECES = [
    {stone_pieces_js}
];
const MOON_NAMES = {MOON_JS_NAMES};
// rot: this swatch's position in the ROYGBIV wheel (0-6), or 0 for an
// off-wheel swatch (brown/grey/midnight) -- mirrors _rainbow_rotation_
// index, used below to rotate RAINBOW_WHEEL for Dark Rainbow's start hue.
const BG_OPTIONS = [
    {", ".join(
        f'{{n: "{display}", c: "{css_hex(hex_)}", rot: {_rainbow_rotation_index(key)}}}'
        for key, display, hex_ in BG_OPTIONS
    )}
];
// The 7 dark ROYGBIV hexes in canonical R-O-Y-G-B-I-V order -- mirrors
// _RAINBOW_WHEEL exactly. Dark Rainbow rotates this to start at whichever
// swatch is picked (see draw() below), instead of always starting at Red.
const RAINBOW_WHEEL = [{", ".join(f'"{css_hex(c)}"' for c in _RAINBOW_WHEEL)}];
// Mirrors the Scene-level ListConfiguration switch (build_bg_switch) --
// "none" has no colors, meaning "fall through to the BG_OPTIONS pick
// above", same as the real face. Digit ink is fixed (DIGIT_INK below),
// not part of this switch.
const BG_GRADIENT_OPTIONS = [
    {{n: "None", colors: null, positions: null}},
    {{n: "Gradient", colors: "DYNAMIC", positions: [{", ".join(f'{p}' for p in GRADIENT_POSITIONS)}]}},
    {{n: "Dark Rainbow", colors: "DYNAMIC_RAINBOW", positions: [{", ".join(f'{p}' for p in DARK_RAINBOW_POSITIONS)}]}}
];

const ctx = document.getElementById('c').getContext('2d');
const bgSel = document.getElementById('bg');
BG_OPTIONS.forEach((opt, i) => {{
  const el = document.createElement('option');
  el.value = i; el.textContent = opt.n;
  bgSel.appendChild(el);
}});
bgSel.value = {BG_DEFAULT_INDEX};
bgSel.addEventListener('change', () => draw(window.__now ? window.__now() : new Date()));

const bgGradSel = document.getElementById('bgGradient');
BG_GRADIENT_OPTIONS.forEach((opt, i) => {{
  const el = document.createElement('option');
  el.value = i; el.textContent = opt.n;
  bgGradSel.appendChild(el);
}});
bgGradSel.value = 0;
bgGradSel.addEventListener('change', () => draw(window.__now ? window.__now() : new Date()));

// Each slot has its own staggered start second; each identity has its own
// curved (not straight-line) path -- mirrors the real face's per-slot,
// per-hour-bucket, per-second Condition branches. Returns null outside
// that slot's own 15-second rise window (wrapping past :59 back to :00,
// same as the real face).
function ghostPos(slot, identity, sec) {{
  const step = ((sec - slot.startSecond) % 60 + 60) % 60;
  if (step >= {_RISE_SECONDS}) return null;
  const t = step / ({_RISE_SECONDS} - 1);
  const endY = -(identity.size + 10);
  const y = identity.startY + t * (endY - identity.startY);
  const wobble = identity.size * identity.wobbleAmp * Math.sin(t * identity.wobbleCycles * 2 * Math.PI);
  const x = slot.x + t * identity.exitDx + wobble;
  return {{ x, y, size: identity.size }};
}}

function draw(now) {{
  const H = now.getHours(), M = now.getMinutes(), S = now.getSeconds();
  // Mirrors the Scene-level ListConfiguration branch for the background:
  // "none" falls through to the flat bgColor pick; "Gradient" fades
  // whichever bgColor is currently picked down to black (mirrors the real
  // face's flat-color-plus-transparent-overlay compositing); the other
  // gradient options build a fixed canvas gradient. Digit ink is fixed
  // (DIGIT_INK), not part of this switch.
  const gradOpt = BG_GRADIENT_OPTIONS[bgGradSel.value];
  let bg;
  if (gradOpt.colors === "DYNAMIC") {{
    const grad = ctx.createLinearGradient({C}, 0, {C}, {CANVAS});
    grad.addColorStop(gradOpt.positions[0], BG_OPTIONS[bgSel.value].c);
    grad.addColorStop(gradOpt.positions[1], "#000000");
    bg = grad;
  }} else if (gradOpt.colors === "DYNAMIC_RAINBOW") {{
    const grad = ctx.createLinearGradient({C}, 0, {C}, {CANVAS});
    const rot = BG_OPTIONS[bgSel.value].rot;
    const rotated = RAINBOW_WHEEL.slice(rot).concat(RAINBOW_WHEEL.slice(0, rot));
    const tail = rotated.slice(1).concat([rotated[rotated.length - 1]]);
    grad.addColorStop(gradOpt.positions[0], BG_OPTIONS[bgSel.value].c);
    tail.forEach((c, i) => grad.addColorStop(gradOpt.positions[i + 1], c));
    bg = grad;
  }} else if (gradOpt.colors) {{
    const grad = ctx.createLinearGradient({C}, 0, {C}, {CANVAS});
    gradOpt.colors.forEach((c, i) => grad.addColorStop(gradOpt.positions[i], c));
    bg = grad;
  }} else {{
    bg = BG_OPTIONS[bgSel.value].c;
  }}
  ctx.clearRect(0, 0, {CANVAS}, {CANVAS});
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, {CANVAS}, {CANVAS});

  ctx.fillStyle = "{css_hex(STAR_COLOR)}";
  for (const [x, y, r] of STARS) {{
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
  }}

  ctx.fillStyle = "{css_hex(GROUND_COLOR)}";
  ctx.fillRect(0, {GROUND_Y}, {CANVAS}, {GROUND_H});

  for (const s of STONES) {{
    for (const [dx, dy, w, h, color] of STONE_PIECES) {{
      ctx.fillStyle = color;
      ctx.fillRect(s.x + dx, {STONE_TOP_Y} + dy, w, h);
    }}
    ctx.fillStyle = "{css_hex(DIGIT_INK)}";   // fixed dark gray, not tied to any picker
    ctx.font = "bold {DIGIT_FONT_SIZE}px serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const v = Math.floor(value(s.expr, now));
    ctx.fillText(String(v), s.x + {STONE_W} / 2, {_TEXT_BOX_Y} + {_TEXT_BOX_H} / 2);
  }}

  // One ghost at a time (staggered starts, 15s each, tiling the full
  // minute) -- a plain JS branch here; the real face uses the same
  // per-slot, per-hour-bucket, per-second Condition branches it always
  // has. hourBucket picks which identity is currently assigned to each
  // slot (rotates hour to hour).
  const hourBucket = H % HOUR_BUCKETS;
  let activeCount = 0;
  for (let s = 0; s < GHOST_SLOTS.length; s++) {{
    const g0 = GHOST_IDENTITIES[(s + hourBucket) % HOUR_BUCKETS];
    const g = ghostPos(GHOST_SLOTS[s], g0, S);
    if (!g) continue;
    activeCount++;
    ctx.fillStyle = "rgba(242,242,248,0.9)";
    ctx.beginPath();
    ctx.arc(g.x, g.y - g.size * 0.15, g.size * 0.3, Math.PI, 0);
    ctx.lineTo(g.x + g.size * 0.3, g.y + g.size * 0.3);
    ctx.lineTo(g.x, g.y + g.size * 0.2);
    ctx.lineTo(g.x - g.size * 0.3, g.y + g.size * 0.3);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#282038";
    ctx.beginPath(); ctx.arc(g.x - g.size * 0.1, g.y - g.size * 0.15, g.size * 0.05, 0, 2 * Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(g.x + g.size * 0.1, g.y - g.size * 0.15, g.size * 0.05, 0, 2 * Math.PI); ctx.fill();
  }}

  // moon + weather -- transparent now, just the icon/mock over the sky
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

  // Middle-lane complications -- 3 empty user-assignable slots, mocked
  // here just as labeled outline boxes so the SIZE/placement is checkable
  // in this preview; real content is whatever provider gets assigned.
  const MID_X = {MID_X};
  ctx.font = "10px sans-serif";
  MID_X.forEach((mx, i) => {{
    ctx.strokeStyle = "rgba(128,128,128,0.6)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(mx, {MID_Y}, {MID_W}, {MID_H}, 12);
    ctx.stroke();
    ctx.fillStyle = "#888";
    ctx.textAlign = "center";
    ctx.fillText("complication " + (i + 1), mx + {MID_W} / 2, {MID_Y} + {MID_H} / 2);
  }});

  document.getElementById('readout').textContent =
    now.toTimeString().slice(0, 8) + "  moon:" + MOON_NAMES[mi] +
    (activeCount ? "  [" + activeCount + " ghost(s) rising]" : "  [ghosts hidden]");
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
    print(f"wrote {len(MOON_NAMES)} moon icons, {len(GHOST_STYLES)} ghost icons")
    print(f"wrote {PREVIEW_IMG.relative_to(ROOT)}")
    print(f"wrote {RAW.relative_to(ROOT)}  ({len(RAW.read_text())} bytes)")
    print(f"wrote {PREVIEW.relative_to(ROOT)}   (open in a browser)")


if __name__ == "__main__":
    main()
