"""Six 8-bit soundboard emoji (16 x 16 art pixels, exported 128 x 128) in the league palette (navy, red, white).

Usage: python brand/sounds/emoji/generate_emoji.py [out_dir]   (default: this folder)
"""
import sys
from PIL import Image
P = {"K": (7, 21, 40), "W": (255, 255, 255), "G": (189, 48, 57), "D": (142, 31, 39), "Y": (226, 92, 100),
     "R": (189, 48, 57), "r": (226, 92, 100), "S": (154, 161, 169), "N": (110, 116, 124), "B": (44, 86, 150),
     "L": (143, 166, 199), "C": (246, 247, 249), "M": (52, 62, 78)}
# per-emoji tweaks: the gavel is wood, the siren's rays are white
OVERRIDE = {"gavel": {"G": (184, 118, 58), "Y": (222, 170, 108), "D": (138, 84, 38)},
            "goalhorn": {"G": (255, 255, 255)}}
E = {
 "goalhorn": [
  "................",
  "..G....GG....G..",
  "...G...GG...G...",
  "................",
  ".....KKKKKK.....",
  "....KRRRrrRK....",
  "...KRRRRrWrRK...",
  "...KRRRRRrrRK...",
  "...KRRRRRRRRK...",
  "...KRRRRRRRRK...",
  "..KKKKKKKKKKKK..",
  "..KSSSSSSSSSSK..",
  "..KSWSSSSSSSSK..",
  "..KNNNNNNNNNNK..",
  "..KKKKKKKKKKKK..",
  "................"],
 "gavel": [
  "................",
  "..KKKKKKKKKKKK..",
  ".KGKYYYYYYYYKGK.",
  ".KGKGGGGGGGGKGK.",
  ".KDKDDDDDDDDKDK.",
  "..KKKKKKKKKKKK..",
  "......KGDK......",
  "......KGDK......",
  "......KGDK......",
  "......KGDK......",
  "......KKKK......",
  "................",
  "..KKKKKKKKKKKK..",
  ".KCCCCCCCCCCCCK.",
  ".KMMMMMMMMMMMMK.",
  "..KKKKKKKKKKKK.."],
 "drafthorn": [
  "................",
  "...........KK...",
  ".........KKGK...",
  ".......KKGGGK.G.",
  "..KK.KKGGGGGK...",
  ".KYGKGGGGGGGK.GG",
  ".KGGGGGGGGGGK...",
  ".KGGGGGGGGGGK.GG",
  ".KDDKDDDDDDDK...",
  "..KK.KKDDDDDK.G.",
  ".......KKDDDK...",
  ".........KKDK...",
  "...........KK...",
  "................",
  "................",
  "................"],
 "onclock": [
  "................",
  "..KKK......KKK..",
  ".KGGYK....KGGYK.",
  ".KGGK.KKKK.KGGK.",
  "..KK.KCCCCK.KK..",
  "....KCCCKCCK....",
  "...KCCCCKCCCK...",
  "...KCCCCKCCCK...",
  "...KCCCCKKKCK...",
  "...KCCCCCCCCK...",
  "...KCCCCCCCCK...",
  "....KCCCCCCK....",
  ".....KKKKKK.....",
  "....KK....KK....",
  "................",
  "................"],
 "trade": [
  "................",
  ".........K......",
  ".........KK.....",
  "..KKKKKKKKGK....",
  "..KGGGGGGGGGK...",
  "..KGGGGGGGGGGK..",
  "..KKKKKKKKGGK...",
  ".........KGK....",
  "....KLK..KK.....",
  "...KBLKKKKKKKK..",
  "..KBBBBBBBBBBK..",
  "...KBBBBBBBBBK..",
  "....KBBKKKKKKK..",
  ".....KBK........",
  "......K.........",
  "................"],
 "buzzer": [
  "................",
  "................",
  "..KKKKKKKKKKKK..",
  ".KMMMMMMMMMMMMK.",
  ".KMRRRRMMRRRRMK.",
  ".KMRMMRMMRMMRMK.",
  ".KMRMMRMMRMMRMK.",
  ".KMRMMRMMRMMRMK.",
  ".KMRMMRMMRMMRMK.",
  ".KMRRRRMMRRRRMK.",
  ".KMMMMMMMMMMMMK.",
  "..KKKKKKKKKKKK..",
  ".....KSSSSK.....",
  "....KNNNNNNK....",
  "....KKKKKKKK....",
  "................"],
}
out = sys.argv[1] if len(sys.argv) > 1 else str(__import__("pathlib").Path(__file__).resolve().parent)

for i, (name, rows) in enumerate(E.items()):
    assert len(rows) == 16 and all(len(r) == 16 for r in rows), name
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            pal = {**P, **OVERRIDE.get(name, {})}
            if ch in pal:
                im.putpixel((x, y), pal[ch] + (255,))
    big = im.resize((128, 128), Image.NEAREST)
    big.save(f"{out}/psbl_{name}.png", optimize=True)


