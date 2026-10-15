#!/usr/bin/env python3
"""PSBL animated emoji, group anim_c (18 GIFs): the ballpark set. File names keep the dbl_ prefix.

    python3 anim_c.py              # writes animated/dbl_<name>.gif for all 18 + anim_c_sheet.png
    python3 anim_c.py swing homer  # just those (no sheet)

Drawn on the 32 x 32 pix.Canvas and exported x4, like anim_a.py and anim_b.py (whose helpers it uses).
League players wear red, opponents bright navy; the ball is white with red seams. Deterministic.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pix  # noqa: E402
from pix import Canvas  # noqa: E402
from anim_a import blit, finish, gif_info, layer, rot, sparkle, speed_lines, sprite, star  # noqa: E402
from anim_b import keyline, make_fist, put  # noqa: E402

OUT = HERE / "animated"
SKIN = (238, 196, 156)
TURF, TURF_LT = (15, 44, 80), (20, 54, 96)
CLAY_DK, CLAY_LT = (114, 40, 44), (160, 66, 66)
WOOD_LT = (222, 170, 108)
LED_OFF = (52, 30, 36)

BALL5 = [".WWW.", "RWWWR", "WRWRW", "RWWWR", ".WWW."]          # seams ) ( facing us
BALL5_TURN = [".RWR.", "WWWWW", "WRWRW", "WWWWW", ".RWR."]     # a quarter turn later
BALL3 = [".W.", "WWW", ".W."]

DIGITS = {  # 3 x 5, also used at 2x for LEDs and scoreboards
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"], "2": ["###", "..#", "###", "#..", "###"],
    "3": ["###", "..#", "###", "..#", "###"], "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", "..#", "..#"], "8": ["###", "#.#", "###", "#.#", "###"],
    "9": ["###", "#.#", "###", "..#", "###"], "-": ["...", "...", "###", "...", "..."], " ": ["...", "...", "...", "...", "..."],
}
EMOJI: dict[str, callable] = {}


def anim(name):
    def deco(fn):
        EMOJI[name] = fn
        return fn
    return deco


# ----------------------------------------------------------------------------------------------
# shared pieces
# ----------------------------------------------------------------------------------------------
def ball_layer(x, y, rows=BALL5) -> Canvas:
    """A ball on its own outlined layer, top-left of the ball (not its keyline) at x, y."""
    L = Canvas()
    L.stamp(rows, int(round(x)), int(round(y)))
    return L.outline()


def clay(c: Canvas, y0: int, y1: int, seed: int = 1, rough: float = .22):
    rng = random.Random(seed)
    for y in range(y0, y1 + 1):
        for x in range(32):
            t = rng.random()
            c.px(x, y, CLAY_DK if t < rough * .7 else (CLAY_LT if t < rough else "c"))


def turf(c: Canvas, y0: int, y1: int):
    for y in range(y0, y1 + 1):
        for x in range(32):
            c.px(x, y, TURF_LT if ((x + y) // 4) % 2 else TURF)


def bat_sprite(length=23) -> Canvas:
    """A bat lying flat, knob at x = 0, barrel to the right (5 px tall, centered on y = 2.5)."""
    b = Canvas(length, 5)
    for x in range(length):
        t = x / (length - 1)
        r = 1.5 if t < .05 else (.6 if t < .42 else min(2.2, .6 + (t - .42) / .3 * 1.6))
        for y in range(5):
            d = y + .5 - 2.5
            if abs(d) <= r:
                if .06 < t < .3:
                    col = "R"
                elif t <= .06:
                    col = "u"
                else:
                    col = WOOD_LT if d < -r + 1 else ("o" if d > r - 1 else "O")
                b.px(x, y, col)
    b.px(length - 1, 0, None); b.px(length - 1, 4, None)
    return b


def gloves(c: Canvas, x, y):
    """Two batting gloves gripping the handle around (x, y)."""
    c.rect(x - 2, y - 2, 4, 4, "W"); c.rect(x - 2, y + 1, 4, 1, "R")
    c.rect(x + 1, y - 2, 3, 4, "W"); c.px(x + 3, y - 2, "I")


def led_digits(c: Canvas, x, y, text, on="R", glint="r", off=LED_OFF, scale=2):
    for ch in text:
        for j, row in enumerate(DIGITS[ch]):
            for i, bit in enumerate(row):
                X, Y = x + i * scale, y + j * scale
                if bit == "#":
                    c.rect(X, Y, scale, scale, on)
                    if glint:
                        c.px(X, Y, glint)
                elif off:
                    c.rect(X, Y, scale, scale, off)
        x += 3 * scale + 2


# ----------------------------------------------------------------------------------------------
# drag: the grounds-crew tractor drags the infield smooth
# ----------------------------------------------------------------------------------------------
@anim("drag")
def drag():
    rng = random.Random(3)
    Y0, H = 25, 6
    rough = {}
    for x in range(32):
        for y in range(Y0, Y0 + H):
            t = rng.random()
            rough[(x, y)] = CLAY_DK if t < .22 else (CLAY_LT if t < .32 else "c")

    def ground(c, gx):
        for (x, y), v in rough.items():
            if x < gx:
                v = CLAY_LT if (y - Y0) % 2 == 1 else "c"           # fresh drag lines
            c.px(x, y, v)

    def machine(c, x0, f):
        c.rect(x0 - 10, 23, 7, 2, "N")                             # the drag mat
        for i in range(x0 - 10, x0 - 3, 2):
            c.px(i, 23, "S")
        c.line(x0 - 3, 23, x0 - 1, 20, "S")                       # chain
        c.rect(x0, 14, 15, 7, "W")                                 # body
        c.rect(x0, 18, 15, 2, "R")
        c.rect(x0 + 15, 15, 2, 6, "W"); c.px(x0 + 16, 16, "r")    # nose, headlight
        c.rect(x0 + 2, 6, 12, 1, "B")                              # canopy
        c.rect(x0 + 3, 7, 1, 7, "N"); c.rect(x0 + 12, 7, 1, 7, "N")
        c.rect(x0 + 6, 8, 3, 1, "R")                               # driver: red cap
        c.rect(x0 + 6, 9, 3, 2, SKIN)
        c.rect(x0 + 5, 11, 5, 3, "n")
        c.rect(x0 + 10, 11, 1, 3, "N")                             # steering column
        for wx, r in ((x0 + 4, 2), (x0 + 13, 2)):
            c.circle(wx, 22, r, "A")
            c.px(wx, 22, "S")
            if f % 2:
                c.px(wx - 1, 22, "N"); c.px(wx + 1, 22, "N")
            else:
                c.px(wx, 21, "N"); c.px(wx, 23, "N")

    frames, durs = [], []
    for f, x0 in enumerate(range(-8, 38, 4)):
        c = Canvas()
        ground(c, x0 - 3)
        machine(c, x0, f)
        frames.append(finish(c)); durs.append(80)
    for spots in ([(7, 21, 1), (20, 20, 2)], [(13, 20, 2), (26, 21, 1)]):
        c = Canvas()
        ground(c, 40)
        for x, y, r in spots:
            sparkle(c, x, y, r)
        frames.append(finish(c)); durs.append(130)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# homer: the ball sails over the outfield fence, HR lights up
# ----------------------------------------------------------------------------------------------
@anim("homer")
def homer():
    path = [(0, 25), (3, 18), (6, 12), (9, 8), (12, 5), (15, 3), (18, 3), (21, 4), (24, 6), (27, 8), (30, 10), (36, 12)]

    def scene(hr=0):
        c = Canvas()
        turf(c, 28, 31)
        c.rect(20, 15, 12, 13, "n")                                 # the fence
        for x in (24, 28):
            c.rect(x, 15, 1, 13, "B")
        c.rect(20, 14, 12, 1, "R")
        c.text(21, 18, "400", "W")
        c.outline()
        if hr:
            T = Canvas()
            T.text(5, 4, "HR", "R" if hr % 2 else "r")
            T.rect(5, 10, 7, 1, "W")
            T.outline()
            blit(c, T)
        return c

    frames, durs = [], []
    for i, (x, y) in enumerate(path):
        c = scene()
        for (tx, ty) in path[max(0, i - 3):i]:
            c.px(tx + 2, ty + 2, "I")
        if x < 32:
            blit(c, ball_layer(x, y, BALL5 if i % 2 else BALL5_TURN))
        frames.append(c); durs.append(70)
    for k in range(1, 5):
        c = scene(k)
        S = Canvas()
        for (sx, sy, r) in (((26, 5, 2), (14, 9, 1)) if k % 2 else ((16, 4, 1), (28, 9, 2))):
            sparkle(S, sx, sy, r, "Y", "W")
        S.outline()
        blit(c, S)
        frames.append(c); durs.append(120)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# paint: the pitch catches the low, outside corner of the zone
# ----------------------------------------------------------------------------------------------
@anim("paint")
def paint():
    X0, Y0, X1, Y1 = 8, 4, 23, 24                     # the strike zone
    CX, CY = 21, 21                                   # target: low and away

    def zone(c, lit=None):
        for x in range(X0, X1 + 1):
            c.px(x, Y0, "W"); c.px(x, Y1, "W")
        for y in range(Y0, Y1 + 1):
            c.px(X0, y, "W"); c.px(X1, y, "W")
        for x in (13, 18):
            for y in range(Y0 + 1, Y1, 2):
                c.px(x, y, "L")
        for y in (11, 17):
            for x in range(X0 + 1, X1, 2):
                c.px(x, y, "L")
        if lit:
            c.rect(19, 18, 4, 6, lit)
        c.poly([(12, 27), (19, 27), (19, 29), (15.5, 31), (12, 29)], "W")   # home plate

    frames, durs = [], []
    for k, off in enumerate((7, 5, 3, 1, 0)):         # the target brackets close in
        c = Canvas()
        zone(c)
        c.outline()
        T = Canvas()
        x0, y0, x1, y1 = 19 - off, 18 - off, 22 + off, 23 + off
        for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            T.rect(x, y, 2, 1, "R") if dx > 0 else T.rect(x - 1, y, 2, 1, "R")
            T.rect(x, y if dy > 0 else y - 1, 1, 2, "R")
        T.outline()
        blit(c, T)
        frames.append(c); durs.append(80)
    flight = [((15, 11), BALL3), ((16, 13), BALL3), ((17, 15), BALL3), ((18, 17), BALL5), ((19, 18), BALL5)]
    for (x, y), rows in flight:
        c = Canvas()
        zone(c)
        c.outline()
        blit(c, ball_layer(x, y, rows))
        frames.append(c); durs.append(70)
    for k in range(5):
        c = Canvas()
        zone(c, "R" if k % 2 == 0 else "r")
        c.outline()
        blit(c, ball_layer(19, 19))
        if k < 3:
            S = Canvas()
            sparkle(S, 26, 16 - k, 1, "W")
            sparkle(S, 25, 26 + (k % 2), 1, "W")
            S.outline()
            blit(c, S)
        frames.append(c); durs.append(110 if k else 90)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# foulpole: the ball clangs off the foul pole (a home run), HR flashes
# ----------------------------------------------------------------------------------------------
@anim("foulpole")
def foulpole():
    def scene(shake=0, hr=0):
        c = Canvas()
        turf(c, 29, 31)
        c.rect(19 + shake, 1, 2, 28, "W"); c.rect(20 + shake, 1, 1, 28, "S")      # the pole
        c.rect(18 + shake, 0, 4, 1, "R")
        for y in range(3, 19):                                                    # the screen
            for x in range(21 + shake, 27 + shake):
                c.px(x, y, "I" if (x + y) % 2 else "L")
        c.outline()
        if hr:
            T = Canvas()
            T.text(3, 3, "HR", "R" if hr % 2 else "r")
            T.outline()
            blit(c, T)
        return c

    frames, durs = [], []
    for (x, y) in ((-3, 17), (1, 15), (5, 13), (9, 12), (13, 11)):
        c = scene()
        blit(c, ball_layer(x, y))
        frames.append(c); durs.append(70)
    c = scene(1)                                      # clang
    S = Canvas()
    star(S, 18, 12, 4)
    S.outline()
    blit(c, S)
    blit(c, ball_layer(14, 11))
    frames.append(c); durs.append(110)
    for i, (x, y) in enumerate(((12, 14), (11, 18), (10, 22), (10, 25))):
        c = scene(-1 if i == 0 else 0, hr=1 + i)
        for k, (px_, py_) in enumerate(((22, 9), (23, 13), (22, 16))):
            if i < 2:
                c.px(px_ + i, py_, "W")
        blit(c, ball_layer(x, y))
        frames.append(c); durs.append(80)
    for k in range(4):
        c = scene(hr=k + 1)
        blit(c, ball_layer(10, 25))
        frames.append(c); durs.append(110)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# heater: the radar gun climbs to 101 as a flaming fastball zips past
# ----------------------------------------------------------------------------------------------
@anim("heater")
def heater():
    def gun(c, text, flash=False):
        c.rect(2, 1, 28, 15, "A")
        c.rect(2, 1, 28, 1, "M"); c.rect(2, 15, 28, 1, "M")
        c.rect(2, 1, 1, 15, "M"); c.rect(29, 1, 1, 15, "M")
        w = len(text) * 8 - 2
        led_digits(c, 16 - w // 2, 3, text, "r" if flash else "R", "W" if flash else "r")

    def fastball(c, x, y):
        for k, col in enumerate(("Y", "F", "R", "R")):            # flame trail
            n = 6 - k
            c.rect(x - 2 - k * 3 - n + 1, y + 1 + (k % 2) - 1, n, 3 - (k // 2), col)
        c.stamp(BALL5, x, y)

    readings = ["  ", "  ", "88", "94", "97", "99", "101", "101"]
    frames, durs = [], []
    for i, x in enumerate((-8, -2, 4, 10, 16, 22, 28, 36)):
        c = Canvas()
        gun(c, readings[i])
        if x < 34:
            fastball(c, x, 21)
        frames.append(finish(c)); durs.append(70)
    for k in range(6):
        c = Canvas()
        gun(c, "101", flash=k % 2 == 0)
        for (sx, sy) in ((5, 22), (16, 25), (26, 21)):
            if (k + sx) % 3:
                sparkle(c, sx + (k % 2), sy, 1, "Y", "W")
        frames.append(finish(c)); durs.append(110)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# bunt: the bat squares, the ball taps off it and dribbles up the line
# ----------------------------------------------------------------------------------------------
@anim("bunt")
def bunt():
    bat = bat_sprite(23)

    def scene(give=0):
        c = Canvas()
        clay(c, 28, 31, seed=5, rough=.18)
        c.outline()
        B = Canvas()
        put(B, bat, 4 - give, 12)
        gloves(B, 8 - give, 14)
        B.outline()
        blit(c, B)
        return c

    frames, durs = [], []
    for x in (32, 28, 25):
        c = scene()
        blit(c, ball_layer(x, 12))
        frames.append(c); durs.append(70)
    c = scene(1)                                       # the tap
    blit(c, ball_layer(23, 12))
    for (x, y) in ((22, 10), (28, 10), (22, 18), (28, 18)):
        c.px(x, y, "W")
    frames.append(c); durs.append(110)
    for i, (x, y) in enumerate(((22, 17), (20, 21), (18, 24), (16, 26), (14, 26), (13, 26), (12, 26))):
        c = scene(1 if i < 1 else 0)
        if i in (2, 3):
            D = Canvas()
            for (dx, dy) in ((x + 6, 27), (x + 8, 26), (x + 7, 25)):
                D.px(dx, dy, CLAY_LT)
            blit(c, D)
        blit(c, ball_layer(x, y, BALL5 if i % 2 else BALL5_TURN))
        frames.append(c); durs.append(90 if i < 4 else 120)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# knuckler: a knuckleball floats in, wobbling, seams barely turning
# ----------------------------------------------------------------------------------------------
@anim("knuckler")
def knuckler():
    big = [".WWWWW.", "WRWWWRW", "WWRWRWW", "WWRWRWW", "WWRWRWW", "WRWWWRW", ".WWWWW."]
    big_t = [".WRWRW.", "WWRWRWW", "WWWWWWW", "WWWWWWW", "WWWWWWW", "WWRWRWW", ".WRWRW."]
    frames, durs = [], []
    n = 16
    for f in range(n):
        x = -6 + f * 38 / n
        y = 13 + 5 * math.sin(f * 1.3) * (0.5 + f / n)
        c = Canvas()
        for k in range(1, 4):                                       # wobble trail
            fx = -6 + (f - k) * 38 / n
            fy = 13 + 5 * math.sin((f - k) * 1.3) * (0.5 + (f - k) / n)
            c.px(int(fx) + 3, int(fy) + 3, "I" if k == 1 else "L")
        c.outline()
        blit(c, ball_layer(x, y, big if (f // 3) % 2 == 0 else big_t))
        if f in (6, 7, 12, 13):
            T = Canvas()
            T.text(int(x) + 2, max(0, int(y) - 8), "?", "W")
            T.outline()
            blit(c, T)
        frames.append(c); durs.append(80)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# swing: wind-up, swing, crack, and the ball rockets out
# ----------------------------------------------------------------------------------------------
@anim("swing")
def swing():
    bat = bat_sprite(22)
    HX, HY = 7, 22                                     # the hands

    def scene(deg, ball=None, crack=False, lines=0):
        c = Canvas()
        clay(c, 29, 31, seed=9, rough=.15)
        c.outline()
        B = Canvas()
        rot(B, bat, HX, HY, 0.5, 2.5, deg)
        gloves(B, HX, HY)
        B.outline()
        blit(c, B)
        if crack:
            S = Canvas()
            star(S, 25, 21, 4)
            S.outline()
            blit(c, S)
        if ball:
            blit(c, ball_layer(*ball))
        if lines:
            L = Canvas()
            speed_lines(L, 24, (12, 16, 9), (lines, lines - 2, lines - 3), "W")
            blit(c, L)
        return c

    seq = [dict(deg=-115), dict(deg=-115, ball=(31, 20)), dict(deg=-118, ball=(28, 20)), dict(deg=-80, ball=(26, 20)),
           dict(deg=-35, ball=(25, 20)), dict(deg=0, crack=True), dict(deg=35, ball=(27, 12), lines=7),
           dict(deg=60, ball=(31, 5), lines=6), dict(deg=70), dict(deg=76), dict(deg=-20), dict(deg=-90)]
    durs = [120, 80, 80, 60, 60, 110, 70, 70, 100, 110, 80, 90]
    frames = [scene(**s) for s in seq]
    return frames, durs


# ----------------------------------------------------------------------------------------------
# brokenbat: the pitch jams the hitter and the bat snaps in two
# ----------------------------------------------------------------------------------------------
@anim("brokenbat")
def brokenbat():
    bat = bat_sprite(24)
    handle = Canvas(24, 5); barrel = Canvas(24, 5)
    for y in range(5):
        for x in range(24):
            p = bat.get(x, y)
            if p[3]:
                (handle if x < 12 else barrel).px(x, y, p[:3])
    for y in (1, 2, 3):                                 # jagged break
        handle.px(12, y, WOOD_LT if y != 2 else "O"); barrel.px(11, y, "O" if y != 2 else WOOD_LT)

    def scene(barrel_at=None, chips=(), ball=None, crack=False):
        c = Canvas()
        clay(c, 28, 31, seed=11, rough=.18)
        c.outline()
        B = Canvas()
        put(B, handle, 3, 14)
        gloves(B, 6, 16)
        B.outline()
        blit(c, B)
        if barrel_at:
            L = Canvas()
            x, y, a = barrel_at
            rot(L, barrel, x, y, 18, 2.5, a)
            L.outline()
            blit(c, L)
        if chips:
            C = Canvas()
            for (x, y) in chips:
                C.px(x, y, "O" if (x + y) % 2 else WOOD_LT)
            C.outline()
            blit(c, C)
        if crack:
            S = Canvas()
            star(S, 16, 16, 3)
            S.outline()
            blit(c, S)
        if ball:
            blit(c, ball_layer(*ball))
        return c

    seq = [dict(barrel_at=(21, 16.5, 0), ball=(31, 14)), dict(barrel_at=(21, 16.5, 0), ball=(26, 14)),
           dict(barrel_at=(21, 16.5, 0), ball=(20, 14)), dict(barrel_at=(21, 16.5, 0), crack=True, ball=(17, 14)),
           dict(barrel_at=(23, 12, -25), chips=[(15, 12), (17, 10), (13, 11)], ball=(16, 20)),
           dict(barrel_at=(25, 8, -70), chips=[(14, 8), (18, 6), (11, 9)], ball=(15, 24)),
           dict(barrel_at=(27, 5, -120), chips=[(13, 7), (19, 4), (10, 9)], ball=(14, 25)),
           dict(barrel_at=(29, 4, -170), chips=[(12, 9), (20, 6)], ball=(13, 25)),
           dict(barrel_at=(31, 6, -220), ball=(12, 25)), dict(ball=(12, 25, BALL5_TURN)), dict(ball=(12, 25))]
    durs = [80, 70, 70, 120, 70, 70, 70, 70, 80, 110, 130]
    return [scene(**s) for s in seq], durs


# ----------------------------------------------------------------------------------------------
# brawl: the batting helmets come off, then the fists come up
# ----------------------------------------------------------------------------------------------
HELMET = [
    "...HHHHH...",
    ".HHhhHHHHH.",
    ".HhHHHHHHH.",
    "HHHHHHHHHHH",
    "HHAAHHHHTTT",
    "HHAAHHH....",
    ".HHHH......",
]
FIST = [
    "YY.YY.YY.YY",
    "GGDGGDGGDGG",
    "GGDGGDGGDGG",
    "GGDGGDGGDGG",
    "DDDDDDDDGGG",
    "YYYYYYYDGGG",
    "GGGGGGGDGGD",
    "DDDDDDDGGGD",
    ".GGGGGGGGD.",
    "..GGGGGGD..",
]


@anim("brawl")
def brawl():
    h1 = sprite(HELMET, {"H": "R", "h": "r", "A": "A", "T": "u"})
    h2 = sprite([r[::-1] for r in HELMET], {"H": "B", "h": "b", "A": "A", "T": "n"})

    def fist(L, x, y, sleeve, trim, mirror=False):
        L.rect(x + 2, y + 10, 7, 9, sleeve)
        L.rect(x + 2, y + 10, 7, 1, "K")
        L.rect(x + 2, y + 13, 7, 1, trim)
        L.stamp([r[::-1] for r in FIST] if mirror else FIST, x, y)

    def scene(p1=None, p2=None, fists=None, puff=None):
        c = Canvas()
        c.ellipse(15.5, 27, 14, 2, "c")
        c.rect(6, 27, 3, 1, CLAY_DK); c.rect(21, 28, 3, 1, CLAY_DK)
        c.outline()
        if fists:
            (lx, ly), (rx, ry) = fists
            F = Canvas(); fist(F, lx, ly, "R", "W"); F.outline(); blit(c, F)
            F = Canvas(); fist(F, rx, ry, "B", "W", True); F.outline(); blit(c, F)
        for h, pos in ((h1, p1), (h2, p2)):
            if pos:
                x, y, a = pos
                L = Canvas()
                rot(L, h, x + 5.5, y + 3.5, 5.5, 3.5, a)
                L.outline()
                blit(c, L)
        if puff:
            P = Canvas()
            for x, y in puff:
                P.px(x, y, CLAY_LT)
            P.outline()
            blit(c, P)
        return c

    H1, H2 = (2, 21, 0), (19, 21, 0)
    seq = [
        dict(p1=(3, -3, 25)), dict(p1=(2, 7, -15)), dict(p1=(2, 15, 8)),
        dict(p1=H1, puff=[(1, 26), (14, 26), (0, 24)]),
        dict(p1=H1, p2=(19, -3, -25)), dict(p1=H1, p2=(19, 8, 15)),
        dict(p1=H1, p2=H2, puff=[(17, 27), (31, 26), (30, 24)]),
        dict(p1=H1, p2=H2, fists=((3, 12), (18, 12))),
        dict(p1=H1, p2=H2, fists=((4, 4), (17, 4))),
        dict(p1=H1, p2=H2, fists=((5, 2), (17, 5))),
        dict(p1=H1, p2=H2, fists=((4, 5), (16, 2))),
        dict(p1=H1, p2=H2, fists=((5, 2), (17, 5))),
        dict(p1=H1, p2=H2, fists=((4, 5), (16, 2))),
        dict(p1=H1, p2=H2, fists=((4, 4), (17, 4))),
    ]
    durs = [70, 70, 70, 110, 70, 70, 120, 70, 90, 100, 100, 100, 100, 120]
    return [scene(s.get("p1"), s.get("p2"), s.get("fists"), s.get("puff")) for s in seq], durs


# ----------------------------------------------------------------------------------------------
# cycle: single, double, triple, home run: the runner circles the bases and each one lights up
# ----------------------------------------------------------------------------------------------
@anim("cycle")
def cycle():
    bases = [(15, 26), (26, 15), (15, 4), (4, 15)]                 # home, first, second, third
    labels = ["1B", "2B", "3B", "HR"]

    def field(c, lit, label=None, flash=False):
        c.poly([(15.5, 27), (27, 15.5), (15.5, 4), (4, 15.5)], "c")
        c.poly([(15.5, 24), (24, 15.5), (15.5, 7), (7, 15.5)], TURF)
        for k, (x, y) in enumerate(bases):
            col = "R" if k in lit else "W"
            if k == 0 and 0 in lit and not flash:
                col = "W"
            c.rect(x - 1, y - 1, 3, 3, col)
        c.outline()
        if label:
            T = Canvas()
            x = 10 if label[0] != "1" else 11
            for ch in label:
                g = pix.FONTS["3x5"][ch]
                for j, row in enumerate(g):
                    for i, bit in enumerate(row):
                        if bit == "#":
                            T.rect(x + i * 2, 11 + j * 2, 2, 2, "W" if not flash else "Y")
                x += (len(g[0]) + 1) * 2
            T.outline()
            blit(c, T)

    frames, durs = [], []
    lit = set()
    for leg in range(4):
        (x0, y0), (x1, y1) = bases[leg], bases[(leg + 1) % 4]
        for t in (.33, .66):
            c = Canvas()
            field(c, lit, labels[leg - 1] if leg else None)
            R = Canvas()
            R.rect(int(x0 + (x1 - x0) * t) - 1, int(y0 + (y1 - y0) * t) - 1, 3, 3, "R")
            R.outline()
            blit(c, R)
            frames.append(c); durs.append(70)
        lit.add((leg + 1) % 4)
        c = Canvas()
        field(c, lit, labels[leg])
        frames.append(c); durs.append(110)
    for k in range(4):
        c = Canvas()
        field(c, {0, 1, 2, 3}, "HR", flash=k % 2 == 0)
        S = Canvas()
        for (sx, sy) in (((4, 4), (27, 26)) if k % 2 else ((27, 4), (4, 26))):
            sparkle(S, sx, sy, 1, "Y", "W")
        S.outline()
        blit(c, S)
        frames.append(c); durs.append(120)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# slide: feet first into the bag, dirt flying, SAFE
# ----------------------------------------------------------------------------------------------
@anim("slide")
def slide():
    def runner(L, x):
        """Sliding feet first to the right; x is the toe of the lead cleat."""
        L.rect(x - 11, 22, 9, 2, "W")                               # lead leg
        L.rect(x - 3, 22, 2, 2, "n")                                # sock
        L.rect(x - 1, 21, 2, 3, "K")                                # cleat
        L.rect(x - 9, 24, 5, 2, "W"); L.rect(x - 5, 24, 1, 2, "n")  # trail leg, tucked
        L.poly([(x - 10, 21), (x - 11, 25), (x - 19, 24), (x - 19, 19)], "R")   # jersey, body nearly flat
        L.circle(x - 21, 18, 2, "n")                                # helmet
        L.rect(x - 20, 19, 2, 2, SKIN)
        L.line(x - 16, 20, x - 18, 13, "R", 2)                      # arm up
        L.rect(x - 19, 11, 2, 2, SKIN)

    def scene(x, dust=(), safe=0):
        c = Canvas()
        clay(c, 25, 31, seed=4, rough=.2)
        c.rect(25, 23, 6, 3, "W"); c.rect(25, 25, 6, 1, "I")          # the bag
        c.outline()
        R = Canvas()
        runner(R, x)
        R.outline()
        blit(c, R)
        if dust:
            D = Canvas()
            for (dx, dy) in dust:
                D.px(dx, dy, CLAY_LT if (dx + dy) % 2 else "c")
            D.outline()
            blit(c, D)
        if safe:
            T = Canvas()
            T.text(3, 2, "SAFE", "W" if safe % 2 else "I")
            T.outline()
            blit(c, T)
        return c

    puffs = [[(25, 19), (27, 17), (29, 20)], [(26, 15), (29, 14), (31, 17), (24, 17)],
             [(27, 12), (30, 11), (25, 14), (31, 15)], [(28, 10), (24, 12)], [(28, 9)]]
    frames, durs = [], []
    for x in (4, 11, 18, 23):
        frames.append(scene(x)); durs.append(70)
    for k, d in enumerate(puffs):
        frames.append(scene(26, d, safe=k + 1 if k >= 2 else 0)); durs.append(90)
    for k in range(4):
        frames.append(scene(26, safe=k + 1)); durs.append(120)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# robbed: a glove reaches over the wall and steals the home run
# ----------------------------------------------------------------------------------------------
GLOVE = [
    ".O.O.O.",
    "OOOOOOO",
    "OoOoOoO",
    "OOOOOOO",
    "OOOOOOo",
    ".OOOOo.",
    "..ooo..",
]


@anim("robbed")
def robbed():
    glove = sprite(GLOVE)

    def scene(glove_y=None, ball=None, caught=False, flash=0):
        c = Canvas()
        if glove_y is not None:                                     # behind the wall
            G = Canvas()
            G.rect(21, glove_y + 7, 4, 20, "B")                     # sleeve
            put(G, glove, 19, glove_y)
            if caught:
                G.stamp(BALL3, 21, glove_y + 1)
            G.outline()
            blit(c, G)
        c.rect(0, 17, 32, 15, "n")                                  # the wall
        for x in (6, 14, 22, 30):
            c.rect(x, 17, 1, 15, "B")
        c.rect(0, 16, 32, 1, "R")
        c.outline()
        if ball:
            blit(c, ball_layer(*ball))
        if flash:
            T = Canvas()
            T.text(3, 3, "OUT", "W" if flash % 2 else "R")
            T.outline()
            blit(c, T)
        return c

    seq = [dict(ball=(0, 9)), dict(ball=(5, 5)), dict(ball=(10, 3), glove_y=14), dict(ball=(15, 4), glove_y=10),
           dict(ball=(19, 7), glove_y=7), dict(glove_y=5, caught=True), dict(glove_y=6, caught=True),
           dict(glove_y=10, caught=True, flash=1), dict(glove_y=14, caught=True, flash=2), dict(flash=3), dict(flash=4)]
    durs = [80, 70, 70, 70, 70, 120, 90, 90, 90, 110, 130]
    return [scene(**s) for s in seq], durs


# ----------------------------------------------------------------------------------------------
# punchout: the umpire rings him up, strike three
# ----------------------------------------------------------------------------------------------
@anim("punchout")
def punchout():
    def ump(c, arm):
        c.rect(7, 3, 8, 2, "n"); c.rect(6, 5, 10, 1, "n")              # cap
        c.rect(8, 6, 6, 4, "A")                                       # mask
        c.rect(9, 6, 1, 4, "S"); c.rect(12, 6, 1, 4, "S"); c.rect(8, 8, 6, 1, "S")
        c.rect(6, 10, 10, 9, "n"); c.rect(8, 11, 6, 6, "M")           # shirt, chest protector
        c.rect(7, 19, 8, 5, "S"); c.rect(10, 22, 2, 2, None)          # slacks
        c.rect(6, 24, 4, 3, "K"); c.rect(12, 24, 4, 3, "K")           # shoes
        c.rect(3, 11, 3, 7, "n"); c.rect(3, 18, 3, 2, SKIN)            # left arm, down
        if arm == "down":
            c.rect(16, 11, 3, 7, "n"); c.rect(16, 18, 3, 2, SKIN)
        elif arm == "cock":
            c.rect(16, 10, 3, 3, "n"); c.rect(18, 5, 3, 6, "n"); c.rect(18, 3, 3, 3, SKIN)
        else:
            ext = 2 if arm == "punch" else 0
            c.rect(16, 11, 8 + ext, 3, "n"); c.rect(24 + ext, 10, 4, 4, SKIN)
            c.rect(25 + ext, 10, 1, 4, "D")

    seq = [("down", 0), ("cock", 0), ("reach", 0), ("punch", 1), ("reach", 2), ("punch", 1), ("reach", 2), ("punch", 1),
           ("cock", 0)]
    durs = [140, 110, 60, 110, 90, 110, 90, 130, 90]
    frames = []
    for arm, k in seq:
        c = Canvas()
        ump(c, arm)
        c.outline()
        if k:
            T = Canvas()
            T.text(23, 1, "K", "R")
            T.rect(22, 7, 1, 1, "W"); T.rect(28, 7, 1, 1, "W")
            if arm == "punch":
                speed_lines(T, 22, (9, 11, 13), (3, 4, 3), "W")
            T.outline()
            blit(c, T)
        frames.append(c)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# batflip: the ball is gone, and the bat goes end over end
# ----------------------------------------------------------------------------------------------
@anim("batflip")
def batflip():
    bat = bat_sprite(18)
    arc = [(8, 23, 0), (10, 16, -40), (12, 11, -100), (15, 7, -160), (18, 6, -220), (21, 8, -280), (23, 12, -340),
           (25, 17, -400), (26, 22, -460), (26, 25, -500), (26, 26, -540)]
    frames, durs = [], []
    for i, (x, y, a) in enumerate(arc):
        c = Canvas()
        clay(c, 29, 31, seed=7, rough=.15)
        c.outline()
        L = Canvas()
        rot(L, bat, x, y, 9, 2.5, a)
        L.outline()
        blit(c, L)
        if i < 3:
            blit(c, ball_layer(20 + i * 6, 10 - i * 5))
            S = Canvas()
            speed_lines(S, 18 + i * 6, (12 - i * 5, 14 - i * 5), (4, 3), "W")
            blit(c, S)
        if i >= 8:
            S = Canvas()
            sparkle(S, 6, 8 - (i % 2), 1, "Y", "W"); sparkle(S, 18, 4 + (i % 2), 2, "Y", "W")
            S.outline()
            blit(c, S)
        frames.append(c); durs.append(70 if i < 8 else 120)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# railbang: fists pound the dugout rail
# ----------------------------------------------------------------------------------------------
@anim("railbang")
def railbang():
    def down_fist(w, h):
        f = make_fist(w=w, h=h, wrist=3)
        f.img = f.img.transpose(Image.FLIP_TOP_BOTTOM)              # knuckles down
        return f

    near, far = down_fist(13, 11), down_fist(11, 9)
    seq = [("back", "back", 0, 100), ("hit", "back", 1, 70), ("back", "back", 0, 70), ("back", "hit", 1, 70),
           ("back", "back", 0, 70), ("hit", "back", 1, 70), ("back", "back", 0, 70), ("back", "hit", 1, 70),
           ("back", "back", 0, 70), ("hit", "hit", 2, 80), ("back", "back", 0, 80), ("back", "back", 0, 90)]
    frames, durs = [], []
    for i, (lf, rf, shake, d) in enumerate(seq):
        c = Canvas()
        ry = 19 + (1 if shake else 0)
        c.rect(0, ry + 4, 32, 9, "n"); c.rect(0, ry + 4, 32, 1, "B")   # dugout wall
        c.rect(0, ry, 32, 4, "R"); c.rect(0, ry, 32, 1, "r"); c.rect(0, ry + 3, 32, 1, "u")   # padded rail
        for x in range(3, 32, 8):
            c.rect(x, ry, 1, 4, "u")
        c.outline()
        for side, state in ((0, lf), (1, rf)):
            f = near if state == "hit" else far
            cx = 9 if side == 0 else 22
            fy = ry - f.h if state == "hit" else 4 + (i + side) % 2
            fx = cx - f.w // 2
            A = Canvas()
            A.rect(fx + 3, 0, f.w - 6, max(1, fy), "G" if state == "hit" else "D")
            A.outline()
            blit(c, A)
            F = Canvas()
            put(F, keyline(f), fx - 1, fy - 1)
            blit(c, F)
            if state == "hit":
                T = Canvas()
                for (x, y) in ((fx - 3, ry - 2), (fx - 4, ry - 4), (fx + f.w + 2, ry - 2), (fx + f.w + 3, ry - 4)):
                    T.px(x, y, "W")
                blit(c, T)
        frames.append(c); durs.append(d)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# scoreboard: the home team puts up a run and the bulbs chase
# ----------------------------------------------------------------------------------------------
@anim("scoreboard")
def scoreboard():
    def board(c, home, chase, blink=False):
        c.rect(1, 3, 30, 24, "n")
        c.rect(6, 27, 3, 4, "N"); c.rect(23, 27, 3, 4, "N")              # legs
        bulbs = [(x, 3) for x in range(2, 30, 3)] + [(29, y) for y in range(6, 26, 3)] + \
                [(x, 26) for x in range(29, 1, -3)] + [(2, y) for y in range(24, 4, -3)]
        for k, (x, y) in enumerate(bulbs):
            c.px(x, y, "Y" if (k + chase) % 4 == 0 else "B")
        c.text(4, 8, "AWAY", "W")
        c.text(4, 19, "HOME", "W")
        led_digits(c, 21, 5, "2", "R", "r", None)
        if not blink:
            led_digits(c, 21, 16, home, "R", "r", None)

    frames, durs = [], []
    for k, (home, blink) in enumerate((("2", False), ("2", False), ("2", True), ("-", False), ("2", True), ("3", False),
                                       ("3", True), ("3", False), ("3", True), ("3", False), ("3", False), ("3", False))):
        c = Canvas()
        board(c, home, k, blink)
        frames.append(finish(c)); durs.append(100 if k < 5 else 90)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# squirrel: the rally squirrel dashes across the infield, stops, twitches, dashes off
# ----------------------------------------------------------------------------------------------
SQUIRREL = [
    "..............oo......",
    ".............oOOo.....",
    ".............oOOo.....",
    "........OOOOOOOOOO....",
    "......OOOOOOOOOOOOO...",
    "....OOOOOOOOOOOOOKOO..",
    "...OOOOOOOOOOOOOOOOOO.",
    "..OOOOOOOOOOOOOOOOOOOP",
    "..OOOOOOOOOOOOOOOOOO..",
    "..oOOOOOOOOOOOOOOOC...",
    "..ooOOOOOOOOOOOCCC....",
    "...oooOOOOOOOCCC......",
    "....ooooooooooo.......",
]
BELLY = (236, 214, 178)


def draw_squirrel(c, x, y, legs=0, head=0, tail=0.0, bob=0):
    y += bob
    s = sprite(SQUIRREL, {"C": BELLY})
    body, head_c = Canvas(22, 13), Canvas(22, 13)
    for j in range(13):
        for i in range(22):
            p = s.get(i, j)
            if p[3]:
                (body if i < 12 else head_c).px(i, j, p[:3])
    for t in range(9):                                              # the bushy tail, curling up behind
        a = t / 8
        tx = x + 2 - 4 * math.sin(a * 2.6) - 1.5 * math.sin(tail + t * .5)
        ty = y + 8 - a * 14
        r = 2.2 + 1.2 * math.sin(a * 3.1)
        c.circle(tx, ty, r, "O")
        if t % 2:
            c.px(int(tx) - 1, int(ty) - 1, WOOD_LT)
    put(c, body, x, y)
    put(c, head_c, x, y + head)
    fy = y + 13
    for fx in {0: (5, 12), 1: (3, 13), 2: (6, 10)}[legs]:
        c.rect(x + fx, fy, 2, 1, "o")


@anim("squirrel")
def squirrel():
    GY = 26
    seq = [(-17, 2, 0, 1.2, -1, 0, 70), (-10, 1, 0, 2.4, 0, 0, 70), (-3, 2, 0, 3.6, -1, 0, 70),
           (4, 0, 0, 4.2, 0, 1, 90), (6, 0, 0, 4.4, 0, 2, 90), (6, 0, -1, 4.4, 0, 0, 90), (6, 0, -1, 5.0, 0, 0, 80),
           (6, 0, 0, 5.6, 0, 0, 90), (6, 0, -1, 7.0, 0, 0, 90), (6, 0, 0, 8.4, 0, 0, 90), (7, 1, 0, 9.4, 0, 0, 70),
           (13, 2, 0, 10.6, -1, 0, 70), (20, 1, 0, 11.8, 0, 0, 70), (27, 2, 0, 13.0, -1, 0, 70), (34, 1, 0, 14.2, 0, 0, 70)]
    frames, durs = [], []
    for x, legs, head, tph, bob, puff, d in seq:
        c = Canvas()
        clay(c, GY + 2, GY + 5, seed=2, rough=.25)
        draw_squirrel(c, x, GY - 12, legs, head, tph, bob)
        if puff:
            for (px_, py_) in ((x + 20, GY), (x + 22, GY - 1 - puff), (x + 24, GY)):
                c.rect(px_, py_, 2 if puff == 1 else 1, 2 if puff == 1 else 1, CLAY_LT)
        c.outline()
        frames.append(c); durs.append(d)
    return frames, durs


# ----------------------------------------------------------------------------------------------
# registry / main
# ----------------------------------------------------------------------------------------------
START = {"drag": 3, "homer": 9, "paint": 11, "foulpole": 5, "heater": 9, "bunt": 3, "swing": 5, "brokenbat": 4,
         "brawl": 9, "cycle": 16, "slide": 6, "robbed": 5, "punchout": 3, "batflip": 4, "railbang": 9, "scoreboard": 5,
         "squirrel": 5}


def main(argv):
    want = [a.replace("dbl_", "") for a in argv]
    paths = []
    for name, fn in EMOJI.items():
        if want and name not in want:
            continue
        frames, durs = fn()
        k = START.get(name, 0)
        frames, durs = frames[k:] + frames[:k], list(durs[k:]) + list(durs[:k])
        path = OUT / f"dbl_{name}.gif"
        pix.save_gif(frames, path, durs)
        ds = gif_info(path)
        ok = 8 <= len(ds) <= 24 and all(60 <= d <= 140 for d in ds)
        print(f"{'ok ' if ok else 'BAD'} dbl_{name}.gif  frames={len(ds):2d}  ms={sum(ds):5d}  "
              f"size={path.stat().st_size / 1024:5.1f} KB")
        paths.append(path)
    if not want:
        pix.sheet(paths, HERE / "anim_c_sheet.png")
        print("sheet: anim_c_sheet.png")
    return paths


if __name__ == "__main__":
    main(sys.argv[1:])
