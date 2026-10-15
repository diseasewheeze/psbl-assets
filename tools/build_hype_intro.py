#!/usr/bin/env python3
"""Build the league hype intro: brand/video/b-roll/PSBL_Hype_Intro.mp4.

    python3 tools/build_hype_intro.py                        # render and encode the clip (a few minutes)
    python3 tools/build_hype_intro.py --stills DIR 2 6.5 12  # PNG frames at those times, for checking

The clip is 75.2 s of 8-bit pixel art at 1920 x 1080, 30 fps, H.264 High (yuv420p) with an AAC LC
stereo 48 kHz track: the format the FilmCraft timelines expect. The pictures come from the league's
pixel kit (tools/pixel_kit.py: the palette, Jersey 10 and Silkscreen, the pixel baseball, the
bleachers, the ballpark and the drag tractor) and the video kit's stills (tools/video_kit_media.py).
The chiptune bed uses the voices and the E minor theme of tools/video_kit_audio.py, at 150 BPM.

tools/video_kit_timelines.py cuts the recruiting trailer and two promos out of this clip at fixed
source times, so every scene keeps to its window (quoted names are the trailer's cuts):

   0.0 -  4.0  arcade title screen
   4.0 -  9.4  "Ballpark and crowd": the lights come up, the drag tractor crosses the infield
               ("Empty ballpark" and "Ballpark lights up" use 4.0 - 9.0)
   9.4 -  9.6  pixel wipe (in no cut)
   9.6 - 15.2  "PSBL logo"
  15.2 - 24.0  dynasty: the calendar flips 2027, 2028, 2029
  24.0 - 32.8  "18 active, 15 minors": daily lineups, the slots fill in
  32.8 - 40.0  22 weeks
  40.0 - 46.0  7 pitcher starts
  46.0 - 50.4  "Unlimited trades"
  50.4 - 56.0  "Dynasty Pot coins"
  56.0 - 61.6  "Championship banners"
  61.6 - 67.2  Startup Draft and first pitch
  67.2 - 75.2  "End card: claim your franchise", held to the last frame

Move a scene and the cuts in video_kit_timelines.py have to move with it.
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pixel_kit as px  # noqa: E402
import video_kit_audio as chip  # noqa: E402
import video_kit_media as vkm  # noqa: E402
from pixel_kit import (BLUE, CHALK, CLAY, CLAY_DK, CLAY_LT, MUTED, NAVY, NAVY_DK, NAVY_LO, NAVY_LT, PAPER,  # noqa: E402
                       RED, RED_DK, RED_LT, STANDS, STEEL, STEEL_DK, TURF, TURF_LT, WHITE, art, dither, rect)

ROOT = HERE.parent
OUT = ROOT / "brand" / "video" / "b-roll" / "PSBL_Hype_Intro.mp4"
W, H, FPS = 1920, 1080, 30
SECONDS = 75.2
FRAMES = round(SECONDS * FPS)          # 2256
K = 8                                  # one art pixel = 8 export pixels
AW, AH = W // K, H // K                # the 240 x 135 art grid
SHORT, EST = px.LEAGUE_SHORT, px.LEAGUE_EST
NAME = px.LEAGUE_NAME.upper()
FOOTER = f"{NAME} · EST. {EST}"
DARK_TITLE = (RED, NAVY_DK)            # keylines for white titles: red, then navy (as on the wordmark)
PAPER_TITLE = (PAPER, RED)             # navy titles on paper: off-white, then red


def F(t: float) -> int:
    return round(t * FPS)


# ---------------------------------------------------------------- drawing helpers
def paste(img: Image.Image, piece: Image.Image, x, y) -> None:
    """alpha_composite that clips at the frame edges."""
    x, y = int(x), int(y)
    l, t = max(0, -x), max(0, -y)
    r, b = min(piece.width, img.width - x), min(piece.height, img.height - y)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (0, 0, piece.width, piece.height):
        piece = piece.crop((l, t, r, b))
    img.alpha_composite(piece, (x + l, y + t))


@lru_cache(maxsize=None)
def label(s: str, face: str, scale: int, color, layers=(), shadow=None):
    return px.text_image(s, face, scale, color, layers, shadow)


def text(img, s, face, scale, x, cap_y, color, align="c", layers=(), shadow=None, full=None) -> int:
    """Pixel-font text with its capitals starting at cap_y; x is the left edge, center or right edge.
    With `full`, only s (the start of full) is drawn, at the spot full would take: typing on."""
    layers = tuple(layers)
    t, cap = label(full if full is not None else s, face, scale, color, layers, shadow)
    w = t.width - (scale if shadow else 0)
    reach = len(layers) * scale
    left = {"l": x - reach, "c": x - w // 2, "r": x - w + reach}[align]
    if full is not None:
        if not s:
            return w
        t, cap = label(s, face, scale, color, layers, shadow)
    paste(img, t, left, cap_y - cap)
    return w


def tw(s: str, face: str, scale: int) -> int:
    return px.font(face).width(s, scale)


def up(a: Image.Image) -> Image.Image:
    return a.resize((a.width * K, a.height * K), Image.NEAREST)


@lru_cache(maxsize=64)
def _lut(k: float):
    return [min(255, int(v * k)) for v in range(256)]


def shade(img: Image.Image, k: float) -> Image.Image:
    """Darken in a palette step (lights coming up, unlit trophies)."""
    if k >= 1:
        return img
    r, g, b, a = img.split()
    lut = _lut(round(k, 3))
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


def ease(p: float) -> float:
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 2


def snap(v: float, g: int = 8) -> int:
    return int(round(v / g)) * g


def outline(img, x, y, w, h, t, color):
    rect(img, x, y, w, t, color)
    rect(img, x, y + h - t, w, t, color)
    rect(img, x, y, t, h, color)
    rect(img, x + w - t, y, t, h, color)


def dashed(img, x, y, w, h, t, color, dash=16, gap=8):
    for i in range(0, w, dash + gap):
        rect(img, x + i, y, min(dash, w - i), t, color)
        rect(img, x + i, y + h - t, min(dash, w - i), t, color)
    for j in range(0, h, dash + gap):
        rect(img, x, y + j, t, min(dash, h - j), color)
        rect(img, x + w - t, y + j, t, min(dash, h - j), color)


SPARK = (["..#..", "..#..", "#####", "..#..", "..#.."], [".#.", "###", ".#."], ["#"])


def sparkle(img, cx, cy, size, color=WHITE, k=8):
    rows = SPARK[size]
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "#":
                rect(img, cx + (i - len(row) // 2) * k, cy + (j - len(rows) // 2) * k, k, k, color)


def twinkles(img, f, spots, start=0, colors=(WHITE, RED_LT)):
    """Sparkles that blink on and off around a piece."""
    for n, (x, y) in enumerate(spots):
        phase = (f - start + n * 5) % 24
        if f >= start + n * 2 and phase < 12:
            sparkle(img, x, y, 0 if phase < 4 else 1 if phase < 8 else 2, colors[n % len(colors)])


_ORDER = [((x, y), (x + (8 - y) * .5) / 19) for y in range(9) for x in range(16)]


def wipe(img, p: float, opening: bool = True):
    """The league's pixel wipe: 120 px navy blocks on a diagonal with a red leading edge.
    opening: blocks clear as p goes 0 -> 1; otherwise they cover."""
    d = ImageDraw.Draw(img)
    for (x, y), o in _ORDER:
        on = o >= p if opening else o <= p
        if not on:
            continue
        edge = (o < p + .12) if opening else (o > p - .12)
        X, Y = x * 120, y * 120
        d.rectangle((X, Y, X + 119, Y + 119), fill=(RED if edge else NAVY) + (255,))
        if not edge:
            d.rectangle((X + 52, Y + 52, X + 67, Y + 67), fill=NAVY_LO + (255,))
    return img


def opening(img, f, n=7):
    """A scene's first frames: the pixel wipe clears off it."""
    return wipe(img, (f + 1) / (n + 1)) if f < n else img


@lru_cache(maxsize=None)
def emblem(k: int) -> Image.Image:
    return px.sprite(px.EMBLEM32(), k)


