"""Images for Last Call, the league's weekly email newsletter.

Email clients ignore web fonts, so the newsletter's pixel lettering comes from
these images: a masthead, one header per section and a footer band. Each is
drawn at twice the size it is shown (1200 px wide for a 600 px email column)
with the shared 8-bit toolkit, so it matches the channel headers.

Section headers sit on the email's off-white paper (#F6F7F9, PAPER in the
toolkit) so they blend into the body: set the email body to that color. League
text comes from brand/identity.json. Run `python tools/build_newsletter_images.py`; the files land in
brand/newsletter/.
"""

from __future__ import annotations

import pixel_kit as px
from pixel_kit import NAVY, NAVY_DK, NAVY_HI, NAVY_LO, PAPER, RED, RED_LT, MUTED, STANDS, WHITE

S = px.LEAGUE_SHORT

OUT = px.ROOT / "brand" / "newsletter"

SECTIONS = {
    "week": "THE WEEK IN 60 SECONDS",
    "ahead": "THE WEEK AHEAD",
    "clubhouse": "AROUND THE CLUBHOUSE",
    "spotlight": "OWNER SPOTLIGHT",
    "prospects": "PROSPECT WATCH",
    "nhl": "AROUND THE MAJORS",          # file name kept for existing links
    "corner": "THE DUGOUT",
    "commissioner": "FROM THE COMMISSIONER",
}


def masthead():
    """1200 x 300: the channel-header look with LAST CALL as the title."""
    k = 8
    a = px.art(150, 38, NAVY)
    px.grain(a, [NAVY_HI, NAVY_LO], .02, 211)
    px.dither(a, 0, 29, 150, 7, STANDS)
    px.rect(a, 9, 6, 2, 26, RED)
    px.put(a, px.EMBLEM32(), 112, 3)
    px.rect(a, 0, 36, 150, 2, RED)
    img = px.enlarge(a, k, (1200, 300), offset=(0, 4))
    x = 16 * k
    px.draw_text(img, f"THE {S} WEEKLY", "silk", 3, x, 52, RED_LT)
    px.draw_text(img, "LAST CALL", "jersey", 12, x, 92, WHITE, shadow=NAVY_DK)
    px.draw_text(img, px.LEAGUE_LINE, "silk", 2, x, 240, MUTED)
    return img


def section(title: str):
    """1200 x 96 on off-white paper: a red pixel, the title in navy Silkscreen, a dashed red rule."""
    a = px.art(300, 24, PAPER)
    px.rect(a, 0, 7, 5, 5, RED)
    for x in range(0, 300, 4):
        px.rect(a, x, 20, 2, 2, RED)
    img = px.enlarge(a, 4, (1200, 96))
    px.draw_text(img, title, "silk-bold", 6, 40, 24, NAVY)
    return img


def footer():
    """1200 x 120 navy band: the small baseball and the sign-off."""
    a = px.art(150, 15, NAVY)
    px.grain(a, [NAVY_HI, NAVY_LO], .02, 97)
    px.rect(a, 0, 0, 150, 1, RED)
    px.put(a, "ball", 8, 1)
    img = px.enlarge(a, 8, (1200, 120))
    px.draw_text(img, f"LAST CALL • THE {S} WEEKLY", "silk", 3, 200, 36, WHITE)
    px.draw_text(img, px.LEAGUE_NAME.upper(), "silk", 2, 200, 76, MUTED)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"last-call-masthead.png": masthead(), "last-call-footer.png": footer()}
    files.update({f"last-call-section-{key}.png": section(title) for key, title in SECTIONS.items()})
    for name, img in files.items():
        img.convert("RGB").save(OUT / name, optimize=True)
    print(f"{len(files)} newsletter images in {OUT.relative_to(px.ROOT)}")


if __name__ == "__main__":
    main()
