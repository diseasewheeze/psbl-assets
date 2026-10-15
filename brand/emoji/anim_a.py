#!/usr/bin/env python3
"""PSBL animated emoji, group anim_a (11 GIFs): reactions and props. File names keep the psbl_ prefix.

    python3 anim_a.py            # writes animated/psbl_<name>.gif for all 11 + anim_a_sheet.png
    python3 anim_a.py goal fire  # just those (no sheet)

Everything is drawn on the 32 x 32 pix.Canvas and exported x4. Deterministic (seeded RNGs only).
Layering rule: a base scene gets one outline(); anything that must read *on top of* other art
(a ball over a glove, tears over a face) is drawn on its own layer, outlined once, then blitted, so
every shape keeps exactly one 1-px keyline.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pix  # noqa: E402
from pix import Canvas  # noqa: E402
from PIL import Image  # noqa: E402

OUT = HERE / "animated"


# =============================================================================================
# helpers
# =============================================================================================
def blit(dst: Canvas, src: Canvas, x: int = 0, y: int = 0):
    data = src.img.load()
    for j in range(src.h):
        for i in range(src.w):
            p = data[i, j]
            if p[3]:
                dst.px(x + i, y + j, p[:3])


def layer(fn) -> Canvas:
    """Draw with fn on a fresh 32 x 32 layer and give it its own keyline."""
    L = Canvas()
    fn(L)
    L.outline()
    return L


def sprite(rows, pal=None) -> Canvas:
    c = Canvas(max(len(r) for r in rows), len(rows))
    c.stamp(rows, 0, 0, pal)
    return c


def rot(dst: Canvas, src: Canvas, ax, ay, sx, sy, deg):
    """Nearest-neighbor rotate src (clockwise on screen for deg > 0) so that the source point
    (sx, sy) lands on the destination point (ax, ay)."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    data = src.img.load()
    R = int(math.hypot(src.w, src.h)) + 2
    for y in range(int(ay) - R, int(ay) + R + 1):
        if not 0 <= y < dst.h:
            continue
        for x in range(int(ax) - R, int(ax) + R + 1):
            if not 0 <= x < dst.w:
                continue
            dx, dy = x + .5 - ax, y + .5 - ay
            u = dx * ca + dy * sa + sx
            v = -dx * sa + dy * ca + sy
            iu, iv = math.floor(u), math.floor(v)
            if 0 <= iu < src.w and 0 <= iv < src.h:
                p = data[iu, iv]
                if p[3]:
                    dst.px(x, y, p[:3])


def rotp(px_, py_, ox, oy, deg):
    """Rotate point about (ox, oy), clockwise on screen for deg > 0."""
    a = math.radians(deg)
    dx, dy = px_ - ox, py_ - oy
    return ox + dx * math.cos(a) - dy * math.sin(a), oy + dx * math.sin(a) + dy * math.cos(a)


