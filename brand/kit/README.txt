PSBL BRAND & GRAPHICS PACKAGE (8-BIT ARCADE)
============================================
Every file is pixel art: drawn on a small grid and enlarged with hard edges.
Banners, headers, dividers and stamps use an 8 px grid (one pixel = 8 px).
Built by tools/build_brand_package.py (drawing code in tools/pixel_kit.py).
League name and year come from brand/identity.json.

Palette: navy #0C2340, red #BD3039, white #FFFFFF, with deep navy #071528 and
off-white paper #F6F7F9. Light navy #8FA6C7 marks pending, amended and
champions stamps. Status green #3FA34D appears on stamps only. Team colors
appear only on small jersey or stripe elements, never on league marks.
Type: Jersey 10 (PSBL, titles) and Silkscreen (labels), in brand/fonts with OFL.txt.
Official marks: PSBL in Jersey 10 with red then navy keylines, and the league
emblem, a pixel baseball (white ball, red seams and stitches, red then navy keylines).

01_logos                 Wordmarks (transparent white / navy, textured paper) and the baseball emblem
02_avatars_icons         Server icon, webhook/bot avatar, profile pic, emoji, favicon
03_server_social_banners Discord server banner/splash, social preview, X header, event cover
04_channel_headers       1600x533 (3:1) headers for every channel category + welcome + generic
05_dividers              Footer divider (transparent), thin rule, red bar
06_seals_stamps          Round official seal (navy/paper) and status stamps (transparent PNG)

File names are kept from the first kit so existing links keep working. The color
words in some names are the old ones: "black" files are deep navy, "charcoal"
files are navy, "cream" files are off-white paper, "gold" files are red, and the
"b-mark" / "b-icon" / "emoji-b" files show the baseball emblem.

Discord notes
- Embed images display at ~400px wide; headers are 3:1 so text stays readable.
- Discord caches by URL: when you replace a file, bump the ?v= version in
  tools/discohook_format.py and run tools/normalize_discohook_templates.py.
- Server banner needs a boosted server; recommended 960x540 or larger (16:9).
- Avatars use the small 14 x 14 pixel baseball so they stay sharp at Discord's 40-48 px.
- Stamps are transparent PNGs: use as embed thumbnail or image in rulings, votes and ledger posts.
