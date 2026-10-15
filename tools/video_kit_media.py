"""Pictures for the DBL Video Kit: the intro sting, the outro, the pixel wipe, overlays, the
EffectCraft backgrounds and art, and the placeholder slates that sit in the FilmCraft timelines.

All of it is pixel art from tools/pixel_kit.py, drawn on whole-pixel grids and enlarged with
nearest-neighbor so every pixel stays square. Movies are 1920x1080 at 30 fps: H.264 for the full-
screen pieces and ProRes 4444 with alpha for the wipe, which sits on a track above the cut.
"""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

from PIL import Image

import pixel_kit as px
from pixel_kit import (NAVY, NAVY_DK, NAVY_HI, NAVY_LO, WHITE, PAPER, RED, RED_LT, RED_DK, SKY, MUTED, BLUE,
                        STANDS, STEEL, STEEL_DK, GREEN, art, rect, dither, grain, put, sprite, enlarge,
                        draw_text, font, lockup, place, EMBLEM32)

W, H, FPS = 1920, 1080, 30


# ---------------------------------------------------------------- movie writing
def write_movie(path: Path, frames, n: int, alpha: bool = False):
    """Pipe `n` RGBA frames from the generator into ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if alpha:
        codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0"]
    else:
        codec = ["-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-tune", "animation",
                 "-movflags", "+faststart", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-an", *codec, "-r", str(FPS), str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    for f in frames:
        if f.size != (W, H):
            raise ValueError(f"frame {count} is {f.size}")
        proc.stdin.write(f.convert("RGBA").tobytes())
        count += 1
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on {path}")
    if count != n:
        raise ValueError(f"{path.name}: wrote {count} frames, expected {n}")


def save_png(path: Path, img: Image.Image):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


BAYER = px.BAYER


def bayer_mask(level: float, cell: int = 8) -> Image.Image:
    """1-bit ordered-dither mask at 1920x1080 in `cell`-pixel squares: level 0 = none, 1 = all."""
    a = Image.new("L", (W // cell, H // cell), 0)
    p = a.load()
    for y in range(a.height):
        for x in range(a.width):
            if BAYER[y & 3][x & 3] < level * 16:
                p[x, y] = 255
    return a.resize((W, H), Image.NEAREST)


# ---------------------------------------------------------------- backgrounds (also used by EffectCraft)
def bg_navy() -> Image.Image:
    """The channel-header ground at 1920x1080: textured navy, bleachers dither, red bar at the bottom.
    (Saved as bg-charcoal.png, the name the EffectCraft scripts use.)"""
    a = art(240, 135, NAVY)
    grain(a, [NAVY_HI, NAVY_LO], .02, 911)
    dither(a, 0, 112, 240, 20, STANDS)
    rect(a, 0, 132, 240, 1, RED_LT)
    rect(a, 0, 133, 240, 1, RED)
    rect(a, 0, 134, 240, 1, RED_DK)
    return enlarge(a, 8, (W, H))


def bg_dots() -> Image.Image:
    """Navy with a grid of darker dots (the hype intro's card ground)."""
    a = art(480, 270, NAVY)
    grain(a, [NAVY_HI, NAVY_LO], .015, 77)
    for y in range(2, 270, 6):
        for x in range(2 + (3 if (y // 6) % 2 else 0), 480, 6):
            a.putpixel((x, y), NAVY_LO + (255,))
    return enlarge(a, 4, (W, H))


def bg_arena() -> Image.Image:
    """The ballpark: red rails, the bleachers fading into navy, a dithered fade to deep navy."""
    return enlarge(px.bg_banner(240, 135, bars=1), 8, (W, H))


def bg_black() -> Image.Image:
    return enlarge(px.bg_plain(240, 135, NAVY_DK), 8, (W, H))


# ---------------------------------------------------------------- art pieces for EffectCraft
def emblem(k: int) -> Image.Image:
    """The league baseball, 32 x 32 art at k px per pixel (saved under the b-mark-* names)."""
    return sprite(EMBLEM32(), k)


def small_ball(k: int) -> Image.Image:
    return sprite("ball", k)


def banner_art() -> Image.Image:
    """A blank championship banner (navy with a red frame and a swallowtail), 384 x 592."""
    w, h, tail = 48, 74, 12
    a = art(w, h)
    rect(a, 1, 0, w - 2, 2, STEEL)                   # the rod it hangs from
    rect(a, 0, 0, 1, 2, STEEL_DK)
    rect(a, w - 1, 0, 1, 2, STEEL_DK)
    top, body_h = 2, h - 2
    for y in range(body_h):
        n = y - (body_h - tail)                      # row inside the swallowtail (>= 0)
        cut = n * 1.6 if n >= 0 else -1.0
        for x in range(4, w - 4):
            d = abs(x + .5 - w / 2)
            if d < cut:
                continue
            gold = x < 6 or x >= w - 6 or y < 2 or y >= body_h - 2 or (n >= 0 and d < cut + 2)
            a.putpixel((x, top + y), (RED if gold else NAVY) + (255,))
    rnd = random.Random(5)
    for _ in range(40):
        x, y = rnd.randrange(7, w - 7), rnd.randrange(4, body_h - tail - 2)
        a.putpixel((x, top + y), NAVY_HI + (255,))
    return a.resize((w * 8, h * 8), Image.NEAREST)


CUP = ["..GGGGGGGGGGGG..", ".GGLLLLLLLLLLGG.", "GG.GLLLLLLLLG.GG", "G..GLLLLLLLLG..G", "G..GLLLLLLLLG..G",
       "GG.GDLLLLLLDG.GG", ".GGGGDLLLLDGGGG.", "....GGDLLDGG....", "......GDDG......", "......GDDG......",
       ".....GGDDGG.....", "....DDDDDDDD....", "...KKKKKKKKKK...", "...KCCCCCCCCK...", "...KKKKKKKKKK..."]


def trophy(k: int) -> Image.Image:
    pal = {"G": (200, 206, 214), "L": WHITE, "D": STEEL_DK, "K": NAVY_DK, "C": RED}   # a silver cup, red name plate
    a = art(len(CUP[0]), len(CUP))
    for y, row in enumerate(CUP):
        for x, ch in enumerate(row):
            if ch in pal:
                a.putpixel((x, y), pal[ch] + (255,))
    return a.resize((a.width * k, a.height * k), Image.NEAREST)


def stamp_frame(color) -> Image.Image:
    """The league's status-stamp frame with no word in it (916 x 368)."""
    a = art(px.STAMP_W, px.STAMP_H)
    px.frame(a, 2, 2, 111, 42, 2, 3, color, wear=.04, seed=3)
    px.frame(a, 5, 5, 105, 36, 1, 2, color)
    return enlarge(a, 8, (916, 368))


def corner_bug() -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    b = small_ball(6)
    alpha = b.getchannel("A").point(lambda v: int(v * .85))
    b.putalpha(alpha)
    img.alpha_composite(b, (W - 96 - b.width, H - 60 - b.height))
    return img


# ---------------------------------------------------------------- the intro sting (3.0 s)
def intro_sting_frames():
    bg = bg_black()
    sizes = {15: 24, 16: 18, 17: 14}
    shake = {15: (12, -8), 16: (-10, 6), 17: (8, -6), 18: (-6, 4), 19: (4, -2), 20: (-2, 2)}
    flash = {15: .55, 16: .35, 17: .18}
    tag = px.LEAGUE_NAME.upper()
    rnd = random.Random(26)
    sparks = [(rnd.randrange(560, 1360) // 8 * 8, rnd.randrange(170, 640) // 8 * 8, rnd.randrange(66, 84)) for _ in range(26)]
    for f in range(90):
        img = bg.copy()
        if f < 15:                                   # the CRT line opens out from the center
            w = min(W, int(W * ((f + 1) / 13) ** 1.5)) // 8 * 8
            col = WHITE if f >= 12 else RED
            rect(img, (W - w) // 2, H // 2 - 4, w, 8, col)
        else:
            k = sizes.get(f, 12)
            b = emblem(k)
            dx, dy = shake.get(f, (0, 0))
            place(img, b, 960 + dx, 420 + dy, snap=2)
            if f >= 30:                              # the tagline types on, one letter a frame
                n = min(len(tag), f - 29)
                full_w = font("silk-bold").width(tag, 6)
                draw_text(img, tag[:n], "silk-bold", 6, (W - full_w) // 2 // 2 * 2, 680, WHITE)
            if f >= 66:
                g = min(1.0, (f - 65) / 4)
                rw = int(900 * g) // 12 * 12
                rect(img, 960 - rw // 2, 738, rw, 6, RED)
                if f >= 68:
                    draw_text(img, f"EST. {px.LEAGUE_EST}", "silk", 4, 960, 768, RED_LT, align="c")
                for x, y, t0 in sparks:              # white sparkles blink around the ball
                    if f >= t0 and (f + x) % 6 < 3 and f < 84:
                        rect(img, x, y, 8, 8, WHITE if (x // 8) % 3 else RED_LT)
            if f in flash:
                over = Image.new("RGBA", (W, H), WHITE + (int(255 * flash[f]),))
                img.alpha_composite(over)
        if f >= 78:                                  # ordered-dither dissolve to black
            level = min(1.0, (f - 77) / 11)
            img.paste(Image.new("RGBA", (W, H), NAVY_DK + (255,)), (0, 0), bayer_mask(level))
        yield img


# ---------------------------------------------------------------- the outro (5.0 s)
def park_scene(rx: int, bob: int) -> Image.Image:
    """The title-screen ballpark (240 x 135 art) with the drag tractor at art x = rx; smooth dirt behind it."""
    w, h, bars = 240, 135, 2
    a = px.bg_plain(w, h, NAVY_DK)
    dither(a, 0, bars, w, 44, NAVY, down=False)
    px.field_scene(a, h - bars - px.SPLASH_FIELD - px.WALL_H, px.SPLASH_FIELD, rx, frame=bob)
    rect(a, 0, 0, w, bars, RED)
    rect(a, 0, h - bars, w, bars, RED)
    return enlarge(a, 8, (W, H))


def outro_frames():
    wall_top = (135 - 2 - px.SPLASH_FIELD - px.WALL_H) * 8
    lk = px.fit_lockup(30, 5, W * 17 // 20, wall_top - 220)
    for f in range(150):
        rx = int(-60 + (f / 149) * 320)
        img = park_scene(rx, 1 if (f // 4) % 2 else 0)
        drop = max(0, 8 - f) * 24                    # the lockup drops in over 8 frames
        place(img, lk, W // 2, (16 + wall_top) // 2 - 40 - drop, snap=5)
        if f >= 24:
            draw_text(img, "SEE YOU AT THE BALLPARK", "silk", 5, 960, wall_top - 120, WHITE, align="c")
        if f >= 138:
            level = (f - 137) / 12
            img.paste(Image.new("RGBA", (W, H), NAVY_DK + (255,)), (0, 0), bayer_mask(level))
        yield img


# ---------------------------------------------------------------- the pixel wipe (20 frames, alpha)
def wipe_frames():
    cols, rows, cell = 16, 9, 120
    order = {}
    for y in range(rows):
        for x in range(cols):
            order[(x, y)] = (x + (rows - 1 - y) * .5) / (cols - 1 + (rows - 1) * .5)   # a diagonal sweep
    for f in range(20):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for (x, y), o in order.items():
            if f <= 9:                               # cover: blocks fill in, left to right (all by frame 9)
                p = (f + 1) / 10
                on = o <= p
                edge = on and o > p - .12
            else:                                    # uncover from frame 11 (frames 9 and 10 are fully covered)
                p = (f - 10) / 9 * 1.0001
                on = o >= p
                edge = on and o < p + .12
            if on:
                rect(img, x * cell, y * cell, cell, cell, RED if edge and f not in (9, 10) else NAVY)
                if not edge:
                    rect(img, x * cell + 52, y * cell + 52, 16, 16, NAVY_LO)
        yield img


# ---------------------------------------------------------------- placeholder slates
KIND = {
    "camera": ("CAMERA", BLUE), "screen": ("SCREEN RECORDING", GREEN), "render": ("EFFECTCRAFT RENDER", SKY),
    "broll": ("B-ROLL", STEEL), "card": ("FILMCRAFT TITLE", WHITE), "vo": ("VOICE", RED_LT),
}


def wrap(text: str, face: str, scale: int, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font(face).width(t, scale) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def slate(kind: str, title: str, lines: list[str]) -> Image.Image:
    """A placeholder: what goes in this slot, in big type, with the steps under it."""
    label, color = KIND[kind]
    img = bg_dots()
    for x in range(48, W - 48, 48):                  # dashed frame in the kind's color
        rect(img, x, 48, 24, 6, color)
        rect(img, x, H - 54, 24, 6, color)
    for y in range(48, H - 48, 48):
        rect(img, 48, y, 6, 24, color)
        rect(img, W - 54, y, 6, 24, color)
    draw_text(img, f"PLACEHOLDER • {label}", "silk", 4, 120, 120, color)
    scale = 8
    tl = wrap(title.upper(), "jersey", scale, W - 240)
    while len(tl) > 3 and scale > 4:
        scale -= 2
        tl = wrap(title.upper(), "jersey", scale, W - 240)
    y = 190
    for t in tl:
        draw_text(img, t, "jersey", scale, 120, y, WHITE, shadow=NAVY_DK)
        y += scale * 13
    y += 30
    for line in lines:
        for t in wrap(line, "silk", 4, W - 240):
            draw_text(img, t, "silk", 4, 120, y, MUTED)
            y += 40
        y += 12
    b = small_ball(4)
    img.alpha_composite(b, (W - 120 - b.width, H - 110 - b.height))
    return img


# ---------------------------------------------------------------- build
def build(media: Path, ec_images: Path) -> dict[str, str]:
    """Write the movies and overlays (FilmCraft/Media) and the EffectCraft art; returns name -> path."""
    out = {}
    write_movie(media / "Stings" / "dbl-intro-sting.mp4", intro_sting_frames(), 90)
    write_movie(media / "Stings" / "dbl-outro.mp4", outro_frames(), 150)
    write_movie(media / "Transitions" / "dbl-pixel-wipe.mov", wipe_frames(), 20, alpha=True)
    save_png(media / "Overlays" / "dbl-corner-bug.png", corner_bug())
    images = {
        "bg-charcoal.png": bg_navy(), "bg-dots.png": bg_dots(), "bg-arena.png": bg_arena(), "bg-black.png": bg_black(),
        "b-mark-12.png": emblem(12), "b-mark-8.png": emblem(8), "b-mark-4.png": emblem(4), "b-small-6.png": small_ball(6),
        "wordmark.png": lockup(30, 5), "wordmark-small.png": lockup(18, 3), "banner.png": banner_art(),
        "trophy.png": trophy(8), "stamp-green.png": stamp_frame(GREEN), "stamp-red.png": stamp_frame(RED),
        "stamp-gold.png": stamp_frame(SKY),
    }
    for name, img in images.items():
        save_png(ec_images / name, img)
        out[name] = str(ec_images / name)
    save_png(media / "Backgrounds" / "dbl-bg-charcoal.png", images["bg-charcoal.png"])
    save_png(media / "Backgrounds" / "dbl-bg-arena.png", images["bg-arena.png"])
    return out