@lru_cache(maxsize=None)
def spr(name, k: int = 1) -> Image.Image:
    return px.sprite(name, k)


@lru_cache(maxsize=None)
def rows_sprite(rows: tuple, pal: tuple, k: int) -> Image.Image:
    pal = dict(pal)
    a = art(len(rows[0]), len(rows))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                a.putpixel((x, y), pal[ch] + (255,))
    return a.resize((a.width * k, a.height * k), Image.NEAREST)


@lru_cache(maxsize=None)
def ground(kind: str) -> Image.Image:
    if kind == "navy":                          # the card ground: navy with a grid of darker dots
        return vkm.bg_dots()
    if kind == "paper":
        return up(px.bg_paper(AW, AH))
    if kind == "red":                           # the same dot grid on red
        a = art(480, 270, RED)
        px.grain(a, [(176, 44, 53), (199, 58, 66)], .02, 31)
        for y in range(2, 270, 6):
            for x in range(2 + (3 if (y // 6) % 2 else 0), 480, 6):
                a.putpixel((x, y), RED_DK + (255,))
        return a.resize((W, H), Image.NEAREST)
    a = px.bg_plain(AW, AH, NAVY_DK)
    if kind == "deep":
        dither(a, 0, 100, AW, 35, NAVY)
    elif kind == "arcade":                      # title screen and end card: a glow off the floor, red rails
        dither(a, 0, 92, AW, 42, NAVY)
        rect(a, 0, 0, AW, 1, RED)
        rect(a, 0, AH - 1, AW, 1, RED)
    return up(a)


# ---------------------------------------------------------------- 0.0 - 4.0 title screen
COIN_AT, START_AT = 78, 102                     # frames: the coin drops in, START is pressed
COIN = (("..KKKK..", ".KWWWWK.", "KWWRRWWK", "KWRWWRTK", "KWRWWRTK", "KWWRRTTK", ".KTTTTK.", "..KKKK.."),
        (("K", STEEL_DK), ("W", WHITE), ("T", CHALK), ("R", RED)))


def coin_frames(k: int) -> list[Image.Image]:
    """A silver league coin spinning: face, narrower, edge, narrower."""
    rows, pal = COIN
    cols = {0: range(8), 1: (0, 1, 3, 4, 6, 7), 2: (0, 2, 5, 7)}
    out = []
    for n in (0, 1, 2, 3, 2, 1):
        if n == 3:
            r = tuple(".K" if y in (0, 7) else "KS" for y in range(8))
            out.append(rows_sprite(r, pal + (("S", STEEL),), k))
        else:
            out.append(rows_sprite(tuple("".join(row[c] for c in cols[n]) for row in rows), pal, k))
    return out


@lru_cache(maxsize=None)
def coins(k: int = 6) -> list[Image.Image]:
    return coin_frames(k)


def title(f):
    if f < 10:                                  # the CRT line opens out
        img = Image.new("RGBA", (W, H), NAVY_DK + (255,))
        w = min(W, int(W * ((f + 1) / 9) ** 1.6)) // 8 * 8
        rect(img, (W - w) // 2, H // 2 - 4, w, 8, WHITE if f >= 7 else RED)
        return img
    img = ground("arcade").copy()
    bob = 10 if (f // 15) % 2 else 0
    paste(img, emblem(10), 800, 176 + bob)
    if COIN_AT - 10 <= f < COIN_AT:             # a coin drops into the slot
        c = coins()[(f // 2) % 6]
        paste(img, c, 96, -48 + (f - COIN_AT + 10) * 10)
    text(img, "CREDIT 01" if f >= COIN_AT else "CREDIT 00", "silk", 4, 64, 48, WHITE, "l")
    if (f // 20) % 2 == 0 or f >= START_AT:
        text(img, "1UP", "silk", 4, W - 64, 48, RED_LT, "r")
    on = (f // 15) % 2 == 0 if f < START_AT else (f // 2) % 2 == 0
    if f < 14 or on:
        text(img, "PRESS START", "silk-bold", 6, 960, 596, WHITE, shadow=NAVY_DK)
    text(img, f"{SHORT} ARCADE", "silk", 4, 960, 688, RED_LT)
    text(img, FOOTER, "silk", 4, 960, 1000, MUTED)
    return img


# ---------------------------------------------------------------- the ballpark (4.0 - 15.2)
CROWD_TOP, CROWD_H = 52, 24
WALL_TOP = CROWD_TOP + CROWD_H                  # 76
FIELD_TOP = WALL_TOP + px.WALL_H                # 82
FIELD_H = AH - 2 - FIELD_TOP                    # 51
BANKS = (14, 206)                               # left edge of each light bank (20 x 10 art pixels)
BOARD = (76, 4, 88, 26)                         # the scoreboard: x, y, w, h
LAMP_ON = (8, 14, 22, 28, 36, 44)               # frames after 4.0 s: bank rows switch on, left then right
BRIGHT = (.24, .36, .46, .58, .7, .84, 1.0)     # how lit the park is with that many rows on
BOARD_ON, TYPE_AT, PRESENTS_AT = 52, 60, 84


@lru_cache(maxsize=None)
def park_static():
    """The ballpark's layers that never move: sky, bleachers and fans, the wall, grass and two kinds
    of infield dirt (raked ahead of the drag tractor, smooth behind it)."""
    sky = px.bg_plain(AW, AH, NAVY_DK)
    dither(sky, 0, 26, AW, CROWD_TOP - 26, NAVY)
    stands = art(AW, AH)
    px.crowd(stands, CROWD_TOP, CROWD_H, 2026)
    rect(stands, 0, CROWD_TOP, AW, 1, NAVY_LT)
    sp = stands.load()
    fans = [(i, CROWD_TOP + j, sp[i, CROWD_TOP + j][:3]) for j in range(2, CROWD_H, 2)
            for i in range((j // 2) % 2, AW, 2)]
    field = art(AW, AH)
    rect(field, 0, WALL_TOP, AW, 1, RED)
    rect(field, 0, WALL_TOP + 1, AW, px.WALL_H - 2, NAVY_LT)
    for x in range(5, AW, 12):
        rect(field, x, WALL_TOP + 1, 1, px.WALL_H - 2, NAVY)
    rect(field, 0, WALL_TOP + px.WALL_H - 1, AW, 1, NAVY_DK)
    grass = round(FIELD_H * .36)
    p = field.load()
    for j in range(grass):
        for i in range(AW):
            p[i, FIELD_TOP + j] = (TURF_LT if ((i + j) // 8) % 2 else TURF) + (255,)
    rect(field, 0, FIELD_TOP + grass, AW, 1, CLAY_DK)
    dy, dh = FIELD_TOP + grass + 1, FIELD_H - grass - 1
    raked, smooth = art(AW, AH), art(AW, AH)
    rect(raked, 0, dy, AW, dh, CLAY)
    rect(smooth, 0, dy, AW, dh, CLAY)
    pr, ps = raked.load(), smooth.load()
    rnd = random.Random(7)
    for j in range(dh):
        for i in range(AW):
            t = rnd.random()
            if t < .12:
                pr[i, dy + j] = CLAY_DK + (255,)
            elif t < .17:
                pr[i, dy + j] = CLAY_LT + (255,)
            if j % 3 == 1:
                ps[i, dy + j] = CLAY_LT + (255,)
    return {"sky": sky, "stands": stands, "fans": fans, "field": field, "raked": raked, "smooth": smooth}


def glow(a, cx, cy, r, strength, color):
    """A dithered halo that thins out from (cx, cy); only over the sky."""
    p = a.load()
    for y in range(max(2, cy - r), min(CROWD_TOP, cy + r + 1)):
        for x in range(max(0, cx - r), min(AW, cx + r + 1)):
            d = math.hypot(x + .5 - cx, y + .5 - cy) / r
            if d < 1 and px.BAYER[y & 3][x & 3] < strength * (1 - d) * 16:
                p[x, y] = color + (255,)


_SY, _SX = np.mgrid[0:CROWD_TOP, 0:AW]
_BAYER = np.array(px.BAYER)[_SY & 3, _SX & 3]


def beams(a: Image.Image, lights) -> Image.Image:
    """Searchlights sweeping the sky: (origin x, angle) pairs, dithered and fading with distance."""
    arr = np.array(a)
    sky = arr[:CROWD_TOP]
    for ox, ang in lights:
        dx, dy = _SX + .5 - ox, CROWD_TOP + 6 - (_SY + .5)
        on = (np.abs(np.arctan2(dx, dy) - ang) < .075) & (_BAYER < 9 * (1 - np.hypot(dx, dy) / 75)) & (_SY >= 2)
        sky[on] = NAVY_LT + (255,)
    return Image.fromarray(arr)


def park(f, lamps=6, show_board=True, board_on=False, tractor=None, wave=None, flashes=0, lights=None, dim=1.0):
    """The ballpark on the art grid at frame f."""
    S = park_static()
    k = BRIGHT[lamps] * dim
    a = shade(S["sky"], k).copy()
    for i, x0 in enumerate(BANKS):              # halos around the lit banks
        lit = sum(1 for n in range(lamps) if n % 2 == i)
        if lit:
            glow(a, x0 + 10, 10, 24, .2 + .12 * lit, BLUE)
            glow(a, x0 + 10, 10, 14, .25 + .2 * lit, NAVY_LT)
    if lights:
        a = beams(a, lights)
    scene = art(AW, AH)
    for x0 in BANKS:                            # the light towers
        rect(scene, x0 + 9, 15, 2, CROWD_TOP - 15, STEEL_DK)
        for y in range(19, CROWD_TOP, 7):
            rect(scene, x0 + 7, y, 6, 1, STEEL_DK)
        rect(scene, x0, 5, 20, 10, STEEL_DK)
        rect(scene, x0 + 1, 6, 18, 8, NAVY_DK)
        for r in range(3):
            for c in range(6):
                rect(scene, x0 + 2 + 3 * c, 6 + 3 * r, 2, 2, NAVY_LT)
    if show_board:
        x, y, w, h = BOARD
        rect(scene, x + 16, y + h, 3, CROWD_TOP - y - h, STEEL_DK)
        rect(scene, x + w - 19, y + h, 3, CROWD_TOP - y - h, STEEL_DK)
        rect(scene, x, y, w, h, NAVY_DK)
        rect(scene, x + 1, y + 1, w - 2, h - 2, RED)
        rect(scene, x + 2, y + 2, w - 4, h - 4, NAVY_DK)
        for i in range(9):                      # inning boxes
            rect(scene, 85 + 8 * i, 21, 5, 4, NAVY_LT)
            rect(scene, 86 + 8 * i, 22, 3, 2, NAVY_DK)
    scene.alpha_composite(S["stands"])
    if wave is not None:                        # the wave: fans stand up as it passes
        p = scene.load()
        for i, y, c in S["fans"]:
            d = abs(i - wave)
            if d <= 6:
                p[i, y] = STANDS + (255,)
                p[i, y - 1] = c + (255,)
                if d <= 3 and (i * 7 + y * 5) % 3 == 0:
                    p[i, y - 2] = WHITE + (255,)
    scene.alpha_composite(S["field"])
    if tractor is None:
        scene.alpha_composite(S["raked"])
    else:
        cut = max(0, min(AW, tractor + 14))
        dirt = S["raked"].copy()
        if cut:
            dirt.paste(S["smooth"].crop((0, 0, cut, AH)), (0, 0))
        scene.alpha_composite(dirt)
        paste(scene, spr("tractor1" if (f // 4) % 2 else "tractor"), tractor, FIELD_TOP + FIELD_H - 29)
    rect(scene, 0, 0, AW, 2, RED)
    rect(scene, 0, AH - 2, AW, 2, RED)
    a.alpha_composite(shade(scene, k))
    p = a.load()
    for n in range(lamps):                      # lit lamps stay at full brightness
        x0, r = BANKS[n % 2], n // 2
        for c in range(6):
            rect(a, x0 + 2 + 3 * c, 6 + 3 * r, 2, 2, WHITE)
            p[x0 + 3 + 3 * c, 7 + 3 * r] = CHALK + (255,)
    if show_board and board_on:                 # chase lights around the scoreboard
        x, y, w, h = BOARD
        ring = [(i, y + 1) for i in range(x + 1, x + w - 1)] + [(x + w - 2, j) for j in range(y + 2, y + h - 1)]
        ring += [(i, y + h - 2) for i in range(x + w - 3, x, -1)] + [(x + 1, j) for j in range(y + h - 3, y + 1, -1)]
        for n, (i, j) in enumerate(ring):
            if n % 2 == 0:
                p[i, j] = (WHITE if ((n // 2) + f // 3) % 2 else RED_LT) + (255,)
    if flashes:                                 # camera flashes in the stands
        rnd = random.Random(f * 7919 + 3)
        for _ in range(flashes):
            i, y, _c = rnd.choice(S["fans"])
            p[i, y] = WHITE + (255,)
            if rnd.random() < .5:
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if 0 <= i + di < AW:
                        p[i + di, y + dj] = CHALK + (255,)
    return a


def board_text(img, f):
    """The scoreboard's display: the short name and a line of zeros, lit after BOARD_ON."""
    if f < BOARD_ON or BOARD_ON + 2 <= f < BOARD_ON + 4:
        return
    text(img, SHORT, "jersey", 7, 960, 64, WHITE, layers=DARK_TITLE)
    for i in range(min(9, max(0, (f - BOARD_ON - 4) // 2 + 1))):
        text(img, "0", "silk-bold", 3, (86 + 8 * i) * K + 12, 22 * K, RED_LT)


PARK_LINE = f"THE {NAME} PRESENTS"


def ballpark(f):
    """4.0 - 9.4: lights come up over a dark park, the board switches on, the line types on."""
    lamps = sum(f >= t for t in LAMP_ON)
    tx = -56 + round(f * (AW + 56) / 161)
    a = park(f, lamps, board_on=f >= BOARD_ON + 4, tractor=tx,
             wave=-8 + (f - 70) * 3.2 if 70 <= f < 150 else None, flashes=3 if f >= LAMP_ON[-1] else 0)
    img = up(a)
    board_text(img, f)
    line = PARK_LINE[:-len(" PRESENTS")]
    if f >= TYPE_AT:
        text(img, line[:2 * (f - TYPE_AT + 1)], "silk-bold", 6, 960, 288, WHITE, shadow=NAVY_DK, full=line)
    if f >= PRESENTS_AT and not (PRESENTS_AT + 4 <= f < PRESENTS_AT + 6 or PRESENTS_AT + 8 <= f < PRESENTS_AT + 10):
        text(img, "PRESENTS", "jersey", 6, 960, 338, RED_LT, shadow=NAVY_DK)
    return img


def to_logo(f):
    """9.4 - 9.6: the pixel wipe closes over the park (no cut uses these frames)."""
    img = ballpark(161)
    return wipe(img, (f + 1) / 6, opening=False)


@lru_cache(maxsize=None)
def lockups():
    return {48: px.lockup(48, 8), 42: px.lockup(42, 7), 36: px.fit_lockup(36, 6, 1640, 640)}


LOGO_SPOTS = [(snap(x), snap(y)) for x, y in ((304, 200), (1640, 176), (232, 560), (1696, 520), (420, 760),
                                               (1520, 768), (704, 104), (1232, 96), (160, 360), (1768, 360))]


def logo(f):
    """9.6 - 15.2: the wordmark slams down over the lit park; searchlights sweep, flashes pop."""
    sweep = 2 * math.pi * f / 96
    a = park(f, 6, show_board=False, tractor=-56 + round(f * (AW + 56) / 167),
             flashes=5, lights=[(64, .5 * math.sin(sweep)), (176, -.5 * math.sin(sweep + .9))], dim=.55)
    img = up(a)
    size = {0: 48, 1: 42}.get(f, 36)
    dx, dy = {2: (12, -8), 3: (-10, 6), 4: (8, -6), 5: (-4, 4)}.get(f, (0, 0))
    lk = lockups()[size]
    paste(img, lk, 960 - lk.width // 2 + dx, 448 - lk.height // 2 + dy)
    if f >= 8:
        twinkles(img, f, LOGO_SPOTS, start=8)
    if f < 3:
        img.alpha_composite(Image.new("RGBA", (W, H), WHITE + (int(255 * (.6, .35, .15)[f]),)))
    return img


# ---------------------------------------------------------------- 15.2 - 24.0 dynasty
CAL_X, CAL_Y, CAL_W = 1208, 208, 512
PAGE_Y, PAGE_H = CAL_Y + 128, 456
FLIPS = (80, 160)                               # 2027 -> 2028 -> 2029
FLIP_LEN = 8


@lru_cache(maxsize=None)
def cal_page(year: int) -> Image.Image:
    pg = Image.new("RGBA", (CAL_W, PAGE_H), PAPER + (255,))
    text(pg, str(year), "jersey", 14, CAL_W // 2, 56, NAVY)
    for r in range(3):
        for c in range(7):
            rect(pg, 64 + c * 56, 264 + r * 48, 40, 32, RED if (r, c) == (1, 4) else CHALK)
    rect(pg, 0, PAGE_H - 8, CAL_W, 8, CHALK)
    return pg


@lru_cache(maxsize=None)
def cal_body() -> Image.Image:
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rect(c, CAL_X + 16, CAL_Y + 16, CAL_W + 16, PAGE_H + 144, NAVY_DK)          # drop shadow
    rect(c, CAL_X - 8, CAL_Y - 8, CAL_W + 16, PAGE_H + 144, NAVY_DK)
    rect(c, CAL_X, CAL_Y, CAL_W, 128, RED)
    rect(c, CAL_X, CAL_Y + 120, CAL_W, 8, RED_DK)
    text(c, "SEASON", "silk-bold", 5, CAL_X + CAL_W // 2, CAL_Y + 56, WHITE)
    for rx in (CAL_X + 104, CAL_X + CAL_W - 128):                               # binder rings
        rect(c, rx, CAL_Y - 40, 24, 72, STEEL)
        rect(c, rx + 16, CAL_Y - 40, 8, 72, STEEL_DK)
        rect(c, rx - 8, CAL_Y + 24, 40, 16, NAVY_DK)
    return c


@lru_cache(maxsize=None)
def roster_card(pos: str) -> Image.Image:
    w, h = 112, 144
    c = Image.new("RGBA", (w, h), NAVY_DK + (255,))
    rect(c, 8, 8, w - 16, h - 16, PAPER)
    rect(c, 8, 8, w - 16, 24, RED)
    paste(c, spr("ball", 4), (w - 56) // 2, 40)
    text(c, pos, "silk-bold", 4, w // 2, 108, NAVY)
    return c


def dynasty(f):
    img = ground("navy").copy()
    slide = max(0, 8 - f) * 80
    text(img, "DYNASTY", "jersey", 14, 180 - slide, 232, WHITE, "l", layers=DARK_TITLE)
    l1, l2 = "ROSTERS CARRY OVER.", "EVERY YEAR."
    if f >= 14:
        text(img, l1[:f - 13], "silk-bold", 6, 180, 470, WHITE, "l", shadow=NAVY_DK, full=l1)
    if f >= 14 + len(l1) + 4:
        text(img, l2[:f - 17 - len(l1)], "silk-bold", 6, 180, 530, RED_LT, "l", shadow=NAVY_DK, full=l2)
    for i, pos in enumerate(("C", "SS", "OF", "SP", "RP")):     # the roster rides along every flip
        hop = 0
        for fl in FLIPS:
            t = f - fl - i * 2
            if 0 <= t < 6:
                hop = (0, 24, 40, 40, 24, 8)[t]
        if f >= 40 + i * 3:
            paste(img, roster_card(pos), 180 + i * 136, 656 - hop)
    img.alpha_composite(cal_body())
    years = [2027, 2028, 2029]
    idx = sum(f >= fl for fl in FLIPS)
    paste(img, cal_page(years[idx]), CAL_X, PAGE_Y)
    for n, fl in enumerate(FLIPS):              # the old page lifts away over the rings
        t = f - fl
        if 0 <= t < FLIP_LEN:
            hv = snap(PAGE_H * (1 - (t + 1) / (FLIP_LEN + 1)))
            old = cal_page(years[n])
            if hv:
                paste(img, old.crop((0, 0, CAL_W, hv)), CAL_X, PAGE_Y)
            rect(img, CAL_X, PAGE_Y + hv, CAL_W, 24, CHALK)
            rect(img, CAL_X, PAGE_Y + hv + 24, CAL_W, 8, STEEL_DK)
    return opening(img, f)


# ---------------------------------------------------------------- 24.0 - 32.8 daily lineups
SLOTS = [["C", "1B", "2B", "3B", "SS"], ["OF", "OF", "OF", "UTIL", "UTIL"], ["SP"] * 5, ["RP"] * 3]
SLOT_W, SLOT_H, SLOT_GAP = 160, 80, 24
FILL0, FILL_STEP = 18, 6
CAPTION = (("18", "ACTIVE"), ("8", "RESERVE"), ("15", "MINORS"), ("4", "IL"))


def slot_positions():
    out = []
    for r, row in enumerate(SLOTS):
        w = len(row) * SLOT_W + (len(row) - 1) * SLOT_GAP
        for c, pos in enumerate(row):
            out.append((pos, (W - w) // 2 + c * (SLOT_W + SLOT_GAP), 384 + r * (SLOT_H + SLOT_GAP)))
    return out


def counters(f):
    """ACTIVE follows the slots; RESERVE, MINORS and IL tick up after them."""
    active = sum(1 for i in range(18) if f >= FILL0 + FILL_STEP * i)
    t0 = FILL0 + FILL_STEP * 17 + 8
    vals, t = [active], t0
    for target in (8, 15, 4):
        vals.append(min(target, max(0, (f - t) // 2 + 1)) if f >= t else 0)
        t += target * 2
    return vals


def caption(img, values, cap_y, scale, word_color, num_color):
    face = "silk-bold"
    sp = tw("A A", face, scale) - 2 * tw("A", face, scale)
    pieces = []
    for i, (num, word) in enumerate(CAPTION):
        pieces += [("n", num, values[i]), ("w", word, None)]
        if i < len(CAPTION) - 1:
            pieces.append(("w", "·", None))
    widths = [tw(p[1], face, scale) for p in pieces]
    x = 960 - (sum(widths) + sp * (len(pieces) - 1)) // 2
    for (kind, s, v), w in zip(pieces, widths):
        if kind == "n":
            text(img, str(v), face, scale, x + w, cap_y, num_color, "r")
        else:
            text(img, s, face, scale, x, cap_y, word_color, "l")
        x += w + sp


def lineups(f):
    img = ground("paper").copy()
    text(img, "DAILY LINEUPS", "jersey", 10, 960, 104, NAVY, layers=PAPER_TITLE)
    text(img, "HEAD-TO-HEAD POINTS. SET IT EVERY DAY.", "silk-bold", 5, 960, 276, NAVY)
    locked = 196 <= f < 200 or 204 <= f < 208
    for i, (pos, x, y) in enumerate(slot_positions()):
        t = f - (FILL0 + FILL_STEP * i)
        if t < 0:
            dashed(img, x, y, SLOT_W, SLOT_H, 8, STEEL)
            text(img, pos, "silk-bold", 4, x + SLOT_W // 2, y + 30, STEEL)
            continue
        dy = (-32, -16)[t] if t < 2 else 0
        flash = t == 0 or locked
        rect(img, x, y + dy, SLOT_W, SLOT_H, WHITE if flash else NAVY)
        if flash:
            outline(img, x, y + dy, SLOT_W, SLOT_H, 8, NAVY)
        rect(img, x, y + dy + SLOT_H - 8, SLOT_W, 8, RED)
        text(img, pos, "silk-bold", 4, x + SLOT_W // 2, y + dy + 28, NAVY if flash else WHITE)
    if f >= 10:
        caption(img, counters(f), 856, 5, NAVY, RED)
    return opening(img, f)


# ---------------------------------------------------------------- 32.8 - 40.0 22 weeks
BOX, BOX_GAP = 104, 24
WEEK0, WEEK_STEP = 22, 5


def weeks(f):
    img = ground("red").copy()
    text(img, "22 WEEKS", "jersey", 16, 960, 120, WHITE, layers=DARK_TITLE)
    text(img, "EVERYONE PLAYS EVERYONE. TWICE.", "silk-bold", 6, 960, 384, WHITE, shadow=RED_DK)
    x0 = (W - (11 * BOX + 10 * BOX_GAP)) // 2
    done = sum(1 for i in range(22) if f >= WEEK0 + WEEK_STEP * i)
    chase = (f - 140) // 2 % 22 if f >= 140 else -1
    for i in range(22):
        x, y = x0 + (i % 11) * (BOX + BOX_GAP), 512 + (i // 11) * (BOX + BOX_GAP)
        t = f - (WEEK0 + WEEK_STEP * i)
        if t < 0:
            rect(img, x, y, BOX, BOX, RED_DK)
            outline(img, x, y, BOX, BOX, 8, RED_LT)
            continue
        g = 8 if t == 0 else 0
        fill = RED_LT if i == chase else WHITE
        rect(img, x - g, y - g, BOX + 2 * g, BOX + 2 * g, fill)
        rect(img, x - g, y + BOX + g - 8, BOX + 2 * g, 8, CHALK if fill == WHITE else RED)
        text(img, str(i + 1), "silk-bold", 5, x + BOX // 2, y + 38, NAVY)
    text(img, f"WEEK {done:02d}", "silk-bold", 6, 960, 830, WHITE, shadow=RED_DK)
    return opening(img, f)


# ---------------------------------------------------------------- 40.0 - 46.0 7 pitcher starts
CHIP, CHIP_GAP = 144, 32
START0, START_STEP = 18, 9
EIGHTH, EIGHTH_TRY, EIGHTH_X = 90, 104, 110


def chip_box(img, x, y, size, edge, fill):
    """A square chip with stepped corners."""
    rect(img, x + 8, y, size - 16, size, edge)
    rect(img, x, y + 8, size, size - 16, edge)
    rect(img, x + 8, y + 8, size - 16, size - 16, fill)


def starts(f):
    img = ground("deep").copy()
    text(img, "7 PITCHER STARTS", "jersey", 12, 960, 184, WHITE, layers=DARK_TITLE)
    text(img, "A WEEK. MAX.", "silk-bold", 6, 960, 400, WHITE if EIGHTH_X <= f < EIGHTH_X + 3 else RED_LT,
         shadow=NAVY_DK)
    x0, y0 = (W - (8 * CHIP + 7 * CHIP_GAP)) // 2, 528
    ball = spr("ball", 6)
    for i in range(8):
        x = x0 + i * (CHIP + CHIP_GAP)
        if i < 7:
            t = f - (START0 + START_STEP * i)
            if t < 0:
                dashed(img, x, y0, CHIP, CHIP, 8, NAVY_LT)
            else:
                g = 8 if t < 2 else 0
                chip_box(img, x - g, y0 - g, CHIP + 2 * g, WHITE if t < 2 else RED, NAVY)
                paste(img, ball, x + (CHIP - ball.width) // 2, y0 + (CHIP - ball.height) // 2)
            text(img, str(i + 1), "silk-bold", 4, x + CHIP // 2, y0 + CHIP + 32, MUTED)
            continue
        if f < EIGHTH:                          # the eighth start: tries to get in, gets crossed out
            continue
        shake = (8, -8, 6, -4)[f - EIGHTH_X] if EIGHTH_X <= f < EIGHTH_X + 4 else 0
        x += shake
        if f < EIGHTH_TRY or (f < EIGHTH_X and f % 2):
            if f >= EIGHTH_TRY or (f // 4) % 2 == 0:
                dashed(img, x, y0, CHIP, CHIP, 8, RED_LT)
        else:
            chip_box(img, x, y0, CHIP, RED if f < EIGHTH_X else RED_DK, NAVY if f < EIGHTH_X else NAVY_DK)
            b = ball if f < EIGHTH_X else shade(ball, .45)
            paste(img, b, x + (CHIP - b.width) // 2, y0 + (CHIP - b.height) // 2)
        if f >= EIGHTH_X:                       # the red X, block by block
            n = min(11, (f - EIGHTH_X) * 2 + 2)
            for s in range(n):
                for (bx, by) in ((x - 16 + s * 16, y0 - 16 + s * 16), (x + CHIP - s * 16, y0 - 16 + s * 16)):
                    rect(img, bx, by, 16, 16, RED)
        text(img, "8", "silk-bold", 4, x + CHIP // 2, y0 + CHIP + 32, RED_LT if f >= EIGHTH_X else MUTED)
    return opening(img, f)


# ---------------------------------------------------------------- 46.0 - 50.4 unlimited trades
CARD_W, CARD_H = 352, 432
CARD_L, CARD_R, CARD_Y = 424, 1144, 424
SWAPS = (22, 76)
SWAP_LEN = 18
ARROW = ("....#...", "....##..", "#######.", "########", "#######.", "....##..", "....#...")


@lru_cache(maxsize=None)
def franchise_card(name: str, body, edge, bar) -> Image.Image:
    w, h = CARD_W, CARD_H
    c = Image.new("RGBA", (w, h), NAVY_DK + (255,))
    rect(c, 8, 8, w - 16, h - 16, edge)
    rect(c, 16, 16, w - 32, h - 32, body)
    text(c, "FRANCHISE", "silk-bold", 3, w // 2, 48, WHITE)
    paste(c, spr("ball", 8), (w - 112) // 2, 88)
    text(c, name, "silk-bold", 5, w // 2, 240, WHITE)
    rect(c, 48, 296, w - 96, 8, edge)
    for j, bw in enumerate((208, 160, 184)):                     # roster lines
        rect(c, 64, 328 + j * 24, bw, 8, bar)
        rect(c, w - 96, 328 + j * 24, 32, 8, bar)
    return c


def trades(f):
    img = ground("paper").copy()
    text(img, "UNLIMITED TRADES", "jersey", 12, 960, 96, NAVY, layers=PAPER_TITLE)
    text(img, "NO VETOES.", "silk-bold", 6, 960, 296, RED)
    a = franchise_card("TEAM 03", NAVY, RED, NAVY_LT)
    b = franchise_card("TEAM 09", RED, NAVY, RED_DK)
    pos = {"a": CARD_L, "b": CARD_R}
    moving = None
    for n, s in enumerate(SWAPS):
        t = f - s
        if t >= SWAP_LEN:
            pos = {"a": pos["b"], "b": pos["a"]}
        elif t >= 0:
            moving = (t / SWAP_LEN, dict(pos))
            break
    lit = (f // 8) % 2 == 0
    for dy, flip, color in ((560, False, RED if lit else STEEL), (696, True, NAVY if not lit else STEEL)):
        rows = tuple(r[::-1] for r in ARROW) if flip else ARROW
        paste(img, rows_sprite(rows, (("#", color),), 12), 912, dy)
    if moving is None:
        paste(img, a, pos["a"], CARD_Y)
        paste(img, b, pos["b"], CARD_Y)
    else:
        p, start = moving
        e = 3 * p * p - 2 * p * p * p
        drawn = []
        for key, card in (("a", a), ("b", b)):
            x0 = start[key]
            x1 = CARD_R if x0 == CARD_L else CARD_L
            over = x0 == CARD_L                  # the card heading right rides over the top
            y = CARD_Y - 72 * math.sin(math.pi * p) if over else CARD_Y + 40 * math.sin(math.pi * p)
            drawn.append((over, card, snap(x0 + (x1 - x0) * e), snap(y)))
        for over, card, x, y in sorted(drawn, key=lambda d: d[0]):
            paste(img, card, x, y)
    return opening(img, f)


# ---------------------------------------------------------------- 50.4 - 56.0 the Dynasty Pot
TROPHY_AT = (20, 34, 48)
TROPHY_X, TROPHY_Y = (600, 960, 1320), 280
POT_LINE_AT = 58
POT_FRAMES = F(56.0) - F(50.4)


@lru_cache(maxsize=None)
def trophies():
    lit = vkm.trophy(10)
    white = Image.new("RGBA", lit.size, WHITE + (255,))
    flash = Image.new("RGBA", lit.size, (0, 0, 0, 0))
    flash.paste(white, (0, 0), lit)
    return lit, shade(lit, .3), flash


COIN_V = 36                                     # px per frame


@lru_cache(maxsize=None)
def coin_rain():
    """Coins fall straight down and heap up into a mound along the bottom. Each coin's spot in the heap
    is settled when it drops (it rolls off any column standing two higher than a neighbor), so it
    falls in its own column and lands on top of the coins dropped before it."""
    rnd = random.Random(50)
    cols, colw = 38, 48
    x0 = (W - cols * colw) // 2
    height = [0] * cols
    out = []
    for f in range(8, 151):
        for _ in range(2 if f % 2 else 1):
            col = min(cols - 1, max(0, int(rnd.gauss(cols / 2, cols / 4.5))))
            while True:
                lower = [n for n in (col - 1, col + 1) if 0 <= n < cols and height[n] < height[col] - 1]
                if not lower:
                    break
                col = min(lower, key=lambda n: (height[n], rnd.random()))
            y = H - 32 - 48 - 18 * height[col]
            height[col] += 1
            land = f + math.ceil((y + 48) / COIN_V)
            out.append({"spawn": f, "x": x0 + col * colw + (12 if height[col] % 2 else 0), "y": y,
                        "land": land, "phase": rnd.randrange(6)})
    return out


def pot(f):
    img = ground("deep").copy()
    frames = coins()
    rain = coin_rain()
    for c in rain:
        if c["spawn"] <= f < c["land"]:
            paste(img, frames[(c["phase"] + f // 2) % 6], c["x"], min(c["y"], -48 + COIN_V * (f - c["spawn"])))
    for c in sorted((c for c in rain if c["land"] <= f), key=lambda c: (c["land"], -c["y"])):
        paste(img, frames[0 if c["phase"] % 3 else 1], c["x"], c["y"])
    text(img, "THE DYNASTY POT", "jersey", 12, 960, 96, WHITE, layers=DARK_TITLE)
    lit, dim, flash = trophies()
    for x, t0 in zip(TROPHY_X, TROPHY_AT):
        t = f - t0
        paste(img, dim if t < 0 else flash if t < 2 else lit, x - lit.width // 2, TROPHY_Y)
    spots = [(snap(x + dx), snap(TROPHY_Y + dy)) for x in TROPHY_X for dx, dy in ((-104, 24), (96, 8), (88, 128))]
    twinkles(img, f, spots, start=TROPHY_AT[-1] + 4)
    rect(img, 544, 480, 832, 168, NAVY_DK)                       # the plaque the words sit on
    outline(img, 544, 480, 832, 168, 8, RED)
    text(img, "FIRST TO 3 TITLES", "silk-bold", 6, 960, 520, WHITE)
    if f >= POT_LINE_AT and not (POT_LINE_AT + 4 <= f < POT_LINE_AT + 6):
        text(img, "TAKES THE WHOLE POT", "silk-bold", 5, 960, 588, RED_LT)
    return opening(img, f)


# ---------------------------------------------------------------- 56.0 - 61.6 championship banners
PEN_W, PEN_H, PEN_TOP = 384, 592, 96
UNFURL = (6, 18, 30)
UNFURL_LEN = 14
BANNER_LINE_AT = 52


@lru_cache(maxsize=None)
def pennant(style: int, coin_lit: bool = True) -> Image.Image:
    """A hanging championship banner (48 x 74 art, swallowtail) with its lettering."""
    body, trim, ink, accent = ((PAPER, RED, NAVY, RED), (RED, WHITE, WHITE, WHITE), (NAVY, BLUE, WHITE, RED_LT))[style]
    w, h, tail = PEN_W // K, PEN_H // K, 12
    a = art(w, h)
    for y in range(h):
        n = y - (h - tail)
        cut = n * 1.6 if n >= 0 else -1.0
        for x in range(2, w - 2):
            d = abs(x + .5 - w / 2)
            if d < cut:
                continue
            edge = x < 4 or x >= w - 4 or y < 2 or y >= h - 2 or (n >= 0 and d < cut + 2)
            a.putpixel((x, y), (trim if edge else body) + (255,))
    img = up(a)
    lines = {0: (("PRESIDENTS'", "TROPHY"), "YOUR NAME", "2027"),
             1: ((f"{SHORT} CHAMPIONS",), "YOUR NAME", "2027"),
             2: ((f"{SHORT} CHAMPIONS",), "INSERT COIN", "2028")}[style]
    heads, name, year = lines
    if len(heads) == 1:                         # split "PSBL CHAMPIONS" over two lines
        heads = tuple(heads[0].split(" ", 1))
    for j, s in enumerate(heads):
        text(img, s, "silk-bold", 4, PEN_W // 2, 64 + j * 40, ink)
    if style != 2 or coin_lit:
        text(img, name, "silk-bold", 4, PEN_W // 2, 176, accent)
    rect(img, 96, 224, PEN_W - 192, 8, accent if style != 1 else WHITE)
    text(img, year, "jersey", 8, PEN_W // 2, 264, ink)
    if style != 2:
        cup = vkm.trophy(4)
        paste(img, cup, (PEN_W - cup.width) // 2, 376)
    return img


@lru_cache(maxsize=None)
def banners_bg() -> Image.Image:
    a = px.bg_plain(AW, AH, NAVY)
    px.crowd(a, 108, 26, 56)
    dither(a, 0, 104, AW, 10, NAVY, down=False)
    rect(a, 0, AH - 1, AW, 1, RED)
    img = up(a)
    rect(img, 248, 72, W - 496, 16, STEEL)       # the rail the banners hang from
    rect(img, 248, 88, W - 496, 8, STEEL_DK)
    for x in (248, W - 264):
        rect(img, x, 40, 16, 56, STEEL_DK)
    return img


def banners(f):
    img = banners_bg().copy()
    x0 = (W - (3 * PEN_W + 2 * 72)) // 2
    for i, t0 in enumerate(UNFURL):
        t = f - t0
        if t < 0:
            continue
        x = x0 + i * (PEN_W + 72)
        pen = pennant(i, (f // 15) % 2 == 0)
        hv = PEN_H if t >= UNFURL_LEN else snap(PEN_H * ease((t + 1) / UNFURL_LEN))
        if hv:
            paste(img, pen.crop((0, 0, PEN_W, hv)), x, PEN_TOP)
        if t < UNFURL_LEN:                      # the rolled-up part, dropping
            rect(img, x + 8, PEN_TOP + hv - 8, PEN_W - 16, 24, STEEL)
            rect(img, x + 8, PEN_TOP + hv + 16, PEN_W - 16, 8, STEEL_DK)
        for hx in (x + 64, x + PEN_W - 80):     # hooks on the rail
            rect(img, hx, 88, 16, 16, STEEL_DK)
    if f >= BANNER_LINE_AT:
        a, b = "YOUR BANNER.", "FOREVER."
        sp = tw("A A", "silk-bold", 6) - 2 * tw("A", "silk-bold", 6)
        wa, wb = tw(a, "silk-bold", 6), tw(b, "silk-bold", 6)
        x = 960 - (wa + sp + wb) // 2
        text(img, a, "silk-bold", 6, x, 768, WHITE, "l", shadow=NAVY_DK)
        if f >= BANNER_LINE_AT + 10:
            text(img, b, "silk-bold", 6, x + wa + sp, 768, RED_LT, "l", shadow=NAVY_DK)
    return opening(img, f)


# ---------------------------------------------------------------- 61.6 - 67.2 the dates
TICKET_W, TICKET_H, TICKET_X = 1360, 288, 280
TICKETS = (("STARTUP DRAFT", "JANUARY 2027", 264, 4), ("FIRST PITCH", "MARCH 2027", 600, 22))
SLIDE_LEN, PITCH_AT = 12, 64


@lru_cache(maxsize=None)
def ticket(event: str, date: str) -> Image.Image:
    w, h = TICKET_W, TICKET_H
    t = Image.new("RGBA", (w, h), NAVY_DK + (255,))
    rect(t, 8, 8, w - 16, h - 16, PAPER)
    rect(t, 8, 8, 40, h - 16, NAVY)
    stub = w - 304
    for y in range(24, h - 24, 24):
        rect(t, stub, y, 8, 12, STEEL)
    text(t, event, "jersey", 9, 96, 56, NAVY, "l")
    text(t, date, "silk-bold", 6, 96, 192, RED, "l")
    text(t, "ADMIT", "silk-bold", 4, stub + 152, 64, NAVY)
    text(t, "ONE", "silk-bold", 4, stub + 152, 100, NAVY)
    paste(t, spr("ball", 6), stub + 110, 152)
    return t


def dates(f):
    img = ground("red").copy()
    text(img, "SAVE THE DATES", "silk-bold", 6, 960, 136, WHITE, shadow=RED_DK)
    for event, date, y, t0 in TICKETS:
        t = f - t0
        if t < 0:
            continue
        side = -1 if t0 == TICKETS[0][3] else 1
        x = TICKET_X + side * snap((W - TICKET_X + 80) * (1 - ease((t + 1) / SLIDE_LEN)))
        paste(img, rect_shadow(), x + 16, y + 16)
        paste(img, ticket(event, date), x, y)
    t = f - PITCH_AT                            # the first pitch zips across
    if 0 <= t < 14:
        bx = -64 + t * 160
        for n, (tail, color) in enumerate(((48, WHITE), (96, CHALK), (160, RED_LT))):
            rect(img, bx - tail, 952 + 24, tail - n * 8, 8, color)
        paste(img, spr("ball", 4), bx, 952)
    return opening(img, f)


@lru_cache(maxsize=None)
def rect_shadow() -> Image.Image:
    return Image.new("RGBA", (TICKET_W, TICKET_H), RED_DK + (255,))


# ---------------------------------------------------------------- 67.2 - 75.2 end card
END_LAND, END_TYPE, END_START = 12, 24, 60
END_SPOTS = [(snap(x), snap(y)) for x, y in ((704, 176), (1216, 160), (624, 424), (1296, 440), (800, 104), (1112, 488))]


def end_card(f):
    img = ground("arcade").copy()
    if f < END_LAND:
        y = -320 + (152 + 320) * (f / END_LAND) ** 2
    elif f < END_LAND + 6:
        y = 152 - 48 * math.sin(math.pi * (f - END_LAND) / 6)
    elif f < END_LAND + 10:
        y = 152 - 16 * math.sin(math.pi * (f - END_LAND - 6) / 4)
    else:
        y = 152
    paste(img, emblem(10), 800, snap(y, 10))
    if END_LAND <= f < END_LAND + 6:            # dust off the landing
        for side in (-1, 1):
            sparkle(img, 960 + side * (200 + (f - END_LAND) * 16), 456, min(2, (f - END_LAND) // 2), CHALK)
    if f >= END_LAND + 18:
        twinkles(img, f, END_SPOTS, start=END_LAND + 18)
    title_s = "CLAIM YOUR FRANCHISE"
    scale = next(s for s in (12, 11, 10, 9, 8) if tw(title_s, "jersey", s) + 4 * s <= W - 240)
    if f >= END_TYPE:
        text(img, title_s[:f - END_TYPE + 1], "jersey", scale, 960, 568, WHITE, layers=DARK_TITLE, full=title_s)
    if f >= END_START and (f // 15) % 2 == 0:
        text(img, "PRESS START", "silk-bold", 5, 960, 800, RED_LT, shadow=NAVY_DK)
    if f >= 6:
        text(img, FOOTER, "silk", 4, 960, 1000, MUTED)
    return img


# ---------------------------------------------------------------- the running order
SCENES = [
    (0.0, 4.0, "Title screen", title),
    (4.0, 9.4, "Ballpark and crowd", ballpark),
    (9.4, 9.6, "Wipe", to_logo),
    (9.6, 15.2, "PSBL logo", logo),
    (15.2, 24.0, "Dynasty", dynasty),
    (24.0, 32.8, "Daily lineups (18 active, 15 minors)", lineups),
    (32.8, 40.0, "22 weeks", weeks),
    (40.0, 46.0, "7 pitcher starts", starts),
    (46.0, 50.4, "Unlimited trades", trades),
    (50.4, 56.0, "Dynasty Pot coins", pot),
    (56.0, 61.6, "Championship banners", banners),
    (61.6, 67.2, "Startup Draft and first pitch", dates),
    (67.2, 75.2, "End card: claim your franchise", end_card),
]


def frame(i: int) -> Image.Image:
    for start, end, _name, paint in SCENES:
        if F(start) <= i < F(end):
            img = paint(i - F(start))
            if img.size != (W, H):
                raise ValueError(f"frame {i} is {img.size}")
            return img
    raise IndexError(i)


# ---------------------------------------------------------------- the chiptune bed
BPM = 150
BEAT = 60 / BPM                                 # 0.4 s
BAR = 4 * BEAT                                  # 1.6 s: the logo lands on bar 6, the end card on bar 42
CHORDS = ("Em", "C", "D", "G")


def swish(dur=.22):
    x = chip.noise(dur, 1.0, 1e9, hp=True)
    return x * np.sin(np.pi * np.arange(len(x)) / len(x)) * .5


def soundtrack() -> np.ndarray:
    """A 150 BPM 8-bit bed in E minor (the league theme over a 4-bar Em C D G loop), with a riser
    into the logo, a hit on the end card and small effects on the action. Mixed low."""
    m = chip.Mix(SECONDS)
    e8, e16 = BEAT / 2, BEAT / 4

    def pl(track, t, nm, dur, duty=.5, vol=1.0, **kw):
        m.add(track, t, chip.pulse(chip.freq(nm), dur, duty, 1.0, **kw), vol)

    def at(scene_start, frame_):
        return scene_start + frame_ / FPS

    # 0.0 - 3.2: the title screen's attract arpeggio
    for k in range(round(3.2 / e16)):
        t = k * e16
        pl("p2", t, chip.ARP[CHORDS[int(t // BAR)]][k % 4], e16 * .9, .125, .45, s=.5)
    for k in range(round(3.2 / e8)):
        m.add("drums", k * e8, chip.hat(), .3)
    tc = at(0, COIN_AT)
    pl("sfx", tc, "B5", .07, .5, .7)
    pl("sfx", tc + .07, "E6", .45, .5, .7, d=.35, s=.25, r=.1)
    for i, nm in enumerate(("E5", "G5", "B5", "E6", "G6", "B6")):
        pl("sfx", at(0, START_AT) + i * .045, nm, .05, .25, .55)

    # 4.0 - 9.6: lights clunk on, the crowd swells, bass and drums come in, a riser into the logo
    for fr_ in LAMP_ON:
        t = at(4.0, fr_)
        m.add("sfx", t, chip.impact(.5))
        m.add("bass", t, chip.tri(55, .25, 1.0, r=.1), .5)
    crowd = chip.noise(5.0, 1.0, 1e9, lp=6)
    ramp = np.minimum(1, np.arange(len(crowd)) / (1.6 * chip.SR)) * np.minimum(1, (len(crowd) - np.arange(len(crowd))) / (.6 * chip.SR))
    m.add("sfx", 4.6, crowd * ramp, .18)
    for i in range(4):
        pl("sfx", at(4.0, BOARD_ON + 4) + i * .066, ("E6", "B5", "E6", "G6")[i], .05, .25, .35)
    for k in range(round(2.4 / e8)):            # 5.6 - 8.0 bass on E
        m.add("bass", 5.6 + k * e8, chip.tri(chip.freq(f"E{(2, 3)[k % 2]}"), e8 * .95, 1.0, r=.01), .85)
    for b in range(4):
        m.add("drums", 6.4 + b * BEAT, chip.kick(), .8)
        m.add("drums", 6.4 + b * BEAT + e8, chip.hat(), .5)
    m.add("sfx", 8.0, chip.riser(BAR, 200, 1800), .9)
    for k in range(8):
        m.add("drums", 8.8 + k * e16 * 2, chip.snare(), .3 + .07 * k)
    for k in range(8):
        m.add("bass", 8.0 + k * e8, chip.tri(chip.freq("B1" if k < 4 else "B2"), e8 * .95, 1.0, r=.01), .85)

    # 9.6: the logo lands
    m.add("drums", 9.6, chip.crash(), .9)
    m.add("drums", 9.6, chip.kick(), 1.0)
    m.add("sfx", 9.6, chip.impact(1.0))

    # 9.6 - 67.2: nine passes of the 4-bar loop
    for i in range(36):
        t0, ch, loop = 9.6 + i * BAR, CHORDS[i % 4], i // 4
        root = chip.ROOT[ch]
        for b in ((0, 1.5, 2, 3.5) if loop in (2, 3, 6, 7) else (0, 2)):
            m.add("drums", t0 + b * BEAT, chip.kick(), .9)
        last = i == 35
        for b in (1, 3):
            if not (last and b == 3):
                m.add("drums", t0 + b * BEAT, chip.snare(), .7)
        step = .25 if loop in (6, 7) else .5
        for k in range(int(4 / step)):
            m.add("drums", t0 + k * step * BEAT, chip.hat(), .5)
        for k, o in enumerate((2, 3, 2, 3, 2, 3, 2, 2)):
            m.add("bass", t0 + k * e8, chip.tri(chip.freq(f"{root}{o}"), e8 * .95, 1.0, r=.01), .9)
        if loop not in (3, 7):
            for k in range(16):
                pl("p2", t0 + k * e16, chip.ARP[ch][k % 4], e16 * .9, .125, .35, s=.5)
        if loop >= 1:
            b = 0
            for nm, ln in chip.THEME_A[ch]:
                pl("p1", t0 + b * e8, nm, ln * e8 * (.92 if ln >= 3 else .85), .5, .8, vib=.006 if ln >= 3 else 0.0)
                b += ln
        if loop in (3, 4, 7):
            for k, nm in enumerate(chip.THEME_B[ch]):
                pl("p3", t0 + k * e8, nm, e8 * .8, .25, .6)
    for k in range(8):                          # fill into the end card
        m.add("drums", 66.4 + k * e16 * 2, chip.snare(), .3 + .07 * k)

    # 67.2 - 75.2: the end card hit, then the theme's last chord rings out
    m.add("drums", 67.2, chip.crash(2.4), 1.0)
    m.add("drums", 67.2, chip.kick(), 1.0)
    m.add("sfx", at(67.2, END_LAND), chip.impact(1.0))
    m.add("drums", at(67.2, END_LAND), chip.kick(), .8)
    m.add("bass", 67.2, chip.tri(chip.freq("E2"), 4 * BAR, 1.0, r=2.0), .9)
    for k in range(round(2 * BAR / e8)):
        pl("p2", 67.2 + k * e8, chip.ARP["Em"][k % 4], e8 * .9, .125, .4, s=.5)
    for k in range(round(2 * BAR / BEAT)):
        pl("p2", 67.2 + 2 * BAR + k * BEAT, chip.ARP[("C", "D")[k // 4] if k < 8 else "Em"][k % 4], BEAT * .9, .125, .35, s=.5)
    for b, (nm, ln) in enumerate((("E5", 2), ("B5", 2), ("E6", 4))):
        pl("p1", 67.2 + (0, 2, 4)[b] * e8, nm, ln * e8 * .9, .5, .7)
    for nm in ("E4", "G4", "B4"):
        pl("p3", 67.2 + 4 * BAR, nm, BAR * 1.5, .25, .5, d=.6, s=.3, r=.8)
    pl("p1", 67.2 + 4 * BAR, "E5", BAR * 1.5, .5, .5, d=.6, s=.3, r=.8)
    for k in range(4):
        m.add("drums", 67.2 + 2 * BAR + k * BAR / 2, chip.hat(open_=True), .35)
    for k in range(len("CLAIM YOUR FRANCHISE")):
        pl("sfx", at(67.2, END_TYPE + k), "B6", .015, .125, .12)

    # the action
    for fl in FLIPS:
        m.add("sfx", at(15.2, fl), swish(.2), .7)
    for i in range(18):
        pl("sfx", at(24.0, FILL0 + FILL_STEP * i), ("E6", "B5")[i % 2], .04, .25, .3)
    t0 = FILL0 + FILL_STEP * 17 + 8
    for n in range(27):
        pl("sfx", at(24.0, t0 + 2 * n), "A6", .02, .125, .12)
    for i in range(22):
        pl("sfx", at(32.8, WEEK0 + WEEK_STEP * i), "G5", .03, .25, .25)
    for i, nm in enumerate(("E5", "F#5", "G5", "A5", "B5", "C6", "D6")):
        pl("sfx", at(40.0, START0 + START_STEP * i), nm, .06, .25, .45)
    pl("sfx", at(40.0, EIGHTH_TRY), "E6", .06, .25, .45)
    m.add("sfx", at(40.0, EIGHTH_X), chip.pulse(98, .35, .5, 1.0, slide=-.5), .6)
    m.add("sfx", at(40.0, EIGHTH_X), chip.noise(.2, 1.0, .08, lp=3), .4)
    for s in SWAPS:
        m.add("sfx", at(46.0, s), swish(.5), .8)
    for t0 in TROPHY_AT:
        pl("sfx", at(50.4, t0), "E6", .08, .5, .5)
        pl("sfx", at(50.4, t0) + .08, "B6", .3, .5, .5, d=.25, s=.2)
    last = -99
    for c in sorted((c for c in coin_rain() if c["land"] is not None), key=lambda c: c["land"]):
        if c["land"] - last >= 6:
            pl("sfx", at(50.4, c["land"]), "B6", .03, .5, .18)
            pl("sfx", at(50.4, c["land"]) + .03, "E7", .1, .5, .18, d=.08, s=.2)
            last = c["land"]
    for t0 in UNFURL:
        m.add("sfx", at(56.0, t0), swish(.35), .7)
    for _e, _d, _y, t0 in TICKETS:
        m.add("sfx", at(61.6, t0), swish(.3), .7)
    m.add("sfx", at(61.6, PITCH_AT), chip.pulse(1400, .25, .125, 1.0, slide=-1.5), .35)
    m.add("sfx", at(61.6, PITCH_AT), swish(.25), .5)

    x = m.stereo(chip.GAINS, chip.PANS)
    return chip.master(x, -18.0, ceiling_db=-2.0, fade_out=1.5)


# ---------------------------------------------------------------- encoding
def encode(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_movie = out.with_name(out.stem + ".part.mp4")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "bed.wav"
        chip.write_wav(wav, soundtrack())
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-",
               "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
               "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-tune", "animation",
               "-profile:v", "high", "-level:v", "5.0", "-pix_fmt", "yuv420p", "-r", str(FPS),
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-t", f"{SECONDS}", "-movflags", "+faststart", str(tmp_movie)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for i in range(FRAMES):
                proc.stdin.write(frame(i).convert("RGB").tobytes())
                if i % 300 == 0:
                    print(f"frame {i}/{FRAMES}", flush=True)
            proc.stdin.close()
        except BaseException:
            proc.kill()
            raise
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
    tmp_movie.replace(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--stills", type=Path, metavar="DIR", help="write PNG frames at the given times instead")
    ap.add_argument("times", nargs="*", type=float)
    a = ap.parse_args()
    if a.stills:
        a.stills.mkdir(parents=True, exist_ok=True)
        for t in a.times:
            path = a.stills / f"hype-{t:05.2f}.png"
            frame(min(FRAMES - 1, F(t))).convert("RGB").save(path)
            print(path)
        return
    encode(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
