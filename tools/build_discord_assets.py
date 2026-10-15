#!/usr/bin/env python3
"""Build the DBL Discohook assets in the 8-bit arcade style.

Writes discord/webhooks/** (channel headers, footer divider, webhook avatar,
banner wordmark, hosting preview, manifest, README), discord/server/** and
DBL_URL_MAP.txt. All artwork is pixel art drawn by tools/pixel_kit.py.

Raw GitHub paths never change, so existing Discohook JSON keeps its URLs. The
?v= version in tools/discohook_format.py is what makes Discord fetch new art:
bump it whenever these images change, then run
tools/normalize_discohook_templates.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixel_kit as px  # noqa: E402
from discohook_format import FOOTER_URL, HEADER_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEBHOOKS = ROOT / "discord" / "webhooks"
SERVER = ROOT / "discord" / "server"

# (file under discord/webhooks, title, eyebrow, kit slug: brand/kit names it dbl-<slug>-header-1600x533.png)
HEADERS = [
    ("welcome/dbl-welcome-banner.png", "WELCOME TO THE DBL", "WELCOME TO THE ROOM", "welcome"),
    ("league-office/dbl-constitution-header.png", "LEAGUE CONSTITUTION", "OFFICIAL DBL RULEBOOK", "constitution"),
    ("league-office/dbl-announcements-header.png", "LEAGUE ANNOUNCEMENTS", "OFFICIAL DBL NOTICE", "announcements"),
    ("league-office/dbl-calendar-header.png", "LEAGUE CALENDAR", "OFFICIAL DBL CALENDAR", "calendar"),
    ("league-office/dbl-ledger-header.png", "LEAGUE LEDGER", "OFFICIAL DBL LEDGER", "ledger"),
    ("league-office/dbl-voting-header.png", "LEAGUE VOTING", "OFFICIAL DBL VOTE", "voting"),
    ("draft-center/dbl-draft-center-header.png", "DRAFT CENTER", "OFFICIAL DBL DRAFT", "draft-center"),
    ("the-wire/dbl-the-wire-header.png", "THE WIRE", "DBL NEWS DESK", "the-wire"),
    ("general-managers/dbl-general-managers-header.png", "GENERAL MANAGERS", "THE CLUBHOUSE", "general-managers"),
    ("trade-center/dbl-trade-center-header.png", "TRADE CENTER", "OFFICIAL DBL TRADES", "trade-center"),
    ("scouting/dbl-scouting-header.png", "SCOUTING DEPARTMENT", "PROSPECTS & PICKS", "scouting"),
    ("waiver-wire/dbl-waiver-wire-header.png", "WAIVER WIRE", "FAAB & CLAIMS", "waiver-wire"),
    ("league-competition/dbl-competition-header.png", "LEAGUE COMPETITION", "STANDINGS & PLAYOFFS", "competition"),
    ("commissioners-office/dbl-commissioners-office-header.png", "COMMISSIONER'S OFFICE", "OFFICIAL DBL RULINGS", "commissioners-office"),
    ("franchise-hq/dbl-franchise-hq-header.png", "FRANCHISE HQ", "YOUR CLUB, YOUR CALLS", "franchise-hq"),
    ("league-office/dbl-champions-header.png", "DBL CHAMPIONS", "PERMANENT LEAGUE HISTORY", "champions"),
    ("league-office/dbl-records-header.png", "LEAGUE RECORDS", "THE PERMANENT RECORD", "records"),
    ("shared/dbl-generic-header-1600x420.png", "DYNASTY BASEBALL LEAGUE", "OFFICIAL DBL", "generic"),
]


def make_header(title: str, kicker: str, seed: int = 7) -> Image.Image:
    """1600 x 533 channel header (3:1): gold eyebrow, big title, the pixel B on the right."""
    return px.header(title, kicker, seed)


def all_headers() -> list[tuple[str, str, Image.Image]]:
    """(webhooks path, kit slug, image) for every header, in kit order."""
    return [(rel, slug, make_header(title, kicker, seed=i + 3)) for i, (rel, title, kicker, slug) in enumerate(HEADERS)]


def make_footer() -> Image.Image:
    """Transparent 1600 x 180 rink divider used under every Discohook message."""
    return px.footer_divider()


def server_banner() -> Image.Image:
    return px.banner((1920, 1080), 36, 6, dy=48, bars=2)


def banner_wordmark() -> Image.Image:
    """640 x 170 transparent lockup for legacy embeds."""
    img = Image.new("RGBA", (640, 170), (0, 0, 0, 0))
    px.place(img, px.lockup(9, 2, "white", sub_bold=False), 320, 85)
    return img


def build_preview(headers: list[tuple[str, Image.Image]], footer: Image.Image) -> Image.Image:
    """1320 x 1260 sheet: every header at quarter size, then the shared footer divider."""
    sheet = Image.new("RGBA", (1320, 1260), px.BLACK + (255,))
    px.draw_text(sheet, "DBL DISCOHOOK GRAPHICS", "jersey", 3, 40, 26, px.PAPER)
    y, col = 84, 0
    for name, img in headers:
        x = 40 + col * 420
        sheet.alpha_composite(img.resize((400, 133), Image.NEAREST), (x, y))
        px.draw_text(sheet, name, "silk", 2, x, y + 141, px.CREAM)
        col += 1
        if col == 3:
            col, y = 0, y + 169
    px.draw_text(sheet, "SHARED TRANSPARENT FOOTER DIVIDER", "silk-bold", 2, 40, y + 4, px.GOLD)
    strip = Image.new("RGBA", (800, 90), px.CHARCOAL + (255,))
    strip.alpha_composite(footer.resize((800, 90), Image.NEAREST))
    sheet.alpha_composite(strip, (260, y + 26))
    return sheet


README = f"""# DBL Discohook graphics (8-bit arcade style)

