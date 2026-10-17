"""Shared helpers, forked from RadixWatchFace/tools/wff_common.py (same
family, same WFF format version 4) and trimmed to what this face needs:
geometry constants, the raster-icon technique, and the two complication
builders (date, weather) ported in unmodified. Radix-specific bits
(palettes, base-N digit grid logic) are dropped; this face's own art
(stones, ghosts, moon icons, stars) lives in gen_watchface.py since it's
not shared with any sibling.
"""

CANVAS = 450
C = CANVAS / 2

DATE_X, DATE_Y, DATE_W, DATE_H = 125, 382, 200, 36
WIDGET_W, WIDGET_H = 120, 68
WIDGET_Y = 48
WIDGET_MARGIN_X = 98

# Fixed regardless of theme -- complications can't reference a dynamic
# palette choice as a color (same limitation RadixWatchFace's complications
# hit), and this face has no theme toggle anyway.
COMPLICATION_TINT = "#FF808080"


def css_hex(argb: str) -> str:
    """#FFRRGGBB -> #RRGGBB -- WFF colors are ARGB, but an 8-digit hex
    literal in CSS/canvas is #RRGGBBAA (alpha LAST, not first), so passing
    a WFF color straight into preview.html silently reinterprets it as a
    mostly-transparent, wrong-hued color instead of erroring. Every
    sibling preview.html hits this; BinaryWatchFace's _css_hex() is the
    proven fix (every color this family uses is fully opaque, so dropping
    the alpha byte is safe)."""
    return "#" + argb[-6:]


def rasterize_polygon(pts, out_path, size=128, supersample=4, pad=0.06,
                       fill=(255, 255, 255, 255)):
    """Rasterize a closed polygon (list of (x, y) in any consistent unit)
    to a PNG at out_path, normalized to fit the canvas with `pad` margin.
    WFF's Image loader only handles raster drawables, not VectorDrawable
    XML (confirmed in BinaryWatchFace's history) -- this is the same
    supersample-then-downscale technique BinaryWatchFace's heart icon
    used, generalized so every hand-drawn icon in this family can share
    it instead of re-deriving the normalize/scale/supersample math."""
    from PIL import Image, ImageDraw
    SS, SIZE = supersample, size
    S = SIZE * SS
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w, h = maxx - minx, maxy - miny
    scale = (1 - 2 * pad) * S / max(w, h)
    ox, oy = (S - w * scale) / 2, (S - h * scale) / 2

    def to_px(x, y):
        return (x - minx) * scale + ox, S - ((y - miny) * scale + oy)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([to_px(x, y) for x, y in pts], fill=fill)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(out_path)


def wff_complication_date() -> str:
    return (
        f'    <ComplicationSlot x="{DATE_X}" y="{DATE_Y}" width="{DATE_W}" height="{DATE_H}" '
        f'slotId="2" displayName="slot_date" supportedTypes="SHORT_TEXT EMPTY">\n'
        f'      <DefaultProviderPolicy defaultSystemProvider="DAY_AND_DATE" defaultSystemProviderType="SHORT_TEXT"/>\n'
        f'      <BoundingRoundBox x="0" y="0" width="{DATE_W}" height="{DATE_H}" cornerRadius="8"/>\n'
        f'      <Complication type="SHORT_TEXT">\n'
        f'        <Condition>\n'
        f'          <Expressions>\n'
        f'            <Expression name="date_on"><![CDATA[[COMPLICATION.TEXT] != null]]></Expression>\n'
        f'          </Expressions>\n'
        f'          <Compare expression="date_on">\n'
        f'            <PartText x="0" y="0" width="{DATE_W}" height="{DATE_H}">\n'
        f'              <Text align="CENTER">\n'
        f'                <Font family="SYNC_TO_DEVICE" size="30" weight="NORMAL" color="{COMPLICATION_TINT}">\n'
        f'                  <Template>%s<Parameter expression="[COMPLICATION.TEXT]"/></Template>\n'
        f'                </Font>\n'
        f'              </Text>\n'
        f'            </PartText>\n'
        f'          </Compare>\n'
        f'        </Condition>\n'
        f'      </Complication>\n'
        f'    </ComplicationSlot>')


