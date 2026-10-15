"""PSBL static emoji, group A (22 emoji): the league ball, baseball gear, the field and reaction props.

Run:  python static_a.py          -> writes static/<name>.png for all 22 and static_a_sheet.png
      python static_a.py name ... -> only those (sheet still covers all files that exist)
Deterministic: no randomness. File names keep the dbl_ prefix.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "tools"))
from pix import Canvas, face, save_png, sheet  # noqa: E402

TURF, TURF_LT = (15, 44, 80), (20, 54, 96)       # the outfield, mown in navy stripes (as in tools/pixel_kit.py)
CLAY_DK = (114, 40, 44)
BALL_SHADE = (214, 221, 231)
MOUTH = (90, 18, 20)
TAR, TAR_DK = (92, 56, 26), (58, 34, 14)


# --- helpers -------------------------------------------------------------------------------
def grid(text: str) -> list[str]:
    """A multi-line string -> stamp rows (blank first/last lines dropped, '.' transparent)."""
    rows = text.strip("\n").split("\n")
    return [r.rstrip() for r in rows]


def sym(text: str, odd: bool = False) -> list[str]:
    """Left half rows -> mirrored full rows (even width, or odd with the last column as the center).
    Half rows are padded to the same width first so the mirror lines up."""
    rows = grid(text)
    n = max(len(r) for r in rows)
    rows = [r.ljust(n, ".") for r in rows]
    return [r + (r[-2::-1] if odd else r[::-1]) for r in rows]


def rrect(c: Canvas, x, y, w, h, r, col):
    """Filled rectangle with rounded corners of radius r."""
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            cx = min(max(xx + .5, x + r), x + w - r)
            cy = min(max(yy + .5, y + r), y + h - r)
            if (xx + .5 - cx) ** 2 + (yy + .5 - cy) ** 2 <= r * r + .25:
                c.px(xx, yy, col)


def capsule(c: Canvas, x0, y0, x1, y1, r, col):
    """Filled stadium shape: every pixel within r of the segment (x0, y0)-(x1, y1)."""
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy or 1
    for y in range(c.h):
        for x in range(c.w):
            px, py = x + .5, y + .5
            t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2))
            qx, qy = x0 + t * dx - px, y0 + t * dy - py
            if qx * qx + qy * qy <= r * r:
                c.px(x, y, col)


def recenter(c: Canvas, dy_bias: int = 0) -> Canvas:
    """Move the drawing so its bounding box sits in the middle of the 32 x 32 frame."""
    l, t, r, b = c.img.getbbox()
    w, h = r - l, b - t
    nx, ny = (c.w - w) // 2, (c.h - h) // 2 + dy_bias
    ny = max(0, min(c.h - h, ny))
    crop = c.img.crop((l, t, r, b))
    c.img = c.img.copy()
    c.img.paste((0, 0, 0, 0), (0, 0, c.w, c.h))
    c.img.alpha_composite(crop, (nx, ny))
    return c


def clear_outer(c: Canvas, key="K"):
    """Make keyline pixels that touch the outside transparent (so outline() can redraw them)."""
    from pix import col as _col
    k = _col(key)
    seen, stack = set(), [(x, y) for x in range(c.w) for y in (0, c.h - 1)] + \
        [(x, y) for y in range(c.h) for x in (0, c.w - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < c.w and 0 <= y < c.h):
            continue
        p = c.get(x, y)
        if p[3] and p != k:
            continue
        seen.add((x, y))
        if p[3]:
            c.px(x, y, None)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]



def ball_into(c: Canvas, d: int, x: int, y: int):
    """The league's baseball (tools/pixel_kit.ball_body) at d x d with its top-left at (x, y)."""
    import pixel_kit
    tint = {"W": "W", "T": BALL_SHADE, "R": "R"}
    for j, row in enumerate(pixel_kit.ball_body(d)):
        for i, ch in enumerate(row):
            if ch != ".":
                c.px(x + i, y + j, tint[ch])


