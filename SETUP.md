# Android dev environment setup (Toussaint)

Identical toolchain to [RadixWatchFace](https://github.com/pburney/RadixWatchFace) and
its siblings — same machine, same SDK.

**Android Studio** (`~/bin/android-studio`) provisioned `~/Android/Sdk` —
platform `android-37.0`, build-tools `36.0.0`, `platform-tools` (`adb`).
`local.properties` (gitignored) points at it:
```
sdk.dir=/home/developer/Android/Sdk
```

**Gradle wrapper is committed** (`./gradlew`, `gradle/wrapper/`, pinned to
8.9) — no manual Gradle install needed.

## Build

```bash
cd /data/BUSINESS/Burnilab/HollowWatchFace
./gradlew :app:assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```

## Install on the Pixel Watch (wireless — no USB port)

```bash
ADB=/home/developer/Android/Sdk/platform-tools/adb
$ADB pair <watch-ip>:<pair-port>      # 6-digit code shown on watch
$ADB devices -l
$ADB install -r app/build/outputs/apk/debug/app-debug.apk
```
On the watch: long-press the current face -> **+ Add** -> **Hollow**.

**Wireless adb is flaky in practice on this watch** — if a connection drops,
`adb kill-server && adb start-server && adb mdns services` usually
rediscovers it; if `adb connect` still fails, the pairing itself has gone
stale and needs a fresh `Settings -> Developer options -> Wireless
debugging -> Pair new device` code, not just a reconnect.

## Validating watchface.xml offline

Same validator as the sibling projects:
```bash
git clone --depth 1 https://github.com/google/watchface.git /tmp/wff-validator-src
cd /tmp/wff-validator-src/third_party/wff/specification/validator
mkdir out
javac -cp "$(find libs -name '*.jar' | tr '\n' ':')" -d out $(find src/main -name '*.java')
(cd ../documents && zip -qr ../validator/out/docs.zip .)
java -cp "$(find libs -name '*.jar' | tr '\n' ':')out" \
  com.samsung.watchface.DWFValidationApplication 4 \
  /data/BUSINESS/Burnilab/HollowWatchFace/app/src/main/res/raw/watchface.xml
```

## Gotchas confirmed (or re-confirmed) building this one

Everything prior siblings' `SETUP.md` documents still applies
(`watch_face_info.xml` required, `ComplicationSlot` must be a direct
`<Scene>` child, Scene paints in document order — complications declared
last so they paint on top of the art beneath them). New ground specific to
Hollow:

- **Part-level `x`/`y`/`width`/`height` (on `PartDraw`/`PartText`/`PartImage`/
  `Group`) are `xs:integer`** — unlike the `x`/`y` on the DRAW SHAPE elements
  *inside* a `PartDraw` (`Rectangle`, `Ellipse`, `Arc`'s `centerX`/`centerY`),
  which are `xs:float`. A computed float like `132.4` at the Part level fails
  the validator outright (`cvc-datatype-valid.1.2.1`); the shape element one
  level down accepts it fine. Confirmed directly against
  `common/attributes/geometricAttributes.xsd` after hitting this on the
  star-field dots. Round at the call site, not just hope the numbers happen
  to land on whole pixels.
- **`<Rectangle>` has no `cornerRadiusX`/`cornerRadiusY`** — that's
  `<RoundRectangle>`, a separate element. `<Rectangle>` only takes `<Stroke>`
  and `<Fill>` as children (not `<Outline>`, despite that reading naturally);
  put both in the same element rather than two overlapping `Rectangle`s.
- **`<Ellipse>` exists and takes `<Fill>` directly** — the simplest way to
  draw a plain filled circle (used here for the star field). The project's
  `Arc` + `WeightedStroke` "pie wedge" trick (first used for Nonary/Radix's
  big-oval minute corners) solves a *different* problem — `RoundRectangle`'s
  corner-radius clamp — and isn't the right tool for an ordinary dot.
- **`[MOON_PHASE_TYPE]`, `[MOON_PHASE_POSITION]`, `[MOON_PHASE_TYPE_STRING]`
  are native WFF data sources** (`common/simpleTypes/sourceType.xsd`,
  `moonPhaseSourceType`), usable directly in any expression the same way
  `[HOUR_0_23]` is — NOT a complication provider category (`MOON_PHASE` is
  absent from `defaultProviderPolicyElement.xsd`'s `defaultProviderType`
  enum), so no `ComplicationSlot` and no user setup. **Unverified on-device
  as of first build**: whether `[MOON_PHASE_TYPE]` is actually a clean 0–7
  integer matching this app's 8-bucket `Condition` assumption — confirm on
  Paul's Pixel Watch 5 before trusting it, same discipline as everywhere
  else in this family (the schema validator has twice missed real
  rendering bugs before).
- **`==` as a comparison operator is new ground for this family** — every
  prior sibling only ever needed `>` (cumulative fill level) or `!=` (null
  checks). Confirmed as a valid token in
  `common/simpleTypes/arithmeticExpressionType.xsd`'s `_operatorType` enum
  (interestingly, `!=` and `<` are NOT in that enum despite `!=` already
  working in every sibling's complications — the published XSD token list
  isn't the full story, the real runtime parser is more permissive). Treat
  `==` as unverified-on-device too, for the same reason.