def mesh(c: Canvas, x0, y0, x1, y1, fill="A", line="S", step=4, warp=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            u = x if warp is None else warp(x, y)
            c.px(x, y, line if ((u + y) % step == 0 or (u - y) % step == 0) else fill)


def sparkle(c: Canvas, x, y, r=1, colr="W", core=None):
    c.px(x, y, core or colr)
    for i in range(1, r + 1):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.px(x + dx * i, y + dy * i, colr)


def star(c: Canvas, x, y, r, inner="W", outer="Y", diag=True):
    """Impact burst: a plus with longer straight rays and shorter diagonals."""
    c.rect(x - 1, y - 1, 3, 3, inner)
    for i in range(2, r + 1):
        col_ = inner if i <= r // 2 else outer
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.px(x + dx * i, y + dy * i, col_)
    if diag:
        for i in range(2, max(2, r - 1)):
            for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                c.px(x + dx * i, y + dy * i, outer)


def drop(c: Canvas, x, y, size=1):
    """Teardrop (point up) in light blue with a white glint; fills only (outline adds the keyline).
    size 0: 2 x 3, size 1: 3 x 4, size 2: 5 x 7. (x, y) = top-left."""
    if size == 0:
        c.px(x, y, "L"); c.px(x + 1, y, "L")
        c.px(x, y + 1, "W"); c.px(x + 1, y + 1, "L")
        c.px(x, y + 2, "L"); c.px(x + 1, y + 2, "L")
        return
    if size == 1:
        c.stamp([".L.", "LLL", "WLL", "LLB"], x, y)
        return
    c.stamp(["..L..", ".LLL.", ".LLL.", "LLLLL", "LWLLL", "LWLLB", ".LLB."], x, y)


def speed_lines(c: Canvas, x_end, ys, lengths, colr="W"):
    """Horizontal dashes ending at x_end (trailing to the left)."""
    for y, n in zip(ys, lengths):
        c.rect(x_end - n + 1, y, n, 1, colr)


def finish(c: Canvas, *layers: Canvas) -> Canvas:
    c.outline()
    for L in layers:
        blit(c, L)
    return c


# =============================================================================================
# cheers: two pint glasses swing in and clink, foam splashes up
# =============================================================================================
def pint():
    g = Canvas(10, 17)
    for r in range(17):
        hw = 5 - (1 if r >= 12 else 0)
        x0, x1 = 5 - hw, 5 + hw - 1
        if r == 0:
            g.rect(x0 + 1, r, x1 - x0 - 1, 1, "W")
        elif r <= 2:
            g.rect(x0, r, x1 - x0 + 1, 1, "W")
            if r == 2:
                g.px(x0 + 2, r, "C"); g.px(x1 - 2, r, "C")
        elif r <= 14:
            g.rect(x0, r, x1 - x0 + 1, 1, "G")
            g.px(x0, r, "I"); g.px(x1, r, "I")
            g.px(x0 + 1, r, "Y")
            g.px(x1 - 1, r, "D")
        else:
            g.rect(x0, r, x1 - x0 + 1, 1, "I")
    g.px(4, 6, "Y"); g.px(6, 9, "Y"); g.px(3, 11, "Y")   # bubbles
    return g


def cheers():
    g = pint()
    gr = pint().flip()
    seq = [  # left glass bottom-center x, y, angle
        (6, 31, -6), (8, 30, 8), (9, 29, 18), (10, 28, 24), (9, 28, 20), (8, 29, 15),
        (7, 29, 10), (6, 30, 5), (5, 30, 0), (5, 31, -4), (5, 31, -6),
    ]
    rng = random.Random(5)
    drops = [[16 + rng.uniform(-1, 1), 10, vx, rng.uniform(-3.4, -2.4)] for vx in (-2.2, -1.2, -0.4, 0.5, 1.3, 2.3)]
    frames, durs = [], []
    for i, (x, y, a) in enumerate(seq):
        c = Canvas()
        for spr, bx, ang in ((g, x, a), (gr, 31 - x, -a)):
            L = Canvas()
            rot(L, spr, bx, y, 5, 17, ang)
            L.outline()
            blit(c, L)
        top = Canvas()
        if i == 3:
            star(top, 16, 11, 4, "W", "Y")
        if i == 4:
            for x_, y_ in ((12, 7), (20, 7), (16, 5)):
                top.px(x_, y_, "Y")
        if i >= 3:
            for d in drops:
                if i > 3:
                    d[0] += d[2]; d[1] += d[3]; d[3] += 0.8
                if d[1] < 30:
                    top.rect(int(round(d[0])), int(round(d[1])), 2, 2, "W")
        if i == 3:
            top.rect(14, 8, 4, 3, "W")
        top.outline()
        blit(c, top)
        frames.append(c)
        durs.append([90, 70, 60, 120, 80, 80, 80, 80, 90, 100, 110][i])
    return frames, durs


# =============================================================================================
# confetti: party popper bursts, confetti flutters down
# =============================================================================================
def confetti():
    BX, BY = 4.0, 28.0
    ux, uy = math.cos(math.radians(-58)), math.sin(math.radians(-58))
    vx_, vy_ = -uy, ux

    def popper(c, recoil=0):
        bx, by = BX - recoil * ux, BY - recoil * uy
        for y in range(32):
            for x in range(32):
                dx, dy = x + .5 - bx, y + .5 - by
                t = dx * ux + dy * uy
                s = dx * vx_ + dy * vy_
                if 0 <= t <= 13 and abs(s) <= 0.7 + t * 0.36:
                    c.px(x, y, "C" if t > 12 else ("R" if int(t // 3) % 2 else "G"))
        c.line(int(bx) - 1, int(by), int(bx) - 3, int(by) + 2, "W")

    rng = random.Random(21)
    cols = "RYLEPVBGW"
    bits = []
    mx, my = BX + 13 * ux, BY + 13 * uy
    for k in range(30):
        a = math.radians(-62 + rng.uniform(-48, 40))
        sp = rng.uniform(3.5, 8.5)
        bits.append(dict(x=mx, y=my, vx=math.cos(a) * sp, vy=math.sin(a) * sp, ph=rng.uniform(0, 6.28),
                         colr=cols[k % len(cols)]))
    streamers = [(-40, "P"), (-75, "L")]

    frames, durs = [], []
    N = 18
    for i in range(N):
        c = Canvas()
        popper(c, 1 if i == 2 else 0)
        if i == 1:
            c.px(int(BX) - 4, int(BY) + 3, "W")
        c.outline()
        T = Canvas()
        if i == 2:
            star(T, int(mx) + 2, int(my) - 2, 4)
        if i >= 2:
            for b in bits:
                if i > 2:
                    b["x"] += b["vx"]; b["y"] += b["vy"]
                    b["vx"] *= 0.7; b["vy"] = b["vy"] * 0.7 + 0.36
                    if b["vy"] > 0:
                        b["x"] += 0.9 * math.sin(b["ph"] + i * 1.2)
                if b["y"] < 31:
                    flip_ = (i + int(b["ph"] * 3)) % 3
                    x, y = int(round(b["x"])), int(round(b["y"]))
                    if flip_ == 0:
                        T.rect(x, y, 2, 1, b["colr"])
                    elif flip_ == 1:
                        T.rect(x, y, 1, 2, b["colr"])
                    else:
                        T.px(x, y, b["colr"])
            if 3 <= i <= 12:
                for a0, colr in streamers:
                    n = min(i - 2, 5) * 2
                    for k in range(n):
                        a = math.radians(a0)
                        x = mx + math.cos(a) * k * 1.4 + math.sin(k * 1.3 + i) * 0.9
                        y = my + math.sin(a) * k * 1.4 + max(0, i - 6) * 0.5 * k / 6
                        T.px(int(round(x)), int(round(y)), colr)
        T.outline()
        blit(c, T)
        frames.append(c)
        durs.append(110 if i < 2 else (70 if i < 6 else 90))
    return frames, durs


# =============================================================================================
# jackpot: slot machine spins, lands on three baseballs, coins pop out
# =============================================================================================
SYM = {
    "O": ([".....", ".###.", "r###r", "#r#r#", "r###r", ".###.", "....."], "W"),   # a baseball
    "7": (["#####", "...##", "..##.", "..##.", ".##..", ".##..", ".##.."], "R"),
    "C": (["...#.", "..#.#", ".#..#", "#...#", "rr.rr", "rr.rr", "....."], "E"),
    "*": ([".....", "..#..", ".###.", "#####", ".###.", ".#.#.", "....."], "G"),
}
STRIP = ["7", "C", "O", "*"]


def jackpot():
    WX = [6, 12, 18]           # reel windows (5 wide) top y 11..19

    def symbol(c, s, x, y, clip):
        rows, colr = SYM[s]
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                yy = y + j
                if ch != "." and clip[0] <= yy <= clip[1]:
                    c.px(x + i, yy, colr if ch == "#" else "R")

    def machine(c, reels, lever, lights, flash):
        c.rect(3, 7, 23, 22, "R"); c.rect(4, 7, 1, 22, "r")          # cabinet
        c.rect(5, 3, 19, 4, "G"); c.rect(5, 3, 19, 1, "Y")           # marquee
        c.px(5, 3, None); c.px(23, 3, None)
        for k, x in enumerate(range(7, 23, 3)):
            c.px(x, 5, "W" if (k + lights) % 2 else "D")
        c.rect(5, 10, 19, 11, "K")
        for k, x in enumerate(WX):
            c.rect(x, 11, 5, 9, "Y" if flash else "W")
            r = reels[k]
            if isinstance(r, str):
                symbol(c, r, x, 12, (11, 19))
            else:   # spinning: scrolled strip
                off = r % 36
                for n, s in enumerate(STRIP * 2):
                    symbol(c, s, x, 12 + n * 9 - off - 9, (11, 19))
                c.px(x, 11 + (r % 9), "S"); c.px(x + 4, 11 + ((r + 4) % 9), "S")
        c.rect(5, 22, 19, 1, "G")
        c.rect(8, 24, 13, 3, "A"); c.rect(8, 24, 13, 1, "G"); c.rect(9, 25, 11, 1, "K")   # coin tray
        c.rect(26, 15, 2, 5, "N")                                      # lever
        top = {0: 4, 1: 10, 2: 16}[lever]
        c.rect(28, top, 1, 18 - top if top < 16 else 3, "S")
        c.circle(28, top, 1, "R"); c.px(28, top - 1, "r")

    coins = []
    rng = random.Random(8)
    for k in range(8):
        coins.append(dict(born=11 + k, x=13.0, y=22.0, vx=(-1 if k % 2 else 1) * (3.2 + (k % 3) * 0.5),
                          vy=-3.0 + (k % 3) * 0.5))
    seq = [
        (["7", "C", "*"], 0, 0, False), (["7", "C", "*"], 1, 1, False), ([5, 11, 17], 2, 0, False),
        ([12, 20, 26], 1, 1, False), ([19, 29, 35], 0, 0, False), ([26, 2, 8], 0, 1, False),
        (["O", 11, 17], 0, 0, False), (["O", 20, 26], 0, 1, False), (["O", "O", 35], 0, 0, False),
        (["O", "O", 8], 0, 1, False), (["O", "O", "O"], 0, 0, True), (["O", "O", "O"], 0, 1, False),
        (["O", "O", "O"], 0, 0, True), (["O", "O", "O"], 0, 1, False), (["O", "O", "O"], 0, 0, True),
        (["O", "O", "O"], 0, 1, False), (["O", "O", "O"], 0, 0, True), (["O", "O", "O"], 0, 1, False),
    ]
    durs = [120, 80, 60, 60, 60, 60, 80, 60, 80, 60, 110, 90, 90, 90, 90, 90, 100, 110]
    frames = []
    for i, (reels, lever, lights, flash) in enumerate(seq):
        c = Canvas()
        machine(c, reels, lever, lights, flash)
        c.outline()
        T = Canvas()
        for cn in coins:
            if i < cn["born"]:
                continue
            if i > cn["born"]:
                cn["x"] += cn["vx"]; cn["y"] += cn["vy"]; cn["vy"] += 0.7
            if cn["y"] < 31:
                x, y = int(round(cn["x"])), int(round(cn["y"]))
                T.stamp([".GG.", "GYGD", "GGGD", ".DD."], x, y)
        T.outline()
        blit(c, T)
        frames.append(c)
    return frames, durs


# =============================================================================================
# breaking: tiny TV with a scrolling BREAKING banner and a pulsing red light
# =============================================================================================
def breaking():
    msg = "BREAKING"
    tw = Canvas(64, 5)
    w = tw.text(0, 0, msg, "W") - 1
    period = 36
    pulse = ["R", "r", "W", "r", "R", "A"]
    frames, durs = [], []
    for f in range(18):
        c = Canvas()
        c.line(13, 5, 8, 0, "S"); c.line(18, 5, 23, 0, "S")             # rabbit ears
        c.rect(1, 5, 30, 22, "M"); c.rect(1, 5, 30, 1, "N")              # cabinet
        c.px(1, 5, None); c.px(30, 5, None); c.px(1, 26, None); c.px(30, 26, None)
        c.rect(5, 27, 3, 2, "A"); c.rect(24, 27, 3, 2, "A")             # feet
        c.rect(3, 7, 22, 18, "B")                                        # screen
        c.rect(3, 7, 22, 1, "b")
        c.rect(10, 9, 12, 1, "L"); c.rect(10, 11, 8, 1, "L")             # headline graphic
        c.rect(3, 14, 22, 7, "R"); c.rect(3, 14, 22, 1, "r")             # banner
        c.rect(3, 21, 22, 2, "G")
        for k in range(0, 22, 4):
            xk = 3 + (k + f) % 22
            c.px(xk, 22, "D")
        off = (f * 2) % period
        for rep in (0, 1):
            x0 = 25 - off + rep * period - period // 2
            for j in range(5):
                for i in range(w):
                    if tw.img.getpixel((i, j))[3] and 3 <= x0 + i <= 24:
                        c.px(x0 + i, 15 + j, "W")
        # pulsing red light, top-left of screen
        p = pulse[f % 6]
        c.rect(5, 9, 3, 3, p if p != "W" else "r")
        if p == "W":
            c.px(6, 10, "W")
            for x, y in ((4, 10), (8, 10), (6, 8), (6, 12)):
                c.px(x, y, "r")
        c.rect(27, 9, 2, 2, "S"); c.rect(27, 13, 2, 2, "S")              # knobs
        for y in (18, 20, 22):
            c.rect(26, y, 4, 1, "A")
        frames.append(finish(c)); durs.append(90)
    return frames, durs


# =============================================================================================
# hourglass: sand drains top to bottom, then the glass flips over
# =============================================================================================
def hourglass():
    TOP = [3, 5, 6, 6, 6, 5, 5, 4, 3, 2, 1, 1]          # half widths for y 5..16 (top bulb)
    BOT = TOP[::-1]                                     # y 17..28
    Y_TOP, Y_BOT = 5, 17
    rows_top = {Y_TOP + i: w for i, w in enumerate(TOP)}
    rows_bot = {Y_BOT + i: w for i, w in enumerate(BOT)}
    CAP = 46

    def draw(p, f):
        c = Canvas()
        c.rect(8, 2, 16, 2, "O"); c.rect(8, 3, 16, 1, "o")             # caps
        c.rect(8, 29, 16, 2, "O"); c.rect(8, 30, 16, 1, "o")
        c.rect(9, 4, 1, 25, "o"); c.rect(22, 4, 1, 25, "o")             # posts
        for rows in (rows_top, rows_bot):
            for y, w in rows.items():
                c.rect(16 - w, y, 2 * w, 1, "I")
                c.px(16 + w - 1, y, "L")
        # sand left on top: fill rows from the neck upwards; the last row fills from the edges (funnel)
        left = round(CAP * p)
        for y in sorted(rows_top, reverse=True):
            w = rows_top[y]
            if left <= 0:
                break
            n = min(left, 2 * w)
            if n == 2 * w:
                c.rect(16 - w, y, 2 * w, 1, "G")
            else:
                h = n // 2
                c.rect(16 - w, y, h, 1, "G"); c.rect(16 + w - h, y, h, 1, "G")
            left -= n
        # sand below: fill rows from the bottom up; the last row fills from the center (mound)
        fallen = CAP - round(CAP * p)
        for y in sorted(rows_bot, reverse=True):
            w = rows_bot[y]
            if fallen <= 0:
                break
            n = min(fallen, 2 * w)
            h = (n + 1) // 2
            c.rect(16 - h, y, 2 * h, 1, "G")
            fallen -= n
            top_y = y
        # stream
        if 0 < p < 1:
            ty = top_y if CAP - round(CAP * p) > 0 else 28
            for y in range(16, ty):
                c.px(15, y, "Y" if (y + f) % 3 else "G")
        for y in (6, 7, 8):
            c.px(12 if y > 6 else 13, y, "W")
        for y in (20, 21):
            c.px(11, y + 3, "W")
        return c

    frames, durs = [], []
    ps = [1, .9, .8, .7, .6, .5, .4, .3, .2, .1, 0]
    for f, p in enumerate(ps):
        c = draw(p, f)
        frames.append(finish(c)); durs.append(100 if p > 0 else 140)
    base = draw(0, 0)
    for a in (45, 90, 135):
        c = Canvas()
        rot(c, base, 15.5, 16, 15.5, 16, a)
        frames.append(finish(c)); durs.append(70)
    return frames, durs


# =============================================================================================
# fire: a flame that flickers, grows and throws sparks
# =============================================================================================
def fire():
    N = 16
    rng = random.Random(12)
    sparks = [dict(born=rng.randrange(N), x=rng.uniform(9, 22), drift=rng.uniform(-0.8, 0.8)) for _ in range(9)]
    frames, durs = [], []
    for f in range(N):
        ph = 2 * math.pi * f / N
        grow = 0.5 - 0.5 * math.cos(ph)
        H = 18 + 8 * grow
        W = 8 + 2.2 * grow
        base, cx = 29.5, 15.5
        c = Canvas()
        for y in range(32):
            t = (base - (y + .5)) / H
            if t < -0.14 or t > 1:
                continue
            env = W * (1 - max(t, 0)) ** 1.25 * min(1.0, math.sqrt(max(0.0, (t + 0.14) / 0.34)))
            env += 0.9 * max(t, 0) * math.sin(y * 1.3 + ph * 3)
            sway = 2.4 * max(t, 0) ** 1.5 * math.sin(ph * 2 + t * 3.5)
            for x in range(32):
                d = abs(x + .5 - (cx + sway)) / max(env, 0.01)
                di = abs(x + .5 - (cx + sway * 0.6)) / max(env, 0.01)
                if d > 1:
                    continue
                colr = "R"
                if di <= 0.7 and t < 0.78:
                    colr = "F"
                if di <= 0.46 and t < 0.56:
                    colr = "G"
                if di <= 0.24 and t < 0.34:
                    colr = "Y"
                c.px(x, y, colr)
        # side tongues: two smaller flames leaning out from the base
        for side, phase, hk in ((-1, 0.0, 0.5), (1, 2.3, 0.42)):
            h2 = H * (hk + 0.08 * math.sin(ph * 2 + phase))
            w2 = W * 0.42
            ccx = cx + side * W * 0.62
            for y in range(32):
                t = (base - 1 - (y + .5)) / h2
                if t < 0 or t > 1:
                    continue
                env = w2 * (1 - t) ** 1.1 * min(1.0, math.sqrt((t + 0.1) / 0.35))
                lean = side * 2.2 * t ** 1.4 + 0.8 * t * math.sin(ph * 3 + phase)
                for x in range(32):
                    if abs(x + .5 - (ccx + lean)) <= env and not c.get(x, y)[3]:
                        c.px(x, y, "R" if t > 0.45 or abs(x + .5 - (ccx + lean)) > env * 0.5 else "F")
        # detached tip
        tipy = int(base - H - 2 - (f % 4) * 2)
        if f % 4 != 3 and tipy > 0:
            c.rect(int(cx + 2.4 * math.sin(ph * 2 + 3.5)), tipy, 2, 2, "R")
        c.outline()
        S = Canvas()
        for s in sparks:
            age = (f - s["born"]) % N
            if age < 5:
                x = int(round(s["x"] + s["drift"] * age + math.sin(age * 1.7)))
                y = int(round(base - H * 0.7 - age * 3))
                if 0 <= y:
                    S.px(x, y, "Y" if age < 3 else "F")
        S.outline()
        blit(c, S)
        frames.append(c); durs.append(70)
    return frames, durs


# =============================================================================================
# rally: the rally meter (a battery) charges bar by bar, then a lightning bolt crackles
# =============================================================================================
def rally():
    BARS = [24, 20, 16, 12, 8]
    BOLTS = [
        [(19, 0), (8, 17), (15, 17), (11, 31), (25, 12), (17, 12), (23, 0)],
        [(18, 1), (9, 15), (15, 15), (12, 30), (24, 13), (17, 13), (22, 1)],
    ]

    def battery(c, n, flash=False):
        c.rect(13, 2, 6, 2, "S")
        c.rect(7, 4, 18, 26, "S"); c.rect(23, 4, 2, 26, "N"); c.rect(7, 4, 18, 1, "W")
        c.rect(9, 6, 14, 22, "A")
        for k in range(n):
            y = BARS[k]
            c.rect(10, y, 12, 3, "W" if flash else "E")
            if not flash:
                c.rect(10, y, 12, 1, "e")

    frames, durs = [], []
    for n in range(6):
        c = Canvas()
        battery(c, n)
        if n == 0:
            c.rect(10, 26, 12, 1, "R")
        frames.append(finish(c)); durs.append(110)
    c = Canvas(); battery(c, 5, True); frames.append(finish(c)); durs.append(80)
    rng = random.Random(2)
    for k in range(6):
        c = Canvas()
        battery(c, 5)
        c.outline()
        L = Canvas()
        pts = BOLTS[k % 2]
        L.poly(pts, "W" if k % 3 == 1 else "Y")
        L.line(pts[0][0] + 1, pts[0][1] + 1, pts[1][0] + 2, pts[1][1] - 1, "W")
        L.line(pts[2][0] - 1, pts[2][1] + 1, pts[3][0], pts[3][1] - 2, "W")
        for _ in range(4):
            x, y = rng.randint(3, 28), rng.randint(1, 29)
            if (x < 7 or x > 25):
                L.px(x, y, "Y")
        if k % 2 == 0:
            L.line(13, 1, 11, 0, "Y"); L.line(19, 1, 21, 0, "Y")
        L.outline()
        blit(c, L)
        frames.append(c); durs.append(70)
    return frames, durs


# =============================================================================================
# face emoji (shared gold face from pix.face)
# =============================================================================================
def happy_eye(c, cx, cy):
    for dx, dy in ((-3, 2), (-2, 1), (-1, 0), (0, 0), (1, 1), (2, 2)):
        c.px(cx + dx, cy + dy, "K"); c.px(cx + dx, cy + dy + 1, "K")


def laugh():
    N = 12
    frames, durs = [], []
    for f in range(N):
        c = Canvas()
        bob = 1 if f % 2 else 0
        pix.face(c, 15.5, 15.5 + bob, 12)
        happy_eye(c, 10, 10 + bob)
        happy_eye(c, 22, 10 + bob)
        h = 7 if f % 2 == 0 else 5
        for y in range(17 + bob, 17 + bob + h + 1):
            t = (y - 17 - bob) / h
            hw = 8 * math.sqrt(max(0, 1 - t * t))
            for x in range(32):
                if abs(x + .5 - 16) <= hw:
                    c.px(x, y, "K")
        for y in range(18 + bob, 17 + bob + h):
            t = (y - 17 - bob) / h
            hw = 7 * math.sqrt(max(0, 1 - t * t))
            for x in range(32):
                if abs(x + .5 - 16) <= hw:
                    c.px(x, y, "A")
        c.rect(10, 18 + bob, 12, 1, "W")
        c.rect(13, 17 + bob + h - 2, 6, 1, "r")
        c.rect(14, 17 + bob + h - 3, 4, 1, "r")
        c.outline()
        T = Canvas()
        # a tear wells up at each outer eye corner, then is flung outward in an arc; one every 3 frames
        for side in (-1, 1):
            ox = 16 + side * 10
            for born in range(-9, N, 3):
                age = (f - born - (1 if side > 0 else 0)) % N
                if age == 0:
                    drop(T, ox - 1 + side, 11 + bob, 1)
                elif age <= 3:
                    x = ox + side * (1 + 1.7 * age)
                    y = 11 - 4.2 * age + 0.9 * age * age
                    drop(T, int(round(x)) - 2, int(round(y)), 2 if age < 3 else 1)
        T.outline()
        blit(c, T)
        frames.append(c); durs.append(80)
    return frames, durs


def cry():
    N = 12
    frames, durs = [], []
    for f in range(N):
        c = Canvas()
        pix.face(c, 15.5, 13.5, 12)
        # sad brows and shut eyes
        c.line(7, 7, 11, 6, "K"); c.line(20, 6, 24, 7, "K")
        c.rect(7, 10, 5, 2, "K"); c.rect(20, 10, 5, 2, "K")
        c.px(7, 9, "K"); c.px(24, 9, "K")
        # wailing mouth (wobbles)
        rx = 4 if f % 2 else 5
        c.ellipse(15.5, 19.5, rx, 3, "K")
        c.ellipse(15.5, 19.5, rx - 1, 2, "A")
        c.rect(14, 21, 4, 1, "r")
        c.outline()
        T = Canvas()
        width = 8 + f * 2
        T.ellipse(15.5, 28.5, min(width, 15), 1.6, "L")
        T.rect(16 - min(width, 15) // 2, 28, min(width, 15), 1, "W")
        for sx in (8, 22):
            for y in range(12, 29):
                T.rect(sx, y, 2, 1, "L")
                if (y - f * 2) % 5 == 0:
                    T.px(sx, y, "W")
                if (y - f * 2) % 5 == 2:
                    T.px(sx + 1, y, "B")
        for k, sx in enumerate((8, 22)):
            if (f + k) % 3 == 0:
                T.px(sx - 2, 26, "W"); T.px(sx + 3, 25, "W")
            elif (f + k) % 3 == 1:
                T.px(sx - 3, 24, "W"); T.px(sx + 4, 24, "W")
        T.outline()
        blit(c, T)
        frames.append(c); durs.append(90)
    return frames, durs


def mindblown():
    CY = 19.5

    def head(f_eyes=0):
        c = Canvas()
        pix.face(c, 15.5, CY, 11)
        for ex in (11, 20):
            c.ellipse(ex, 18, 2, 3 + f_eyes, "W")
            c.rect(ex, 18, 1, 2, "K")
        c.circle(15.5, 25, 2, "K")
        c.circle(15.5, 25, 1, "A")
        return c

    def crack(x):
        return 13 + (1 if (x // 2) % 2 else 0)

    def split(c):
        cap, rest = Canvas(), Canvas()
        data = c.img.load()
        for y in range(32):
            for x in range(32):
                p = data[x, y]
                if p[3]:
                    (cap if y < crack(x) else rest).px(x, y, p[:3])
        return cap, rest

    frames, durs = [], []
    seq = ["calm", "shake1", "shake2", "boom", "fire", "smoke1", "smoke2", "smoke3", "wisp", "fall1", "land", "calm2"]
    for i, st in enumerate(seq):
        c = Canvas()
        if st in ("calm", "calm2"):
            blit(c, head(0))
            if st == "calm2":
                c.px(15, 9, "Y")
            frames.append(finish(c)); durs.append(120 if st == "calm" else 110)
            continue
        if st.startswith("shake"):
            dx = 1 if st == "shake1" else -1
            h = head(1)
            for x in range(6, 26):
                h.px(x, crack(x) - 1, "D")
            blit(c, h, dx, 0)
            frames.append(finish(c)); durs.append(70)
            continue
        cap, rest = split(head(1))
        # open top: dark hole along the crack
        for x in range(6, 26):
            if rest.get(x, crack(x))[3]:
                rest.px(x, crack(x), "A")
                rest.px(x, crack(x) + 1, "D" if x % 3 else "A")
        blit(c, rest)
        c.outline()
        T = Canvas()
        if st == "boom":
            blit(T, cap, 0, -4)
            star(T, 15, 9, 6, "W", "Y")
        elif st == "fire":
            rot(T, cap, 9, 0, 15.5, 10, -35)
            T.circle(15.5, 7, 5, "F"); T.circle(15.5, 7, 3, "Y"); T.circle(15.5, 7, 1, "W")
            for x, y in ((5, 3), (26, 4), (8, 12), (24, 11), (3, 9), (28, 8)):
                T.px(x, y, "G")
        elif st.startswith("smoke"):
            k = int(st[-1])
            yy = 8 - 2 * k
            for (ox, oy, r) in ((-4, 0, 3 + (k > 1)), (4, 0, 3 + (k > 1)), (0, -3, 4), (0, 3, 2)):
                T.circle(15.5 + ox, yy + oy, r, "S")
            for (ox, oy, r) in ((-3, -1, 1), (3, -2, 1), (0, -4, 2)):
                T.circle(15.5 + ox, yy + oy, r, "W")
            T.rect(14, yy + 4, 4, 13 - (yy + 4) + 1, "N")
            if k == 1:
                T.circle(15.5, yy + 1, 2, "F")
            for x, y in ((4 - k, 14 + 3 * k), (27 + k, 13 + 3 * k)):
                T.px(x, y, "G")
        elif st == "wisp":
            T.rect(15, 9, 2, 4, "N")
            T.circle(13, 6, 2, "S"); T.circle(19, 4, 2, "S"); T.circle(16, 2, 1, "W")
            T.px(12, 5, "W"); T.px(19, 3, "W")
        elif st == "fall1":
            blit(T, cap, 0, -7)
        elif st == "land":
            blit(T, cap, 0, -1)
            for x, y in ((4, 12), (27, 12), (3, 10), (28, 10)):
                T.px(x, y, "W")
        T.outline()
        blit(c, T)
        frames.append(c)
        durs.append({"boom": 80, "fire": 80, "smoke1": 90, "smoke2": 100, "smoke3": 100, "wisp": 110,
                     "fall1": 70, "land": 90}[st])
    return frames, durs


def sweat():
    N = 14
    frames, durs = [], []
    # sweat drop path: forms on the brow (top right), grows, then runs down the right side
    path = [(22, 4, 0), (22, 4, 1), (21, 3, 2), (21, 3, 2), (21, 4, 2), (22, 7, 2), (23, 10, 2),
            (24, 14, 2), (25, 18, 2), (25, 23, 1), (25, 27, 1), (25, 31, 0), (None, 0, 0), (None, 0, 0)]
    for f in range(N):
        c = Canvas()
        pix.face(c)
        # worried brows, open eyes
        c.line(7, 9, 11, 7, "K"); c.line(20, 7, 24, 9, "K")
        c.rect(9, 11, 3, 4, "K"); c.rect(20, 11, 3, 4, "K")
        c.px(9, 11, "W"); c.px(20, 11, "W")
        # nervous toothy grin (trembles)
        j = f % 2
        c.rect(7, 18, 18, 6, "K")
        c.px(7, 18, "G"); c.px(24, 18, "G")
        c.rect(8, 19, 16, 4, "W")
        c.rect(8, 21 - 0, 16, 1, "K")
        for x in (11 + j, 15 + j, 19 + j):
            c.rect(x, 19, 1, 4, "K")
        x, y, s = path[f]
        if x is not None and 6 <= f < 11:      # wet streak left on the skin behind the running drop
            for yy in range(8, min(y, 27)):
                tx = 23 + (yy - 8) * 3 // 19
                if c.get(tx + 2, yy)[3] and c.get(tx + 2, yy)[:3] != pix.PAL["K"]:
                    c.px(tx + 2, yy, "Y")
        c.outline()
        T = Canvas()
        if x is not None:
            if s == 2:
                drop(T, x, y, 2)
            elif s == 1:
                drop(T, x + 1, y, 1)
            else:
                drop(T, x + 1, y, 0)
        else:
            T.px(22 + (f - 12), 4, "L")
        T.outline()
        blit(c, T)
        frames.append(c); durs.append([100, 100, 110, 120, 90, 70, 70, 70, 70, 70, 70, 80, 100, 110][f])
    return frames, durs


# =============================================================================================
# registry / main
# =============================================================================================
ALL = [
    ("cheers", cheers), ("confetti", confetti), ("jackpot", jackpot), ("breaking", breaking),
    ("hourglass", hourglass), ("fire", fire), ("rally", rally), ("laugh", laugh), ("cry", cry),
    ("mindblown", mindblown), ("sweat", sweat),
]


def gif_info(path):
    im = Image.open(path)
    ds = []
    try:
        while True:
            ds.append(im.info.get("duration", 0))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return ds


# Every loop is cyclic, so each GIF starts on its most telling frame: that is the still Discord
# shows when animation is off (and in some pickers).
START = {
    "cheers": 5, "confetti": 6, "jackpot": 12, "hourglass": 4, "fire": 8, "rally": 8, "cry": 6, "mindblown": 6,
    "sweat": 4,
}


def main(argv):
    want = [a.replace("psbl_", "") for a in argv]
    paths = []
    for name, fn in ALL:
        if want and name not in want:
            continue
        frames, durs = fn()
        k = START.get(name, 0)
        frames, durs = frames[k:] + frames[:k], list(durs[k:]) + list(durs[:k])
        path = OUT / f"psbl_{name}.gif"
        pix.save_gif(frames, path, durs)
        ds = gif_info(path)
        ok = 8 <= len(ds) <= 24 and all(60 <= d <= 140 for d in ds)
        print(f"{'ok ' if ok else 'BAD'} psbl_{name}.gif  frames={len(ds):2d}  ms={sum(ds):5d}  "
              f"size={path.stat().st_size / 1024:5.1f} KB  durs={ds if not ok else ''}")
        paths.append(path)
    if not want:
        pix.sheet(paths, HERE / "anim_a_sheet.png")
        print("sheet: anim_a_sheet.png")
    return paths


if __name__ == "__main__":
    main(sys.argv[1:])