def wff_complication_weather(x: int) -> str:
    """Ported unmodified from RadixWatchFace/tools/wff_common.py. WEATHER
    is not a valid defaultSystemProvider in the WFF schema (confirmed via
    defaultProviderPolicyElement.xsd) -- no DefaultProviderPolicy here is
    deliberate, the user assigns a weather provider in the watch face
    editor. Unlike moon phase, there is no native [WEATHER.*] complication
    shortcut that skips this."""
    icon = 36
    text_w = WIDGET_W - icon
    icon_y = (WIDGET_H - icon) // 2
    return (
        f'    <ComplicationSlot x="{x}" y="{WIDGET_Y}" width="{WIDGET_W}" height="{WIDGET_H}" '
        f'slotId="1" displayName="slot_weather" supportedTypes="SHORT_TEXT EMPTY">\n'
        f'      <BoundingRoundBox x="0" y="0" width="{WIDGET_W}" height="{WIDGET_H}" cornerRadius="12"/>\n'
        f'      <Complication type="SHORT_TEXT">\n'
        f'        <Condition>\n'
        f'          <Expressions>\n'
        f'            <Expression name="weather_icon_text"><![CDATA['
        f'[COMPLICATION.TEXT] != null && [COMPLICATION.MONOCHROMATIC_IMAGE] != null]]></Expression>\n'
        f'            <Expression name="weather_text"><![CDATA['
        f'[COMPLICATION.TEXT] != null && [COMPLICATION.MONOCHROMATIC_IMAGE] == null]]></Expression>\n'
        f'          </Expressions>\n'
        f'          <Compare expression="weather_icon_text">\n'
        f'            <PartText x="0" y="0" width="{text_w}" height="{WIDGET_H}">\n'
        f'              <Text align="CENTER" ellipsis="TRUE">\n'
        f'                <Font family="SYNC_TO_DEVICE" size="30" weight="NORMAL" color="{COMPLICATION_TINT}">\n'
        f'                  <Template>%s<Parameter expression="[COMPLICATION.TEXT]"/></Template>\n'
        f'                </Font>\n'
        f'              </Text>\n'
        f'            </PartText>\n'
        f'            <PartImage x="{text_w}" y="{icon_y}" width="{icon}" height="{icon}" tintColor="{COMPLICATION_TINT}">\n'
        f'              <Image resource="[COMPLICATION.MONOCHROMATIC_IMAGE]"/>\n'
        f'            </PartImage>\n'
        f'          </Compare>\n'
        f'          <Compare expression="weather_text">\n'
        f'            <PartText x="0" y="0" width="{WIDGET_W}" height="{WIDGET_H}">\n'
        f'              <Text align="CENTER" ellipsis="TRUE">\n'
        f'                <Font family="SYNC_TO_DEVICE" size="30" weight="NORMAL" color="{COMPLICATION_TINT}">\n'
        f'                  <Template>%s<Parameter expression="[COMPLICATION.TEXT]"/></Template>\n'
        f'                </Font>\n'
        f'              </Text>\n'
        f'            </PartText>\n'
        f'          </Compare>\n'
        f'        </Condition>\n'
        f'      </Complication>\n'
        f'    </ComplicationSlot>')


# JS mirror of WFF's clock-value expressions, for preview.html -- identical
# to every sibling project.
JS_VALUE_FN = r"""function value(src, now) {
  const H = now.getHours(), M = now.getMinutes(), S = now.getSeconds();
  src = src.replaceAll("[HOUR_0_23]", H).replaceAll("[MINUTE]", M).replaceAll("[SECOND]", S);
  src = src.replace(/floor\(([^()]+)\)/g, (_, e) => "Math.floor(" + e + ")");
  return Function('"use strict";return (' + src + ')')();
}"""