def fill_where(c: Canvas, test, color):
    for y in range(c.h):
        for x in range(c.w):
            if test(x + .5, y + .5):
                c.px(x, y, color)


def chunky(c: Canvas, shape_fn, main, light, dark, depth=2):
    """Arcade letter: an extruded dark copy below/right, the face on top, a light top-left bevel."""
    m = Canvas()
    shape_fn(m)
    filled = lambda x, y: 0 <= x < 32 and 0 <= y < 32 and m.get(x, y)[3] > 0  # noqa: E731
    for d in range(depth, 0, -1):
        for y in range(32):
            for x in range(32):
                if filled(x, y):
                    c.px(x + d, y + d, dark)
    for y in range(32):
        for x in range(32):
            if filled(x, y):
                c.px(x, y, light if (not filled(x, y - 1) or not filled(x - 1, y)) else main)


# --- 1. the league ball ----------------------------------------------------------------------
def dbl_ball():
    c = Canvas()
    ball_into(c, 28, 2, 2)
    return recenter(c.outline())


# --- 2. dinger: a ball launched toward the seats ---------------------------------------------
def dbl_dinger():
    c = Canvas()
    for (x0, y0, x1, y1, w, col) in ((15, 13, 2, 29, 3, "I"), (18, 16, 7, 30, 2, "L"), (12, 11, 1, 22, 2, "L"),
                                     (16, 14, 5, 26, 1, "W")):
        c.line(x0, y0, x1, y1, col, w)
    ball_into(c, 16, 14, 1)
    for x, y in ((4, 6), (8, 2), (27, 22)):
        c.px(x, y, "W"); c.px(x - 1, y, "Y"); c.px(x + 1, y, "Y"); c.px(x, y - 1, "Y"); c.px(x, y + 1, "Y")
    return recenter(c.outline())


# --- 3. bat ------------------------------------------------------------------------------------
def dbl_bat():
    c = Canvas()
    x0, y0, x1, y1 = 4.0, 28.0, 28.5, 3.5          # knob to barrel end
    L = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    LITE = (222, 170, 108)

    def radius(t):
        if t < .05:
            return 2.3                              # the knob
        if t < .42:
            return 1.15                             # handle
        if t < .78:
            return 1.15 + (t - .42) / .36 * 2.0     # taper up
        return 3.15                                 # barrel

    for y in range(32):
        for x in range(32):
            px_, py_ = x + .5 - x0, y + .5 - y0
            t = (px_ * ux + py_ * uy) / L
            d = -px_ * uy + py_ * ux                     # signed distance across the bat
            if -.02 <= t <= 1.0 and abs(d) <= radius(t):
                if t > .97 and abs(d) > radius(t) - 1.2:
                    continue                             # round the barrel end
                col = "R" if .07 < t < .3 else ("u" if t <= .07 else "O")
                if col == "O":
                    col = "o" if d > radius(t) - 1.1 else (LITE if d < -radius(t) + 1.1 else "O")
                c.px(x, y, col)
    return recenter(c.outline())


# --- 4. catcher's mask ---------------------------------------------------------------------------
def dbl_catcher():
    c = Canvas()
    rrect(c, 6, 1, 20, 26, 7, "n")                  # padded frame
    rrect(c, 9, 5, 14, 18, 4, "A")                   # the opening
    for x in (12, 16, 19):                           # cage bars
        c.rect(x, 4, 1, 20, "S")
    for y in (9, 14, 19):
        c.rect(8, y, 16, 1, "S")
    c.rect(12, 4, 1, 20, "W"); c.rect(8, 9, 16, 1, "W")
    for x, y in ((8, 3), (9, 2), (10, 2), (7, 5), (7, 6)):
        c.px(x, y, "B")                              # sheen on the pads
    c.rect(3, 8, 3, 3, "R"); c.rect(26, 8, 3, 3, "R")                 # strap buckles
    c.rect(1, 9, 2, 1, "u"); c.rect(29, 9, 2, 1, "u")
    rrect(c, 12, 25, 8, 6, 2, "S"); c.rect(13, 26, 6, 1, "W"); c.rect(13, 29, 6, 1, "N")   # throat guard
    return recenter(c.outline())


