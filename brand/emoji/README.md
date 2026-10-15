# League server emoji

94 original 8-bit emoji for the server: 44 static and 50 animated, all baseball or general reactions in the
league's navy, red and white. With the 5 soundboard emoji in `brand/sounds/emoji/`, that uses 49 of the 50 static
slots and all 50 animated slots an unboosted server has. File names keep the `psbl_` prefix; `RENAMES.md` lists every
hockey emoji that was replaced and the baseball emoji that took its place.

Every emoji is a different idea. No static emoji repeats another, no animated emoji is a static one that
just moves, and none repeats a soundboard emoji.

- `static/` — 44 PNG files, 128 × 128
- `animated/` — 50 GIF files, 128 × 128, looping, each under 256 KB
- `static_a_sheet.png`, `static_b_sheet.png`, `anim_a_sheet.png`, `anim_b_sheet.png`, `anim_c_sheet.png` —
  contact sheets (each GIF is shown frame by frame)
- `pix.py` plus `static_a.py`, `static_b.py`, `anim_a.py`, `anim_b.py`, `anim_c.py` — the scripts that draw them.
  `python3 static_a.py` (and so on) rewrites that group's files and its sheet. Pillow only. `anim_c.py` is the
  ballpark set; the league ball in `psbl_ball` and `psbl_glove` comes from `tools/pixel_kit.py`.

Style: 32 × 32 pixel art enlarged 4×, hard pixels, the league palette (navy, red, white), a deep navy keyline
on every subject so it reads on Discord's dark and light themes. Our players wear red, opponents bright navy.
Gold appears only on things that are gold (coins, crowns, medals, beer) and on the yellow reaction faces and
hands. No real logos, marks or people.

## Uploading

Open **Server Settings → Emoji** and drag the files from a folder onto that page. Discord uploads them all
at once and names each emoji after its file, so nothing needs typing. Drag the 44 static files first, then the
50 animated ones; the page counts the two kinds separately (50 slots each). If Discord stops partway
through a batch, wait a minute and drag in the ones that are missing.

Members use them as `:psbl_homer:` and so on, or from the server's tab in the emoji picker. Discord lets
everyone see animated emoji, but only members with Nitro can send them.

## Static (44)

| Name | Shows |
|---|---|
| psbl_ball | The league baseball (the emblem) |
| psbl_dinger | A ball launched toward the seats |
| psbl_bat | A bat |
| psbl_catcher | A catcher's mask |
| psbl_cleat | A baseball cleat |
| psbl_helmet | A navy batting helmet with an ear flap |
| psbl_jersey | The navy league jersey from the back, number 27 |
| psbl_diamond | The field from above |
| psbl_cup | The championship trophy: a silver cup on a navy base |
| psbl_banner | A red championship banner |
| psbl_beer | A mug of beer |
| psbl_umpire | An umpire calling it |
| psbl_ejected | The umpire's thumb: you're outta here |
| psbl_pine_tar | A tin of pine tar |
| psbl_bottle | A water bottle |
| psbl_mitt | A batting glove |
| psbl_glove | A fielder's glove with a ball in the pocket |
| psbl_plate | Home plate between the batter's boxes |
| psbl_k | K, the strikeout |
| psbl_salty | A salt shaker |
| psbl_crown | A crown |
| psbl_trash | A trash can (trash talk) |
| psbl_faab | A money bag with a $ (FAAB) |
| psbl_contract | A signed contract with a wax seal |
| psbl_pick | A red "1ST" draft-pick ticket |
| psbl_scout | A magnifying glass over a prospect star |
| psbl_lineup | The lineup card on a clipboard |
| psbl_medal | A gold medal |
| psbl_spoon | The Wooden Spoon |
| psbl_pot | The Dynasty Pot: a cauldron of gold coins |
| psbl_rally_cap | A rally cap |
| psbl_tooth | A big grin with a missing front tooth |
| psbl_injury | A first-aid kit |
| psbl_hotdog | A ballpark hot dog |
| psbl_beard | A playoff beard |
| psbl_w | A big W |
| psbl_l | A big L |
| psbl_gg | GG |
| psbl_bullpen | The bullpen phone |
| psbl_error | E6 on the scoreboard |
| psbl_chirp | A red bird mid-chirp |
| psbl_apple | An apple (an assist) |
| psbl_sauce | Hot sauce (bringing the heat) |
| psbl_lock | A red padlock (lock it in) |

## Animated (50)

| Name | What happens |
|---|---|
| psbl_cheers | Two pints swing in and clink, foam splashes |
| psbl_confetti | A popper fires a burst of confetti |
| psbl_jackpot | Slot reels spin and land on three baseballs, coins pour out |
| psbl_breaking | A TV with a scrolling BREAKING ticker |
| psbl_hourglass | Sand drains, then the glass flips |
| psbl_fire | A flame flickers |
| psbl_rally | The rally meter charges bar by bar, then a lightning bolt crackles |
| psbl_laugh | Laughing so hard the tears fly |
| psbl_cry | Crying a river |
| psbl_mindblown | The top of the head blows off |
| psbl_sweat | A nervous grin, sweat dripping |
| psbl_sideeye | The eyes slide over and narrow |
| psbl_facepalm | A hand slaps over the face, then slides off |
| psbl_clap | Hands clap |
| psbl_hello | A hand waves |
| psbl_fistpump | A fist pumps, YES! |
| psbl_dice | Two dice are thrown, tumble and land |
| psbl_lottery | Balls tumble in the draft-lottery drum and one pops out |
| psbl_popcorn | Popcorn keeps popping |
| psbl_dumpsterfire | A dumpster burns |
| psbl_typing | The typing dots |
| psbl_rocket | A rocket lifts off on a column of smoke |
| psbl_stonks | A green line climbs the chart |
| psbl_tank | A red line crashes down the chart |
| psbl_spotlight | A spotlight swings onto a star |
| psbl_fireworks | A shell rises and bursts |
| psbl_micdrop | The mic drops and bounces |
| psbl_whiteflag | A white flag waves (I surrender) |
| psbl_vote | A ballot drops into the box |
| psbl_ghosted | A ghost fades away and comes back |
| psbl_skull | A skull laughs, eyes glowing |
| psbl_lfg | L, F, G stamp down one by one |
| psbl_drag | The grounds-crew tractor drags the infield smooth |
| psbl_homer | The ball sails over the outfield fence, HR lights up |
| psbl_paint | The target closes on the low, outside corner and the pitch paints it |
| psbl_foulpole | The ball clangs off the foul pole: a home run |
| psbl_heater | The radar gun climbs to 101 as a flaming fastball zips past |
| psbl_bunt | The bat squares and the ball dribbles up the line |
| psbl_knuckler | A knuckleball floats in, wobbling |
| psbl_swing | Wind-up, swing, crack, and the ball rockets out |
| psbl_brokenbat | The pitch jams the hitter and the bat snaps in two |
| psbl_brawl | Two batting helmets come off, then the fists come up |
| psbl_cycle | Single, double, triple, home run: each base lights up |
| psbl_slide | Feet first into the bag, dirt flying, SAFE |
| psbl_robbed | A glove reaches over the wall and steals the home run |
| psbl_punchout | The umpire rings him up: strike three |
| psbl_batflip | The bat goes end over end |
| psbl_railbang | Fists pound the dugout rail |
| psbl_scoreboard | The home team puts up a run and the bulbs chase |
| psbl_squirrel | The rally squirrel dashes across the infield |
