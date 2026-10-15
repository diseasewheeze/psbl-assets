# PSBL Discohook graphics (8-bit arcade style)

Canonical hosted graphics for PSBL Discohook messages, drawn as pixel art by
tools/build_discord_assets.py (shared drawing code in tools/pixel_kit.py).

- Headers: 1600x533 (3:1) on a 200 x 67 pixel grid at 8 px per pixel, so each pixel
  is 2 px wide when Discord shows the image at 400 px.
- Header embed side color: #0C2340 (HEADER_COLOR in tools/discohook_format.py).
- Footer: transparent 1600x180 PNG (legacy filename psbl-footer-divider-1600x90.png kept).
- Palette: navy #0C2340, red #BD3039, white #FFFFFF, deep navy #071528, off-white #F6F7F9;
  small red text on navy uses #D9545C. Status green #3FA34D is for stamps only.
- Type: Jersey 10 for titles and Silkscreen for eyebrows and labels (brand/fonts).
- The right side of every header carries the league emblem, a pixel baseball.
- Image URLs carry a cache-busting version (?v=8bit-sox-1 on headers, ?v=8bit-sox-1 on the footer),
  set in tools/discohook_format.py. Bump it whenever the artwork changes, then run
  tools/normalize_discohook_templates.py.
