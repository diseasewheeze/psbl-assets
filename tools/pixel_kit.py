"""DBL 8-bit pixel-art toolkit, shared by build_discord_assets.py and build_brand_package.py.

Every graphic is painted on a small art grid and enlarged with NEAREST, so each
art pixel is a hard-edged square (banners and headers use an 8 px grid: one art
pixel = 8 export pixels). Text uses the OFL pixel fonts in brand/fonts
(Jersey 10 for display, Silkscreen for labels). Glyphs are rendered at their
design pixel, thresholded to 1-bit and enlarged by whole numbers, so letter
edges stay crisp too.

Palette: navy, red and white (see the palette block below). The league emblem
is a pixel baseball generated here: ball_sprite() paints a white ball with red
seams and stitches at any size and wraps it in red and navy keylines; the small
14 x 14 ball for avatars and emoji is drawn by hand in SPRITES. The ballpark
scenes (bleachers, outfield wall, mown outfield, infield dirt and the drag
tractor) replace the old arena and rink.

League text comes from brand/identity.json (LEAGUE_NAME, LEAGUE_SHORT,
LEAGUE_EST): rename the league there and rebuild.

Pillow only: the CI workflow installs nothing else.
"""

from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "brand" / "fonts"

# ---------------------------------------------------------------- league identity
# The league's name lives in brand/identity.json: rename it there, then rebuild.
IDENTITY = json.loads((ROOT / "brand" / "identity.json").read_text(encoding="utf-8"))
LEAGUE_NAME = IDENTITY["league_name"]                      # Dynasty Baseball League
LEAGUE_SHORT = IDENTITY["short_name"]                      # DBL
LEAGUE_EST = str(IDENTITY["established"])                  # 2026
LEAGUE_TAGLINE = f"{LEAGUE_NAME} • Est. {LEAGUE_EST}"
LEAGUE_LINE = f"{LEAGUE_NAME.upper()} • EST. {LEAGUE_EST}"  # sign-off line on headers and cards

# ---------------------------------------------------------------- palette
# Navy, red and white. Everything else is a one-step shade of those three or a neutral grey.
NAVY = (12, 35, 64)         # #0C2340  main ground: banners, headers, embed side color
NAVY_DK = (7, 21, 40)       # #071528  deep ground, outer keylines, counters
RED = (189, 48, 57)         # #BD3039  the accent: keylines, rails, rules, bars; red status stamps
WHITE = (255, 255, 255)     # #FFFFFF  letter fill of DBL, the ball, titles on navy
PAPER = (246, 247, 249)     # #F6F7F9  off-white paper ground
GREEN = (63, 163, 77)       # #3FA34D  status green: stamps only

# Tones: shades of the palette for grain, dither, bevels, the crowd and the ballpark.
RED_LT, RED_DK = (217, 84, 92), (142, 31, 39)          # #D9545C small red text on navy / #8E1F27
NAVY_LT = (22, 50, 90)                                 # #16325A panels, the outfield wall
NAVY_HI, NAVY_LO = (16, 41, 73), (9, 29, 54)           # grain on navy
DEEP_HI, DEEP_LO = (11, 27, 49), (4, 14, 28)           # grain on deep navy
STANDS = (8, 26, 48)                                   # #081A30 the bleachers
SEAT, SEAT_DK, SEAT_LT = (30, 58, 98), (22, 46, 80), (42, 74, 120)
SKY = (143, 166, 199)       # #8FA6C7  light navy: pending and amended stamps
BLUE = (44, 86, 150)        # #2C5696  bright navy: canopy, links
MUTED = (160, 174, 196)     # #A0AEC4  sign-off text on navy
STEEL, STEEL_DK = (154, 161, 169), (110, 116, 124)
TIRE = (40, 44, 52)
CHALK = (214, 221, 231)     # #D6DDE7  the ball's shaded side, chalk in shadow
PAPER_DK, PAPER_MD, PAPER_DKR, INK = (232, 235, 240), (238, 240, 244), (222, 226, 233), NAVY
TURF, TURF_LT = (15, 44, 80), (20, 54, 96)             # the outfield, mown in navy stripes
CLAY, CLAY_DK, CLAY_LT = (140, 52, 54), (114, 40, 44), (160, 66, 66)   # infield dirt

# Sprite letters -> colors ("." is transparent)
PAL = {"K": NAVY_DK, "V": NAVY, "W": WHITE, "C": PAPER, "T": CHALK, "R": RED, "D": RED_DK, "L": RED_LT,
       "U": BLUE, "S": STEEL, "N": STEEL_DK, "M": TIRE}

SPRITES = {
    # the league's small baseball (14 x 14): avatars, emoji, favicon, sign-offs
    "ball": [
        "....KKKKKK....",
        "..KKWWWWWWKK..",
        ".KWRWWWWWWRWK.",
        ".KWWRWWWWRWWK.",
        "KWWWRWWWWRWWTK",
        "KWWWWRWWRWWWTK",
        "KWWWWRWWRWWWTK",
        "KWWWWRWWRWWWTK",
        "KWWWWRWWRWWTTK",
        "KWWWRWWWWRWTTK",
        ".KWWRWWWWRWTK.",
        ".KTRTTWWTTRTK.",
        "..KKTTTTTTKK..",
        "....KKKKKK....",
    ],
    # a ball at rest on the field (7 x 7)
    "pebble": ["..KKK..", ".KWWWK.", "KRWWWRK", "KWRWRWK", "KRWWWRK", ".KWWTK.", "..KKK.."],
    # crossed bats (16 x 14)
    "bats": [
        "..KK........KK..",
        ".KCCK......KTTK.",
        "KCCCCK....KTTTTK",
        ".KCCCCK..KTTTTK.",
        "..KCCCCKKTTTTK..",
        "...KCCCCKTTTK...",
        "....KCCCCKTK....",
        ".....KCCCCK.....",
        ".....KKCCCK.....",
        "....KRTKKCRK....",
        "...KRRK..KRRK...",
        ".KKRRK....KRRKK.",
        "KDDDK......KDDDK",
        ".KDK........KDK.",
    ],
}