Canonical hosted graphics for DBL Discohook messages, drawn as pixel art by
tools/build_discord_assets.py (shared drawing code in tools/pixel_kit.py).

- Headers: 1600x533 (3:1) on a 200 x 67 pixel grid at 8 px per pixel, so each pixel
  is 2 px wide when Discord shows the image at 400 px.
- Header embed side color: #2B2D31.
- Footer: transparent 1600x180 PNG (legacy filename dbl-footer-divider-1600x90.png kept).
- Palette: black #0E0F12, charcoal #2B2D31, gold #FFB81C, cream #F4EFE4, ice #EEF5FA,
  paper #FCFCFC, blue #2457C5, red #C8241F.
- Type: Jersey 10 for titles and Silkscreen for eyebrows and labels (brand/fonts).
- The right side of every header carries the pixel B traced from the official mark.
- Image URLs carry a cache-busting version ({HEADER_VERSION} on headers, ?{FOOTER_URL.split('?')[1]} on the footer),
  set in tools/discohook_format.py. Bump it whenever the artwork changes, then run
  tools/normalize_discohook_templates.py.
"""


def main() -> None:
    headers = all_headers()
    for rel, _slug, img in headers:
        px.save(WEBHOOKS / rel, img, "RGB")
    footer = make_footer()
    px.save(WEBHOOKS / "shared" / "dbl-footer-divider-1600x90.png", footer, "RGBA")
    px.save(WEBHOOKS / "shared" / "dbl-banner-wordmark.png", banner_wordmark(), "RGBA")
    px.save(WEBHOOKS / "avatar" / "dbl-webhook-avatar-512.png", px.avatar(512), "RGB")
    px.save(SERVER / "dbl-server-icon-1024.png", px.avatar(1024), "RGB")
    px.save(SERVER / "dbl-server-banner-1920x1080.png", server_banner(), "RGB")
    px.save(WEBHOOKS / "DBL_Phase_2C6_Hosting_Preview.png",
            build_preview([(Path(rel).name, img) for rel, _s, img in headers], footer), "RGB")

    base = "https://raw.githubusercontent.com/diseasewheeze/dbl-assets/main/discord/webhooks/"
    (ROOT / "DBL_URL_MAP.txt").write_text(
        f"""DBL RAW ASSET URLS\n\nWelcome banner:\n{base}welcome/dbl-welcome-banner.png\n\nFooter divider:\n{base}shared/dbl-footer-divider-1600x90.png\n\nGeneric header:\n{base}shared/dbl-generic-header-1600x420.png\n\nBanner wordmark:\n{base}shared/dbl-banner-wordmark.png\n\nHosting preview:\n{base}DBL_Phase_2C6_Hosting_Preview.png\n\nConstitution:\n{base}league-office/dbl-constitution-header.png\n\nAnnouncements:\n{base}league-office/dbl-announcements-header.png\n\nCalendar:\n{base}league-office/dbl-calendar-header.png\n\nLedger:\n{base}league-office/dbl-ledger-header.png\n\nVoting:\n{base}league-office/dbl-voting-header.png\n\nDraft Center:\n{base}draft-center/dbl-draft-center-header.png\n""",
        encoding="utf-8",
    )

    manifest = {
        "phase": "2C.6-frozen",
        "style": "8-bit arcade",
        "asset_version": HEADER_VERSION.removeprefix("?v="),
        "header_dimensions": "1600x533",
        "header_grid": "200x67 pixels at 8 px",
        "header_embed_color": "#2B2D31",
        "footer_dimensions": "1600x180 (legacy filename retained for stable URLs)",
        "footer_background": "transparent",
        "palette": {"black": "#0E0F12", "charcoal": "#2B2D31", "gold": "#FFB81C", "cream": "#F4EFE4",
                    "ice": "#EEF5FA", "paper": "#FCFCFC", "blue": "#2457C5", "red": "#C8241F"},
        "fonts": {"display": "Jersey 10", "labels": "Silkscreen"},
        "design": {
            "status": "frozen layout, 8-bit artwork",
            "right_mark": "pixel B traced from the official mark, fully inset; never clipped",
            "wordmark": "DBL in Jersey 10 with gold then black keylines; wordmark file kept for legacy use",
            "footer": "transparent cream/gold/cream rink divider with a centered gold pixel ring",
        },
    }
    (WEBHOOKS / "DBL_Phase_2C6_Hosting_Manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (WEBHOOKS / "README.md").write_text(README, encoding="utf-8")
    print(f"DBL 8-bit Discohook assets generated ({len(HEADERS)} headers, version {HEADER_VERSION}).")


if __name__ == "__main__":
    main()