# --- 5. cleat ------------------------------------------------------------------------------------
def dbl_cleat():
    c = Canvas()
    c.poly([(3, 11), (9, 9), (15, 11), (21, 15), (27, 17), (30, 20), (30, 23), (3, 23)], "n")
    c.rect(4, 10, 6, 2, "A")                          # the opening
    c.rect(2, 12, 3, 10, "R")                         # heel tab
    for i in range(6):                                # laces
        c.px(12 + i * 2, 13 + i, "W"); c.px(13 + i * 2, 13 + i, "W")
    c.line(7, 20, 22, 19, "W", 1); c.line(8, 21, 26, 20, "R", 1)   # side stripe
    for x, y in ((10, 12), (16, 13), (23, 17), (27, 19)):
        c.px(x, y, "B")
    c.rect(2, 23, 29, 2, "W"); c.rect(2, 24, 29, 1, "I")             # midsole
    c.rect(2, 25, 29, 1, "N")
    for x in (4, 9, 18, 23, 28):                      # spikes
        c.rect(x, 26, 2, 2, "S"); c.px(x, 27, "N")
    return recenter(c.outline())


# --- 6. batting helmet ----------------------------------------------------------------------------
def dbl_helmet():
    c = Canvas()
    fill_where(c, lambda X, Y: ((X - 17) / 12.5) ** 2 + ((Y - 16) / 12) ** 2 <= 1 and Y <= 21, "n")
    c.poly([(1, 19), (12, 16), (13, 21), (1, 23)], "n")              # brim
    c.rect(1, 22, 11, 1, "R")                                        # red edge on the brim
    c.poly([(17, 18), (29, 17), (28, 28), (20, 29), (15, 24)], "n")  # ear flap
    c.circle(22, 22, 2, "A"); c.px(22, 22, "K")                       # ear hole
    for x, y in ((9, 8), (10, 7), (11, 6), (12, 5), (13, 5), (8, 9), (8, 10)):
        c.px(x, y, "B")
    c.px(11, 8, "W"); c.px(12, 7, "W")
    for x, y in ((18, 6), (23, 8), (26, 12)):                         # vents
        c.px(x, y, "A")
    c.rect(16, 21, 3, 1, "B")
    return recenter(c.outline())


# --- 7. jersey (from the back, inaugural-season number) ----------------------------------------
def dbl_jersey():
    c = Canvas()
    c.poly([(9, 2), (13, 1), (19, 1), (23, 2), (31, 8), (28, 15), (25, 13), (25, 30), (7, 30), (7, 13), (4, 15), (1, 8)], "n")
    c.rect(13, 1, 6, 2, "R")                                          # collar
    c.rect(14, 3, 4, 1, "u")
    c.line(28, 14, 31, 8, "R"); c.line(4, 14, 1, 8, "R")             # sleeve trim
    c.line(27, 14, 30, 8, "W"); c.line(5, 14, 2, 8, "W")
    digits = {"2": ["###", "..#", "###", "#..", "###"], "7": ["###", "..#", "..#", ".#.", ".#."]}
    x = 9
    for ch in "27":                                                   # the number, 2x scale, red with a white shadow
        for j, row in enumerate(digits[ch]):
            for i, bit in enumerate(row):
                if bit == "#":
                    c.rect(x + 2 * i + 1, 12 + 2 * j + 1, 2, 2, "W")
        for j, row in enumerate(digits[ch]):
            for i, bit in enumerate(row):
                if bit == "#":
                    c.rect(x + 2 * i, 12 + 2 * j, 2, 2, "R")
        x += 8
    for x, y in ((10, 4), (8, 6)):
        c.px(x, y, "B")
    return recenter(c.outline())