# The infield drag tractor (56 x 28, drives right, dragging the mat), its body left blank for the league's
# short name; frame 1 has the body bobbed up a pixel. SPRITES["tractor"] / ["tractor1"] carry the name.
TRACTOR_FRAMES = ([
    "........................................................",
    "........................................................",
    "........................................................",
    "..............................KKKKKKKKKKKKKKKKKKKK......",
    ".............................KUUUUUUUUUUUUUUUUUUUUK.....",
    "..............................KNKKKKKKKKKKKKKKKNKK......",
    "..............................KNK.............KNK.......",
    "..............................KNK.............KNK.......",
    "..............................KNK....KKK......KNK.......",
    "..............................KNK...KRRRK.....KNK.......",
    "..............................KNK.KKKRRRRKKK..KNK.......",
    "..............................KNKKVVVTTTKKKKK.KNK.......",
    "..............................KNKKVVUUUUUKNK..KNK.......",
    "..............................KNKKVVUUUUUKNKKKKNKKKKK...",
    ".........................KKKKKKNKKVVUUUUUKNKWWWWWWWWWK..",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWTWK.",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWLWK.",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    ".....................KKKKWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    "....................KNNNNWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    "...................KKKKKKRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.",
    ".................KKSNK..KRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.",
    "..............KKKSNKK....KKMSSNNNNSSMKKKKKKKKKMMSSSMMK..",
    "KKKKKKKKKKKKKKNSNKK.......KMSSNWNNSSMK.......KMSNNNSMK..",
    "NNNNNNNNNNNNNNKKK.........KMMSNNNNSMMK.......KMSWNNSMK..",
    "NSNSNSNSNSNSNNK...........KMMSSSSSSMMK.......KMMSSSMMK..",
    "NNNNNNNNNNNNNNK............KMMMSSMMMK........KMMMMMMMK..",
    "KKKKKKKKKKKKKK..............KMMMMMMK..........KKMMMKK...",
], [
    "........................................................",
    "........................................................",
    "..............................KKKKKKKKKKKKKKKKKKKK......",
    ".............................KUUUUUUUUUUUUUUUUUUUUK.....",
    "..............................KNKKKKKKKKKKKKKKKNKK......",
    "..............................KNK.............KNK.......",
    "..............................KNK.............KNK.......",
    "..............................KNK....KKK......KNK.......",
    "..............................KNK...KRRRK.....KNK.......",
    "..............................KNK.KKKRRRRKKK..KNK.......",
    "..............................KNKKVVVTTTKKKKK.KNK.......",
    "..............................KNKKVVUUUUUKNK..KNK.......",
    "..............................KNKKVVUUUUUKNKKKKNKKKKK...",
    ".........................KKKKKKNKKVVUUUUUKNKWWWWWWWWWK..",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWTWK.",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWLWK.",
    "........................KWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    ".....................KKKKWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    "....................KNNNNWWWWWWWWWWWWWWWWWWWWWWWWWWWWWK.",
    ".....................KKKKRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.",
    "...................KK...KRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.",
    ".................KKSNK...KKMMSNNNNSMMKKKKKKKKKMMMMMMMK..",
    "..............KKKSNKK.....KMSSNNNNSSMK.......KMMSSSMMK..",
    "KKKKKKKKKKKKKKNSNKK.......KMSSNNNWSSMK.......KMSNNNSMK..",
    "NNNNNNNNNNNNNNKKK.........KMMSNNNNSMMK.......KMSNNWSMK..",
    "NSNSNSNSNSNSNNK...........KMMSSSSSSMMK.......KMMSSSMMK..",
    "NNNNNNNNNNNNNNK............KMMMSSMMMK........KMMMMMMMK..",
    "KKKKKKKKKKKKKK..............KMMMMMMK..........KKMMMKK...",
])
TRACTOR_TEXT_AT = ((28, 15), (28, 14))   # where the name starts on each frame
TRACTOR_TEXT_MAX = 23                    # pixels of body side the name may use

# 3 x 5 letters for names painted on sprites
TINY = {
    "A": ["###", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."], "C": ["###", "#..", "#..", "#..", "###"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."], "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": ["###", "#..", "#.#", "#.#", "###"], "H": ["#.#", "#.#", "###", "#.#", "#.#"], "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["..#", "..#", "..#", "#.#", "###"], "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"], "N": ["##.", "#.#", "#.#", "#.#", "#.#"], "O": ["###", "#.#", "#.#", "#.#", "###"],
    "P": ["###", "#.#", "###", "#..", "#.."], "Q": ["###", "#.#", "#.#", "###", "..#"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": ["###", "#..", "###", "..#", "###"], "T": ["###", ".#.", ".#.", ".#.", ".#."], "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "V": ["#.#", "#.#", "#.#", "#.#", ".#."], "W": ["#.#", "#.#", "###", "###", "#.#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"], "0": ["###", "#.#", "#.#", "#.#", "###"],
    "1": [".#", "##", ".#", ".#", ".#"], "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", "###", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"], "6": ["###", "#..", "###", "#.#", "###"],
    "7": ["###", "..#", "..#", "..#", "..#"], "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
}


def lettered(rows, text: str, x: int, y: int, ink: str = "V", room: int | None = None) -> list[str]:
    """Rows with `text` stamped in 3 x 5 letters from (x, y); letters that would pass `room` px are left off."""
    g = [list(r) for r in rows]
    start = x
    for ch in text.upper():
        glyph = TINY.get(ch)
        if glyph is None:
            x += 2
            continue
        if room is not None and x + len(glyph[0]) - start > room:
            break
        for j, line in enumerate(glyph):
            for i, bit in enumerate(line):
                if bit == "#":
                    g[y + j][x + i] = ink
        x += len(glyph[0]) + 1
    return ["".join(r) for r in g]


SPRITES["tractor"] = lettered(TRACTOR_FRAMES[0], LEAGUE_SHORT, *TRACTOR_TEXT_AT[0], room=TRACTOR_TEXT_MAX)
SPRITES["tractor1"] = lettered(TRACTOR_FRAMES[1], LEAGUE_SHORT, *TRACTOR_TEXT_AT[1], room=TRACTOR_TEXT_MAX)

SPRITE_PALS: dict[str, dict] = {}


# ---------------------------------------------------------------- the emblem: a pixel baseball
@lru_cache(maxsize=None)
def ball_body(d: int, theta: float = 38, bulge: float = .30) -> tuple[str, ...]:
    """A d x d baseball: white with a chalk-shaded lower right, and two red seams that curve toward the
    middle, each stitched with chevrons. Seams and stitches thicken with the size."""
    R = c = d / 2
    cells = {}
    for y in range(d):
        for x in range(d):
            if math.hypot(x + .5 - c, y + .5 - c) <= R:
                shaded = math.hypot(x + .5 - c + R * .3, y + .5 - c + R * .3) > R * 1.08
                cells[(x, y)] = "T" if shaded else "W"
    t = 1 if d < 36 else 2 if d < 64 else 3              # seam thickness
    inset = 1.2 if d < 36 else 2.2 if d < 64 else 3.5    # seams stop short of the edge
    gap = 3 if d < 36 else 4 if d < 64 else 6            # stitch spacing along the seam
    tick = 1 if d < 36 else 2 if d < 64 else 3           # stitch length each side
    th = math.radians(theta)
    ex, ey = R * math.sin(th), R * math.cos(th)          # seam ends on the rim
    mx = ex - bulge * R                                  # seam middle, closer to the center
    ccx = (ex * ex + ey * ey - mx * mx) / (2 * (ex - mx))
    r = ccx - mx
    a0 = math.atan2(ey, ex - ccx)
    for side in (-1, 1):
        run, last, n = 0.0, None, 2000
        for i in range(n + 1):
            a = -a0 + 2 * a0 * i / n
            x, y = side * (ccx - r * math.cos(a)), r * math.sin(a)
            if math.hypot(x, y) > R - inset:
                continue
            nx, ny = side * math.cos(a), -math.sin(a)       # across the seam
            tx, ty = side * math.sin(a), math.cos(a)        # along the seam
            for k in range(t):
                off = (k - (t - 1) / 2) * .9
                q = (int(math.floor(c + x + nx * off)), int(math.floor(c + y + ny * off)))
                if q in cells:
                    cells[q] = "R"
            if last is not None:
                run += math.hypot(x - last[0], y - last[1])
            last = (x, y)
            if run >= gap:
                run = 0.0
                for s in (-1, 1):
                    for j in range(1, tick + 1):
                        dd = t / 2 + j * .9
                        q = (int(math.floor(c + x + s * nx * dd - tx * j * .75)),
                             int(math.floor(c + y + s * ny * dd - ty * j * .75)))
                        if q in cells:
                            cells[q] = "R"
    return tuple("".join(cells.get((x, y), ".") for x in range(d)) for y in range(d))


def _layer_of(cells: set, x: int, y: int, reach: int) -> int:
    """Rounded distance (in cells) from (x, y) to the nearest filled cell, or reach + 1."""
    best = reach + 1.5
    for dy in range(-reach - 1, reach + 2):
        for dx in range(-reach - 1, reach + 2):
            if (x + dx, y + dy) in cells:
                best = min(best, math.hypot(dx, dy))
    return math.ceil(best - 0.5)


@lru_cache(maxsize=None)
def ball_sprite(total: int, outer: str = "RK") -> tuple[str, ...]:
    """The emblem at total x total: the ball, then one keyline per letter of `outer` (red, then navy)."""
    reach = len(outer)
    body = ball_body(total - 2 * reach)
    cells = {(x + reach, y + reach) for y, row in enumerate(body) for x, ch in enumerate(row) if ch != "."}
    rows = []
    for y in range(total):
        row = []
        for x in range(total):
            if (x, y) in cells:
                row.append(body[y - reach][x - reach])
                continue
            layer = _layer_of(cells, x, y, reach)
            row.append(outer[layer - 1] if layer <= reach else ".")
        rows.append("".join(row))
    return tuple(rows)


EMBLEM32 = lambda: ball_sprite(32, "RK")            # logos, icons, the primary mark
EMBLEM48 = lambda: ball_sprite(48, "RRK")           # channel headers
EMBLEM_SEAL = lambda: ball_sprite(100, "RRRRKK")    # the official seal (100 x 100)


def sprite(rows, scale: int = 1) -> Image.Image:
    pal = {**PAL, **SPRITE_PALS.get(rows, {})} if isinstance(rows, str) else PAL
    rows = SPRITES[rows] if isinstance(rows, str) else rows
    img = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                px[x, y] = pal[ch] + (255,)
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def put(img: Image.Image, rows, x: int, y: int, scale: int = 1) -> None:
    s = sprite(rows, scale)
    img.alpha_composite(s, (x, y))


# ---------------------------------------------------------------- canvas helpers
def art(w: int, h: int, color=None) -> Image.Image:
    return Image.new("RGBA", (w, h), (color + (255,)) if color else (0, 0, 0, 0))


def rect(img, x, y, w, h, color):
    if w > 0 and h > 0:
        ImageDraw.Draw(img).rectangle((x, y, x + w - 1, y + h - 1), fill=color + (255,))


BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def dither(img, x, y, w, h, color, down=True):
    """Ordered (Bayer 4x4) dither: `color` grows from 0 to 100% coverage across the band."""
    px = img.load()
    for j in range(h):
        level = ((j + 0.5) / h if down else 1 - (j + 0.5) / h) * 16
        for i in range(w):
            if BAYER[(y + j) & 3][(x + i) & 3] < level:
                px[x + i, y + j] = color + (255,)


def grain(img, colors, density, seed):
    rnd = random.Random(seed)
    px = img.load()
    w, h = img.size
    for i in range(round(w * h * density)):
        px[rnd.randrange(w), rnd.randrange(h)] = colors[i % len(colors)] + (255,)


def crowd(img, top, h, seed):
    """Bleachers full of fans: staggered seat dots in navy, a few fans in red and white."""
    w = img.width
    rect(img, 0, top, w, h, STANDS)
    rnd = random.Random(seed)
    px = img.load()
    for j in range(0, h, 2):
        for i in range((j // 2) % 2, w, 2):
            t = rnd.random()
            px[i, top + j] = (RED if t < .05 else WHITE if t < .085 else SEAT if t < .4 else SEAT_DK if t < .72 else SEAT_LT) + (255,)


def frame(img, x, y, w, h, t, step, color, wear=0.0, seed=1):
    """Rectangle outline `t` pixels thick with stepped corners; `wear` knocks out a few pixels."""
    rnd = random.Random(seed)
    px = img.load()
    for j in range(h):
        for i in range(w):
            dx, dy = min(i, w - 1 - i), min(j, h - 1 - j)
            s = dx + dy
            if s < step:
                continue
            if (dx < t or dy < t or s < step + t) and not (wear and rnd.random() < wear):
                px[x + i, y + j] = color + (255,)


def ring(img, cx, cy, r0, r1, color, box=None):
    """Fill art pixels whose centers lie between radii r0 and r1 of (cx, cy)."""
    px = img.load()
    x0, y0, x1, y1 = box or (0, 0, img.width, img.height)
    for j in range(y0, y1):
        for i in range(x0, x1):
            if r0 <= math.hypot(i + .5 - cx, j + .5 - cy) <= r1:
                px[i, j] = color + (255,)


def enlarge(img: Image.Image, k: int, size: tuple[int, int], offset: tuple[int, int] | None = None, pad=None) -> Image.Image:
    """Scale the art by k with NEAREST, then crop (or pad) to the exact export size."""
    big = img.resize((img.width * k, img.height * k), Image.NEAREST)
    W, H = size
    if big.width >= W and big.height >= H:
        ox, oy = offset if offset else ((big.width - W) // 2, (big.height - H) // 2)
        return big.crop((ox, oy, ox + W, oy + H))
    out = Image.new("RGBA", size, (pad + (255,)) if pad else (0, 0, 0, 0))
    out.alpha_composite(big, ((W - big.width) // 2, (H - big.height) // 2))
    return out


# ---------------------------------------------------------------- pixel fonts
class PixelFont:
    """A pixel font rendered at its design pixel: mask() returns 1 px per font pixel."""

    def __init__(self, path: Path, size: int, unit: int, cap: int):
        self.font = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)
        self.unit, self.cap = unit, cap  # render pixels per font pixel, cap height in font pixels

    @lru_cache(maxsize=None)
    def mask(self, text: str) -> tuple[Image.Image, int]:
        """1-bit-style L mask (0/255) at one pixel per font pixel, and the row where capitals start."""
        u = self.unit
        asc, desc = self.font.getmetrics()
        width = (math.ceil(self.font.getlength(text) / u) + 4) * u
        base = (math.ceil(asc / u) + 1) * u
        height = base + (math.ceil(desc / u) + 1) * u
        img = Image.new("L", (width, height), 0)
        ImageDraw.Draw(img).text((u, base), text, font=self.font, fill=255, anchor="ls")
        small = img.resize((width // u, height // u), Image.NEAREST).point(lambda v: 255 if v >= 128 else 0)
        box = small.getbbox()
        if not box:
            return Image.new("L", (1, 1), 0), 0
        cropped = small.crop((box[0], box[1], box[2], box[3]))
        return cropped, base // u - self.cap - box[1]

    def width(self, text: str, scale: int = 1) -> int:
        return self.mask(text)[0].width * scale


@lru_cache(maxsize=None)
def font(name: str) -> PixelFont:
    if name == "jersey":    # Jersey 10: 75-unit pixel on a 1400 em -> size 56 gives 3 px per font pixel
        return PixelFont(FONTS / "jersey10" / "Jersey10-Regular.ttf", 56, 3, 10)
    if name == "silk":      # Silkscreen: 8 px design size -> size 64 gives 8 px per font pixel
        return PixelFont(FONTS / "silkscreen" / "Silkscreen-Regular.ttf", 64, 8, 5)
    if name == "silk-bold":
        return PixelFont(FONTS / "silkscreen" / "Silkscreen-Bold.ttf", 64, 8, 5)
    raise KeyError(name)


def outlined(mask: Image.Image, fill, layers) -> Image.Image:
    """Color a mask and wrap it in stepped keylines (one color per pixel of distance, rounded corners)."""
    reach = len(layers)
    w, h = mask.width + 2 * reach, mask.height + 2 * reach
    mp = mask.load()
    cells = {(x + reach, y + reach) for y in range(mask.height) for x in range(mask.width) if mp[x, y]}
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = out.load()
    for y in range(h):
        for x in range(w):
            if (x, y) in cells:
                px[x, y] = fill + (255,)
            elif reach:
                layer = _layer_of(cells, x, y, reach)
                if 1 <= layer <= reach:
                    px[x, y] = layers[layer - 1] + (255,)
    return out


def text_image(text: str, face: str, scale: int, color, layers=(), shadow=None) -> tuple[Image.Image, int]:
    """Text as an RGBA image at `scale` px per font pixel; returns (image, y of cap top inside it)."""
    mask, cap_top = font(face).mask(text)
    img = outlined(mask, color, layers)
    if shadow:  # hard drop shadow one font pixel down-right
        sh = Image.new("RGBA", (img.width + 1, img.height + 1), (0, 0, 0, 0))
        tint = Image.new("RGBA", img.size, shadow + (255,))
        sh.paste(tint, (1, 1), img)
        sh.alpha_composite(img, (0, 0))
        img = sh
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img, (cap_top + len(layers)) * scale


def draw_text(img, text, face, scale, x, cap_y, color, align="l", layers=(), shadow=None, snap=None):
    """Draw text with its capitals starting at cap_y. align: l (x is left) or c (x is center)."""
    t, cap_top = text_image(text, face, scale, color, layers, shadow)
    reach = len(layers) * scale
    left = x - reach if align == "l" else x - (t.width - (scale if shadow else 0)) // 2
    if snap:
        left = round(left / snap) * snap
    img.alpha_composite(t, (left, cap_y - cap_top))
    return t.width


# ---------------------------------------------------------------- the wordmark lockup
VARIANTS = {
    #          fill    keylines (half font-pixel steps)  (whole-pixel steps)  sub/est  sub keyline
    "white": (WHITE, (RED, RED, NAVY_DK), (RED, NAVY_DK), WHITE, NAVY_DK),
    "black": (NAVY, (WHITE, RED, RED), (RED,), NAVY, None),     # navy letters for light grounds
    "paper": (NAVY, (PAPER, RED, RED), (RED,), NAVY, None),
}


def lockup(a: int, b: int, variant: str = "white", sub_bold: bool = True) -> Image.Image:
    """The short name (DBL) in Jersey 10 (a px per font pixel) over the league name and EST. year in
    Silkscreen (b px per font pixel). Keylines: red then navy on the white version."""
    fill, keys, whole_keys, ink, subkey = VARIANTS[variant]
    mask, cap_top = font("jersey").mask(LEAGUE_SHORT)
    if a % 2 == 0:  # keylines on a half-pixel grid
        top = outlined(mask.resize((mask.width * 2, mask.height * 2), Image.NEAREST), fill, keys)
        top = top.resize((top.width * a // 2, top.height * a // 2), Image.NEAREST)
    else:           # odd scale: one keyline per font pixel
        top = outlined(mask, fill, whole_keys)
        top = top.resize((top.width * a, top.height * a), Image.NEAREST)
    sub, sub_cap = text_image(LEAGUE_NAME.upper(), "silk-bold" if sub_bold else "silk", b, ink,
                              (subkey,) if subkey else ())
    est, est_cap = text_image(f"EST. {LEAGUE_EST}", "silk", b, ink, (subkey,) if subkey else ())
    rule_w, rule_h, gap = 34 * b, 2 * b, 4 * b
    est_w = est.width + 2 * (rule_w + gap)
    W = max(top.width, sub.width, est_w)
    sub_y = top.height + a - sub_cap
    est_y = sub_y + sub_cap + 5 * b + a - est_cap
    H = est_y + est.height
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(top, ((W - top.width) // 2, 0))
    out.alpha_composite(sub, ((W - sub.width) // 2, sub_y))
    ex = (W - est_w) // 2
    rule_y = est_y + est_cap + (5 * b - rule_h) // 2
    rect(out, ex, rule_y, rule_w, rule_h, RED)
    out.alpha_composite(est, (ex + rule_w + gap, est_y))
    rect(out, ex + est_w - rule_w, rule_y, rule_w, rule_h, RED)
    return out


def fit_lockup(a: int, b: int, max_w: int, max_h: int, variant: str = "white", sub_bold: bool = True) -> Image.Image:
    """The largest lockup no bigger than the one asked for (a, b) that fits max_w x max_h, so a longer
    league name steps the whole lockup down instead of clipping. Scales keep their even/odd parity."""
    for pct in range(100, 19, -4):
        a2 = max(2, round(a * pct / 100))
        if a2 % 2 != a % 2:
            a2 -= 1
        b2 = max(1, round(b * pct / 100))
        piece = lockup(a2, b2, variant, sub_bold)
        if piece.width <= max_w and piece.height <= max_h:
            return piece
    return piece


def place(img: Image.Image, piece: Image.Image, cx: int, cy: int, snap: int = 1) -> None:
    x = round((cx - piece.width / 2) / snap) * snap
    y = round((cy - piece.height / 2) / snap) * snap
    img.alpha_composite(piece, (x, y))


# ---------------------------------------------------------------- painted backgrounds (art grid)
def bg_plain(w, h, color, textured=True):
    img = art(w, h, color)
    if textured and color == NAVY:
        grain(img, [NAVY_HI, NAVY_LO], .02, w + h)
    elif textured and color == NAVY_DK:
        grain(img, [DEEP_HI, DEEP_LO], .02, w + h)
    return img


def bg_paper(w, h):
    """Off-white paper with a light grey grain and a few navy specks."""
    img = art(w, h, PAPER)
    grain(img, [PAPER_DK, PAPER_MD, PAPER_DKR], .06, 77)
    grain(img, [INK], .0012, 5)
    return img


def bg_banner(w, h, bars=1, bats=False):
    """Navy ballpark: red rails top and bottom, bleachers fading into navy, a dithered fade to deep navy."""
    img = bg_plain(w, h, NAVY)
    ch = round(h * .24)
    f = round(ch * .5)
    crowd(img, bars, ch, w + h)
    dither(img, 0, bars + ch - f, w, f, NAVY)
    bf = round(h * .14)
    dither(img, 0, h - bars - bf, w, bf, NAVY_DK)
    if bats:
        sy = round(h / 2 - 7) + 1
        put(img, "bats", 5, sy)
        put(img, "bats", w - 21, sy)
    rect(img, 0, 0, w, bars, RED)
    rect(img, 0, h - bars, w, bars, RED)
    return img


WALL_H = 6          # the outfield wall above the field: red rail, padded navy wall, shadow
SPLASH_FIELD = 32   # rows of field under the wall on the title screen


def field_scene(img, top: int, field_h: int, tractor_x: int, frame: int = 0, ball_x: int | None = None) -> int:
    """The ballpark strip, painted across the whole width from row `top`: the outfield wall, a mown navy
    outfield, then the infield dirt with the drag tractor at tractor_x smoothing the clay behind it.
    Returns the row where the field starts."""
    w = img.width
    rect(img, 0, top, w, 1, RED)                               # rail cap
    rect(img, 0, top + 1, w, WALL_H - 2, NAVY_LT)              # padded wall
    for x in range(5, w, 12):
        rect(img, x, top + 1, 1, WALL_H - 2, NAVY)             # pad seams
    rect(img, 0, top + WALL_H - 1, w, 1, NAVY_DK)
    fy = top + WALL_H
    grass = max(6, round(field_h * .36))
    px = img.load()
    for j in range(grass):                                     # diagonal mowing stripes
        for i in range(w):
            px[i, fy + j] = (TURF_LT if ((i + j) // 8) % 2 else TURF) + (255,)
    rect(img, 0, fy + grass, w, 1, CLAY_DK)                    # the lip where grass meets dirt
    dy, dh = fy + grass + 1, field_h - grass - 1
    rect(img, 0, dy, w, dh, CLAY)
    smooth = tractor_x + 14                                    # the mat has dragged everything left of here
    rnd = random.Random(field_h * 7 + w)
    for j in range(dh):
        for i in range(w):
            if i < smooth:
                if j % 3 == 1:
                    px[i, dy + j] = CLAY_LT + (255,)             # fresh drag lines
            else:
                t = rnd.random()
                if t < .12:
                    px[i, dy + j] = CLAY_DK + (255,)             # raked, cleat-scuffed dirt
                elif t < .17:
                    px[i, dy + j] = CLAY_LT + (255,)
    put(img, "tractor1" if frame else "tractor", tractor_x, fy + field_h - 29)
    if ball_x is not None:
        put(img, "pebble", ball_x, fy + field_h - 9)
    return fy


def bg_splash(w=240, h=135):
    """Title screen: deep navy with a dithered stadium glow, red rails, and the ballpark strip with the
    drag tractor working the infield."""
    bars = 2
    img = bg_plain(w, h, NAVY_DK)
    dither(img, 0, bars, w, 44, NAVY, down=False)
    top = h - bars - SPLASH_FIELD - WALL_H
    field_scene(img, top, SPLASH_FIELD, 20, ball_x=round(w * .62))
    rect(img, 0, 0, w, bars, RED)
    rect(img, 0, h - bars, w, bars, RED)
    return img


# ---------------------------------------------------------------- finished graphics (export size)
def wordmark_on(size, color, variant, b, dy=0, k=8):
    """Full lockup centered on a flat, lightly textured ground."""
    W, H = size
    aw, ah = math.ceil(W / k), math.ceil(H / k)
    img = enlarge(bg_plain(aw, ah, color, textured=color in (NAVY, NAVY_DK)), k, size)
    place(img, fit_lockup(6 * b, b, W * 3 // 4, H * 3 // 4, variant), W // 2, H // 2 + dy, snap=b)
    return img


def wordmark_transparent(size, variant, b):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    piece = fit_lockup(6 * b, b, size[0] * 9 // 10, size[1] * 9 // 10, variant)
    place(img, piece, size[0] // 2, size[1] // 2, snap=b)
    return img


def wordmark_paper(size=(1774, 887), b=6):
    W, H = size
    img = enlarge(bg_paper(math.ceil(W / 8), math.ceil(H / 8)), 8, size)
    place(img, fit_lockup(6 * b, b, W * 17 // 20, H * 4 // 5, "paper"), W // 2, H // 2, snap=b)
    return img


def banner(size, a, b, dy=0, bars=1, bats=False, sub_bold=True):
    W, H = size
    aw, ah = math.ceil(W / 8), math.ceil(H / 8)
    img = enlarge(bg_banner(aw, ah, bars, bats), 8, size)
    room = W - 2 * (26 * 8 if bats else round(W * .08))     # keep clear of the bats and the edges
    place(img, fit_lockup(a, b, room, H - 2 * (bars + 3) * 8, "white", sub_bold), W // 2, H // 2 + dy, snap=b)
    return img


def splash(size=(1920, 1080), b=5):
    W, H = size
    img = enlarge(bg_splash(), 8, size)
    wall_top = (135 - 2 - SPLASH_FIELD - WALL_H) * 8
    place(img, fit_lockup(6 * b, b, W * 17 // 20, wall_top - 16 - 64), W // 2, (16 + wall_top) // 2, snap=b)
    return img


HEADER_W, HEADER_H, HEADER_K = 200, 67, 8


def header(title: str, kicker: str, seed: int = 7) -> Image.Image:
    """1600 x 533 channel header on a 200 x 67 art grid: red eyebrow, big title, the baseball on the right."""
    a = art(HEADER_W, HEADER_H, NAVY)
    grain(a, [NAVY_HI, NAVY_LO], .02, seed * 31)
    dither(a, 0, 56, HEADER_W, 9, STANDS)
    rect(a, 9, 10, 2, 47, RED)
    put(a, EMBLEM48(), 141, 9)
    rect(a, 0, 65, HEADER_W, 2, RED)
    img = enlarge(a, HEADER_K, (1600, 533), offset=(0, 1))
    x = 16 * HEADER_K
    draw_text(img, kicker, "silk", 4, x, 100, RED_LT)
    avail = 116 * HEADER_K
    fp = next(s for s in (8, 6, 4, 3) if font("jersey").width(title, s) + s <= avail)
    draw_text(img, title, "jersey", fp, x, 236 - 5 * fp, WHITE, shadow=NAVY_DK)
    draw_text(img, LEAGUE_LINE, "silk", 4, x, 372, MUTED)
    return img


def footer_divider() -> Image.Image:
    """Transparent 1600 x 180: white and red lines running into a pixel baseball (200 x 23 art grid)."""
    a = art(200, 23)
    rect(a, 8, 10, 84, 2, RED)
    rect(a, 108, 10, 84, 2, RED)
    for y, step in ((8, 9), (13, 12)):
        rect(a, 8, y, 83, 1, WHITE)
        rect(a, 91, step, 1, 1, WHITE)
        rect(a, 109, y, 83, 1, WHITE)
        rect(a, 108, step, 1, 1, WHITE)
    put(a, "ball", 93, 4)
    return enlarge(a, 8, (1600, 180), offset=(0, 0))


def thin_rule() -> Image.Image:
    a = art(400, 10)
    rect(a, 16, 1, 368, 1, WHITE)
    rect(a, 16, 3, 368, 4, RED)
    rect(a, 16, 8, 368, 1, WHITE)
    return enlarge(a, 4, (1600, 40))


def red_bar() -> Image.Image:
    a = art(200, 3)
    rect(a, 0, 0, 200, 1, RED_LT)
    rect(a, 0, 1, 200, 1, RED)
    rect(a, 0, 2, 200, 1, RED_DK)
    return enlarge(a, 8, (1600, 24))


def emblem_icon(size: int, color, k: int = 21) -> Image.Image:
    """The large baseball (32 x 32 art) centered on a flat color."""
    img = Image.new("RGBA", (size, size), color + (255,))
    place(img, sprite(EMBLEM32(), k), size // 2, size // 2)
    return img


def emblem_mark(size: tuple[int, int], k: int) -> Image.Image:
    """The large baseball on a transparent ground."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    place(img, sprite(EMBLEM32(), k), size[0] // 2, size[1] // 2)
    return img


def avatar(size: int, color=NAVY, round_=False) -> Image.Image:
    """The small baseball (14 x 14) on a 20 x 20 grid that survives Discord's 40-48 px display."""
    a = art(20, 20, None if round_ else color)
    if round_:
        ring(a, 10, 10, 0, 10, color)
    put(a, "ball", 3, 3)
    return enlarge(a, size // 20, (size, size), pad=None if round_ else color)


def emoji(size: int, bg=None) -> Image.Image:
    a = art(16, 16, bg)
    put(a, "ball", 1, 1)
    return enlarge(a, size // 16, (size, size))


def seal(dark: bool = True, k: int = 4) -> Image.Image:
    """Round official seal on a 256 x 256 art grid (k=4 -> 1024 px, k=1 -> 256 px)."""
    N, m = 256, 128
    fill, ink = (NAVY, WHITE) if dark else (PAPER, NAVY)
    a = art(N, N)
    ring(a, m, m, 0, 117.3, fill)
    ring(a, m, m, 117.3, 124.7, RED)
    ring(a, m, m, 124.7, 128, NAVY_DK)
    ring(a, m, m, 108, 109.6, RED)
    ring(a, m, m, 70.7, 72.3, RED)
    rect(a, 14, 127, 3, 3, RED)
    rect(a, 239, 127, 3, 3, RED)
    e = EMBLEM_SEAL()
    put(a, e, m - len(e[0]) // 2, m - len(e) // 2)
    _arc_text(a, LEAGUE_NAME.upper(), m, 94.5, ink, top=True, fit=math.radians(150))
    _arc_text(a, f"OFFICIAL • EST. {LEAGUE_EST}", m, 95, ink, top=False, fit=math.radians(150))
    return a if k == 1 else enlarge(a, k, (N * k, N * k))


def _arc_text(img, text, c, r, color, top=True, size=24, gap=1.0, fit=None):
    """Text around a circle, each letter rotated and re-thresholded so it stays solid pixels.
    With `fit` (radians), the size steps down until the text spans no more than that angle."""
    while True:
        f = ImageFont.truetype(str(FONTS / "jersey10" / "Jersey10-Regular.ttf"), size)
        widths = [f.getlength(ch) for ch in text]
        total = sum(widths) + gap * (len(text) - 1)
        if fit is None or total / r <= fit or size <= 14:
            break
        size -= 1
    pos = -total / 2
    tint = Image.new("RGBA", (64, 64), color + (255,))
    for ch, w in zip(text, widths):
        th = (pos + w / 2) / r
        pos += w + gap
        if ch == " ":
            continue
        tile = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(tile).text((32, 32), ch, font=f, fill=255, anchor="mm")
        if top:
            tile = tile.rotate(-math.degrees(th), resample=Image.BICUBIC)
            px, py = c + r * math.sin(th), c - r * math.cos(th)
        else:
            tile = tile.rotate(math.degrees(th), resample=Image.BICUBIC)
            px, py = c + r * math.sin(th), c + r * math.cos(th)
        tile = tile.point(lambda v: 255 if v >= 128 else 0)
        img.paste(tint, (round(px - 32), round(py - 32)), tile)


STAMP_W, STAMP_H = 115, 46


def stamp(word: str, color, sub: str | None = None, seed: int = 1) -> Image.Image:
    """916 x 368 transparent status stamp: stepped double frame with a little ink wear."""
    a = art(STAMP_W, STAMP_H)
    frame(a, 2, 2, 111, 42, 2, 3, color, wear=.04, seed=seed)
    frame(a, 5, 5, 105, 36, 1, 2, color)
    img = enlarge(a, 8, (916, 368))
    avail = 90 * 8
    jersey = font("jersey")
    fp = next(s for s in range(8 if sub else 10, 2, -1) if jersey.width(word, s) <= avail)
    if sub:
        sfp = next(s for s in (4, 3, 2) if font("silk").width(sub, s) <= avail - 32)
        gap = 28
        block = 10 * fp + gap + 5 * sfp
        top = (368 - block) // 2
        draw_text(img, word, "jersey", fp, 458, top, color, align="c")
        draw_text(img, sub, "silk", sfp, 458, top + 10 * fp + gap, color, align="c")
    else:
        draw_text(img, word, "jersey", fp, 458, 184 - 5 * fp, color, align="c")
    return img


# ---------------------------------------------------------------- contact sheets
def contact_sheet(title: str, groups, size: tuple[int, int], max_w=480, max_h=300) -> Image.Image:
    """Grid of thumbnails with Silkscreen labels; pixel art is shrunk by whole factors with NEAREST."""
    W, H = size
    sheet = Image.new("RGBA", size, NAVY_DK + (255,))
    draw_text(sheet, title, "jersey", 4, 30, 30, WHITE)
    y = 30 + 40 + 34
    for group, items in groups:
        draw_text(sheet, group, "silk-bold", 3, 30, y, RED_LT)
        y += 15 + 22
        x, rowh = 30, 0
        for name, im in items:
            f = max(1, math.ceil(max(im.width / max_w, im.height / max_h)))
            t = im.convert("RGBA").resize((max(1, im.width // f), max(1, im.height // f)), Image.NEAREST)
            if t.getextrema()[3][0] < 255:  # transparent asset: show it on a checkerboard
                light = _mostly_dark(t)
                tile = Image.new("RGBA", t.size, (PAPER if light else NAVY) + (255,))
                _checker(tile, PAPER_DKR if light else NAVY_HI)
                tile.alpha_composite(t)
                t = tile
            cell = max(t.width, 200)
            lines = _wrap_label(name, cell)
            h = t.height + 8 + 16 * len(lines)
            if x + cell > W - 30:
                x, y, rowh = 30, y + rowh + 28, 0
            sheet.alpha_composite(t, (x, y))
            for i, line in enumerate(lines):
                draw_text(sheet, line, "silk", 2, x, y + t.height + 8 + 16 * i, PAPER)
            x += cell + 24
            rowh = max(rowh, h)
        y += rowh + 52
    if y > H:
        raise ValueError(f"contact sheet needs {y} px but is {H} px tall")
    return sheet


def _wrap_label(name: str, width: int, scale: int = 2) -> list[str]:
    """Break a file name after hyphens so each line fits `width` pixels."""
    silk, lines, cur = font("silk"), [], ""
    for part in [p + "-" for p in name.split("-")[:-1]] + [name.split("-")[-1]]:
        if cur and silk.width(cur + part, scale) > width:
            lines.append(cur)
            cur = ""
        cur += part
    return lines + [cur]


def _checker(tile: Image.Image, color=NAVY_HI, cell: int = 8):
    d = ImageDraw.Draw(tile)
    for y in range(0, tile.height, cell):
        for x in range(0, tile.width, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=color + (255,))


def _mostly_dark(img: Image.Image) -> bool:
    """True when most opaque pixels are dark (a navy wordmark needs a light backdrop)."""
    lum = img.convert("L").load()
    alpha = img.getchannel("A").load()
    dark = total = 0
    for y in range(0, img.height, 2):
        for x in range(0, img.width, 2):
            if alpha[x, y] > 128:
                total += 1
                dark += lum[x, y] < 60
    return total > 0 and dark / total > .4


def save(path: Path, img: Image.Image, mode: str = "RGBA") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert(mode).save(path, "PNG", optimize=True)