# --- 8. the diamond from above ----------------------------------------------------------------------
def dbl_diamond():
    c = Canvas()
    hx, hy = 15.5, 29.5                                               # home plate
    def fan(X, Y, r):
        a = math.degrees(math.atan2(hy - Y, X - hx))
        return 45 <= a <= 135 and math.hypot(X - hx, Y - hy) <= r
    fill_where(c, lambda X, Y: fan(X, Y, 28.5), "c")                  # warning track
    for y in range(32):
        for x in range(32):
            if fan(x + .5, y + .5, 26.5):
                c.px(x, y, TURF_LT if ((x + y) // 4) % 2 else TURF)   # mown outfield
    c.poly([(15.5, 30.5), (25, 21), (15.5, 11.5), (6, 21)], "c")       # infield dirt
    c.poly([(15.5, 27.5), (22, 21), (15.5, 14.5), (9, 21)], TURF)     # infield grass
    c.circle(15, 20, 1.5, "c"); c.px(15, 20, "W")                     # the mound
    c.line(15, 29, 1, 15, "W"); c.line(16, 29, 30, 15, "W")           # foul lines
    for x, y in ((23, 20), (15, 12), (7, 20)):
        c.rect(x, y, 2, 2, "W")                                       # bases
    c.rect(15, 28, 2, 2, "W")
    return recenter(c.outline())


# --- 9. umpire ---------------------------------------------------------------------------------------
def dbl_umpire():
    c = face(cy=17.5, r=12)
    fill_where(c, lambda X, Y: ((X - 16) / 12.5) ** 2 + ((Y - 10) / 7.5) ** 2 <= 1 and Y <= 10.5, "n")   # cap
    c.rect(3, 10, 26, 2, "n"); c.rect(3, 11, 26, 1, "A")              # short brim
    c.px(10, 5, "B"); c.px(11, 4, "B"); c.px(12, 4, "B")
    for ex, d in ((9, 1), (20, 0)):                                   # stern brows and eyes
        c.line(ex, 13 + d, ex + 3, 14 - d, "K")
        c.rect(ex + 1, 15, 2, 3, "K")
    fill_where(c, lambda X, Y: ((X - 16) / 5) ** 2 + ((Y - 24) / 3.6) ** 2 <= 1, MOUTH)   # yelling
    c.rect(13, 21, 6, 1, "W")
    fill_where(c, lambda X, Y: ((X - 16) / 3) ** 2 + ((Y - 26.5) / 1.6) ** 2 <= 1, "r")
    return recenter(c.outline())


# --- 10. ejected: the umpire's thumb, heave-ho ---------------------------------------------------------
def dbl_ejected():
    c = Canvas()
    capsule(c, 27.5, 31, 19, 19, 4.2, "n")                            # sleeve
    capsule(c, 21.5, 23.5, 18.5, 19.5, 4.4, "W")                      # cuff
    capsule(c, 26.5, 31, 21.5, 24, 3.6, "n")
    rrect(c, 9, 11, 12, 11, 4, "G")                                   # fist, seen from the side
    for y in (14, 17, 20):
        c.rect(11, y, 8, 1, "D")                                      # curled fingers
    for y in (12, 15, 18):
        c.px(20, y, "Y"); c.px(20, y + 1, "Y")                        # knuckles catching the light
    c.rect(9, 13, 1, 7, "D")
    capsule(c, 12, 12, 7.5, 3.5, 2.1, "G")                            # the thumb, jerked back
    c.px(6, 3, "Y"); c.px(7, 2, "Y")
    for a in range(200, 300, 12):                                     # whoosh
        x = 14 + 11 * math.cos(math.radians(a)); y = 15 + 11 * math.sin(math.radians(a))
        c.px(int(x), int(y), "W")
    return recenter(c.outline())


# --- 11. pine tar --------------------------------------------------------------------------------------
def dbl_pine_tar():
    c = Canvas()
    c.rect(7, 10, 18, 20, "S")                                         # the tin
    c.rect(7, 10, 2, 20, "W"); c.rect(22, 10, 3, 20, "N")
    c.ellipse(15.5, 29, 9, 1.5, "N")
    c.rect(7, 16, 18, 8, "R"); c.rect(7, 23, 18, 1, "u")             # label
    c.text(10, 18, "TAR", "W")
    c.ellipse(15.5, 9, 9, 2.5, "N")                                    # rim
    c.ellipse(15.5, 8.5, 8, 1.5, TAR)                                  # the goo
    for x, n in ((9, 3), (14, 5), (20, 4), (23, 2)):                   # drips
        c.rect(x, 10, 2, n, TAR); c.px(x + 1, 10 + n, TAR_DK)
    c.px(12, 8, (140, 96, 48)); c.px(13, 8, (140, 96, 48))
    c.line(19, 8, 27, 0, "O", 2); c.line(20, 8, 28, 0, "o")           # the stir stick
    return recenter(c.outline())


# --- 12. fielder's glove with a ball in the pocket --------------------------------------------------------
def dbl_glove():
    c = Canvas()
    for (xa, ya, xb, yb) in ((13, 15, 12, 4), (17, 14, 17, 2), (21, 14, 22, 4), (25, 17, 27, 8)):
        capsule(c, xa, ya, xb, yb, 2.4, "O")                           # fingers
    c.ellipse(17, 20, 10, 9, "O")                                       # palm
    capsule(c, 7, 24, 4.5, 11, 2.8, "O")                               # thumb
    web = Canvas()
    web.poly([(5, 9), (11.5, 5), (13, 14), (8, 18)], "o")
    for y in range(32):
        for x in range(32):
            if web.get(x, y)[3] and not c.get(x, y)[3]:
                c.px(x, y, "o" if (x + y) % 3 else "O")               # laced web
    for xx in (15, 19, 23):                                            # finger seams
        c.line(xx, 5 if xx != 23 else 7, xx, 14, "o")
    for x, y in ((11, 3), (16, 1), (21, 3), (26, 7), (3, 11)):
        c.px(x, y, "R"); c.px(x + 1, y, "R")                           # red lacing on the tips
    c.rect(9, 27, 16, 3, "o"); c.rect(9, 28, 16, 1, "R")               # wrist strap
    ball_into(c, 10, 13, 16)
    return recenter(c.outline())


# --- 13. home plate ------------------------------------------------------------------------------------------
def dbl_plate():
    c = Canvas()
    rrect(c, 1, 1, 30, 30, 5, "c")
    for x, y in ((5, 4), (26, 3), (8, 27), (24, 26), (14, 4), (19, 28), (3, 16), (28, 18)):
        c.px(x, y, CLAY_DK)
    c.frame(2, 6, 6, 19, "W"); c.frame(24, 6, 6, 19, "W")             # batter's boxes
    c.poly([(9.5, 8.5), (22.5, 8.5), (22.5, 15.5), (16, 22.5), (9.5, 15.5)], "W")   # the plate
    c.line(22, 9, 22, 15, "I"); c.line(22, 15, 16, 21, "I")
    c.line(10, 9, 22, 9, "S")
    return recenter(c.outline())


# --- 14. K: the strikeout -----------------------------------------------------------------------------------------
def dbl_k():
    c = Canvas()

    def shape(m):
        m.rect(4, 2, 7, 26, "R")
        m.poly([(10, 14), (20, 2), (28, 2), (15, 17)], "R")
        m.poly([(13, 13), (17, 12), (28, 28), (20, 28)], "R")
    chunky(c, shape, "R", "r", "u", depth=3)
    return recenter(c.outline())


# --- 15. batting glove -------------------------------------------------------------------------------------------
def dbl_mitt():
    c = Canvas()
    for (xa, ya, xb, yb) in ((10.5, 14, 10, 4.5), (14.5, 13, 14.5, 2.5), (18.5, 13, 19, 3.5), (22.5, 14, 23.5, 6.5)):
        capsule(c, xa, ya, xb, yb, 1.9, "W")
    rrect(c, 8, 12, 17, 13, 3, "W")
    capsule(c, 9, 20, 4, 13, 2.1, "W")                                 # thumb
    for y in range(32):                                                # navy fingertips
        for x in range(32):
            if c.get(x, y)[3] and y <= 7:
                c.px(x, y, "n")
    for x in (12, 16, 20):
        c.line(x + .5, 8, x + .5, 13, "I")                             # knuckle seams
    rrect(c, 11, 15, 11, 6, 2, "n")                                    # back-of-hand panel
    c.rect(12, 16, 3, 1, "B")
    c.rect(9, 24, 15, 4, "R"); c.rect(9, 27, 15, 1, "u")               # velcro strap
    c.rect(10, 28, 13, 3, "n")                                         # cuff
    c.rect(21, 20, 3, 3, "I"); c.rect(23, 24, 2, 3, "r")               # strap tab
    return recenter(c.outline())


# --- kept from the first set, recolored -------------------------------------------------------
def _silver_band(c, x0, x1, y0, y1):
    c.rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, "S")
    c.rect(x0 + 1, y0, 1, y1 - y0 + 1, "W")
    c.rect(x1 - 1, y0, 2, y1 - y0 + 1, "N")


def dbl_cup():
    """The championship trophy: a two-handled silver cup with a red band on a navy base."""
    c = Canvas()
    for cx in (5.5, 26.5):                                            # handles
        fill_where(c, lambda X, Y, cx=cx: 2.2 <= math.hypot(X - cx, Y - 8.5) <= 4.2 and abs(X - 16) > 9, "S")
    c.poly([(7, 3), (25, 3), (24.5, 10), (20.5, 15.5), (11.5, 15.5), (7.5, 10)], "S")   # bowl
    c.rect(6, 2, 20, 2, "W"); c.rect(6, 3, 20, 1, "I")                # rim
    for y in range(4, 16):                                            # light left, dark right
        xs = [x for x in range(32) if c.get(x, y)[:3] == (154, 161, 169) and 6 <= x <= 25]
        if xs:
            c.px(xs[0] + 1, y, "W"); c.px(xs[-1], y, "N"); c.px(xs[-1] - 1, y, "N")
    for y in (7, 8):
        for x in range(8, 25):
            if c.get(x, y)[:3] in ((154, 161, 169), (255, 255, 255), (110, 116, 124)):
                c.px(x, y, "R" if y == 7 else "u")
    c.rect(14, 16, 4, 4, "S"); c.rect(14, 16, 1, 4, "W"); c.rect(17, 16, 1, 4, "N")   # stem
    c.rect(11, 20, 10, 2, "S"); c.rect(11, 20, 10, 1, "W")            # knot
    c.rect(9, 22, 14, 3, "n"); c.rect(7, 25, 18, 5, "n")              # base
    c.rect(9, 22, 14, 1, "B"); c.rect(7, 25, 18, 1, "B")
    c.rect(11, 26, 10, 3, "I"); c.rect(12, 27, 8, 1, "S")             # name plate
    return recenter(c.outline())


def dbl_banner():
    c = Canvas()
    c.poly([(6, 5), (26, 5), (26, 31), (16, 25), (6, 31)], "R")
    c.rect(6, 5, 1, 26, "r")
    c.rect(24, 5, 2, 26, "u")
    c.rect(6, 5, 20, 2, "u")
    c.rect(2, 3, 28, 2, "o"); c.rect(2, 3, 28, 1, "O")
    c.stamp(grid("""
.WW.
WSSW
WSSN
.NN.
"""), 0, 2)
    c.stamp(grid("""
.WW.
WSSW
WSSN
.NN.
"""), 28, 2)
    c.stamp(grid("""
WWWWWWWWWW
W.WWWWWS.W
W.WWWWWS.W
.WWWWWWSW.
..WWWWS...
....WS....
...WWWS...
..WWWWWS..
"""), 11, 7)
    c.rect(8, 17, 16, 7, "n")
    c.text(9, 18, "2027", "W")
    return recenter(c.outline())


def dbl_beer():
    c = Canvas()
    c.rect(4, 9, 18, 21, "I")                    # glass
    c.rect(5, 10, 16, 17, "G")                   # beer
    c.rect(5, 10, 1, 17, "Y"); c.rect(18, 10, 3, 17, "D")
    for x, y in ((8, 22), (11, 18), (14, 24), (9, 14), (15, 15), (12, 21)):
        c.px(x, y, "Y")
    c.rect(4, 27, 18, 3, "S"); c.rect(5, 27, 16, 1, "I")
    c.rect(4, 9, 1, 21, "W")
    # handle
    c.rect(22, 12, 4, 2, "I"); c.rect(22, 23, 4, 2, "I"); c.rect(25, 13, 3, 11, "I")
    c.rect(26, 14, 1, 9, "S")
    # foam
    for cx, cy, r in ((7, 6, 3), (12, 4.5, 3.5), (17.5, 5.5, 3), (21, 8, 2), (5, 9, 2)):
        c.circle(cx, cy, r, "W")
    c.rect(3, 9, 20, 2, "W")
    c.rect(3, 11, 2, 3, "W"); c.rect(20, 11, 2, 2, "W")
    for x, y in ((8, 9), (9, 9), (14, 9), (15, 9), (16, 8), (10, 8), (19, 10)):
        c.px(x, y, "C")
    return recenter(c.outline())


def dbl_bottle():
    c = Canvas()
    rrect(c, 8, 11, 16, 20, 3, "L")
    c.rect(9, 17, 14, 12, "b")
    rrect(c, 8, 17, 16, 14, 3, "b")
    c.rect(8, 11, 16, 6, "L")
    for y in (20, 23, 26):
        c.rect(9, y, 14, 1, "B")
    c.rect(10, 12, 1, 16, "W")
    c.rect(9, 7, 14, 4, "R")
    for x in range(10, 22, 2):
        c.rect(x, 7, 1, 4, "u")
    c.rect(10, 6, 12, 1, "R")
    c.line(15, 5, 21, 0, "W", 2)
    c.line(14, 5, 20, 0, "S")
    return recenter(c.outline())


def _shaker(u, v):
    """Material of the salt shaker at local point (u across, v up from the foot), or None."""
    if 0 <= v < 17 and abs(u) <= 7.5:                           # glass body
        if v < 1.5:
            return "N" if v < .8 else "S"
        if u < -5.8:
            return "W"
        if u > 5.8:
            return "S"
        if v < 11.5:                                            # salt inside
            return "C" if ((int(u * 3) * 7 + int(v) * 5) % 23 == 0) else "W"
        return "S" if abs(u - 1) < .5 or abs(u + 3) < .5 else "I"
    if 17 <= v < 20 and abs(u) <= 8.5:                          # threaded collar
        return "S" if 18 <= v < 19 else "N"
    if v >= 20 and (u / 8.5) ** 2 + ((v - 20) / 7) ** 2 <= 1:   # chrome dome with holes
        for hu, hv in ((-4, 22), (0, 23), (4, 22), (-2, 25.5), (2, 25.5)):
            if abs(u - hu) < .75 and abs(v - hv) < .75:
                return "K"
        if u < -3 and v > 22:
            return "W"
        if u > 5:
            return "N"
        return "S"
    return None


def dbl_salty():
    import math
    big = Canvas(64, 64)
    th = math.radians(28)                                       # tipped over to shake out salt
    ox, oy, sc = 24.0, 50.0, .86                                # foot center on the scratch canvas, scale
    for y in range(64):
        for x in range(64):
            dx, dy = x + .5 - ox, oy - (y + .5)
            k = _shaker((dx * math.cos(th) - dy * math.sin(th)) / sc, (dx * math.sin(th) + dy * math.cos(th)) / sc)
            if k:
                big.px(x, y, k)
    tx, ty = ox + 27 * sc * math.sin(th), oy - 27 * sc * math.cos(th)   # top of the dome
    for gx, gy in ((2, -3), (6, -6), (6, -1), (10, -3), (10, 2)):
        big.px(int(tx + gx), int(ty + gy), "W")                 # salt flying out of the cap
    l, t, r, b = big.img.getbbox()
    assert r - l <= 30 and b - t <= 30, (r - l, b - t)
    c = Canvas()
    c.img.alpha_composite(big.img.crop((l, t, r, b)), (1, 1))
    return recenter(c.outline())


def dbl_crown():
    c = Canvas()
    c.poly([(3, 21), (2.5, 8), (6.5, 15), (9.5, 6), (12.5, 14), (16, 3), (19.5, 14), (22.5, 6), (25.5, 15),
            (29.5, 8), (29, 21)], "G")
    c.rect(3, 19, 26, 8, "G")
    c.rect(3, 19, 26, 1, "Y"); c.rect(3, 25, 26, 2, "D")
    for cx, cy in ((2, 7), (9, 5), (15.5, 2), (22, 5), (29, 7)):
        c.circle(cx, cy, 1, "Y")
    c.stamp(grid("""
.RR.
RrRR
RRRR
.RR.
"""), 14, 20)
    for x in (7, 22):
        c.stamp(grid("""
.B.
BLB
.B.
"""), x, 21)
    return recenter(c.outline())


def dbl_trash():
    c = Canvas()
    c.poly([(6, 15), (26, 15), (24, 31), (8, 31)], "S")              # can
    for x in (11, 15, 19, 23):
        c.line(x, 17, x, 29, "N")                                    # ribs
    c.rect(8, 17, 1, 12, "W")
    c.ellipse(15.5, 14, 10, 2, "S")                                  # rim seen a little from above
    c.ellipse(15.5, 14, 8, 1, "A")                                   # dark opening
    c.rect(5, 16, 22, 1, "N")
    c.stamp(grid("""
...WWWS...
.WWSWWWSC.
WWWWSWWWSC
WSWWWSSWWC
.WWSWWWWC.
..CWWSCC..
"""), 13, 8)                                                         # crumpled paper ball
    c.poly([(1, 9), (13, 3), (15, 6), (3, 12)], "N")                 # lid knocked open
    c.line(2, 9, 13, 4, "S")
    c.stamp(grid("""
.SS.
S..S
"""), 5, 4)                                                          # lid handle
    return recenter(c.outline())


EMOJI = [dbl_ball, dbl_dinger, dbl_bat, dbl_catcher, dbl_cleat, dbl_helmet, dbl_jersey, dbl_diamond,
         dbl_cup, dbl_banner, dbl_beer, dbl_umpire, dbl_ejected, dbl_pine_tar, dbl_bottle,
         dbl_mitt, dbl_glove, dbl_plate, dbl_k, dbl_salty, dbl_crown, dbl_trash]


def main(names=None):
    out = []
    for fn in EMOJI:
        p = HERE / "static" / f"{fn.__name__}.png"
        if not names or fn.__name__ in names:
            save_png(fn(), p)
        out.append(p)
    sheet([p for p in out if p.exists()], HERE / "static_a_sheet.png")


if __name__ == "__main__":
    main(sys.argv[1:])
