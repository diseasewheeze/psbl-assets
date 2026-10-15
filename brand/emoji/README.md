# League server emoji

94 original 8-bit emoji for the server: 44 static and 50 animated, all baseball or general reactions in the
league's navy, red and white. With the 6 soundboard emoji in `brand/sounds/emoji/`, that fills the 50 static
and 50 animated slots an unboosted server has. File names keep the `dbl_` prefix; `RENAMES.md` lists every
hockey emoji that was replaced and the baseball emoji that took its place.

Every emoji is a different idea. No static emoji repeats another, no animated emoji is a static one that
just moves, and none repeats a soundboard emoji.

- `static/` — 44 PNG files, 128 × 128
- `animated/` — 50 GIF files, 128 × 128, looping, each under 256 KB
- `static_a_sheet.png`, `static_b_sheet.png`, `anim_a_sheet.png`, `anim_b_sheet.png`, `anim_c_sheet.png` —
  contact sheets (each GIF is shown frame by frame)
- `pix.py` plus `static_a.py`, `static_b.py`, `anim_a.py`, `anim_b.py`, `anim_c.py` — the scripts that draw them.
  `python3 static_a.py` (and so on) rewrites that group's files and its sheet. Pillow only. `anim_c.py` is the
  ballpark set; the league ball in `dbl_ball` and `dbl_glove` comes from `tools/pixel_kit.py`.

Style: 32 × 32 pixel art enlarged 4×, hard pixels, the league palette (navy, red, white), a deep navy keyline
on every subject so it reads on Discord's dark and light themes. Our players wear red, opponents bright navy.
Gold appears only on things that are gold (coins, crowns, medals, beer) and on the yellow reaction faces and
hands. No real logos, marks or people.

## Uploading

Open **Server Settings → Emoji** and drag the files from a folder onto that page. Discord uploads them all
at once and names each emoji after its file, so nothing needs typing. Drag the 44 static files first, then the
50 animated ones; the page counts the two kinds separately (50 slots each). If Discord stops partway
through a batch, wait a minute and drag in the ones that are missing.

Members use them as `:dbl_homer:` and so on, or from the server's tab in the emoji picker. Discord lets
everyone see animated emoji, but only members with Nitro can send them.

## Static (44)

| Name | Shows |
|---|---|
| dbl_ball | The league baseball (the emblem) |
| dbl_dinger | A ball launched toward the seats |
| dbl_bat | A bat |
| dbl_catcher | A catcher's mask |
| dbl_cleat | A baseball cleat |
| dbl_helmet | A navy batting helmet with an ear flap |
| dbl_jersey | The navy league jersey from the back, number 27 |
| dbl_diamond | The field from above |
| dbl_cup | The championship trophy: a silver cup on a navy base |
| dbl_banner | A red championship banner |
| dbl_beer | A mug of beer |
| dbl_umpire | An umpire calling it |
| dbl_ejected | The umpire's thumb: you're outta here |
| dbl_pine_tar | A tin of pine tar |
| dbl_bottle | A water bottle |
| dbl_mitt | A batting glove |
| dbl_glove | A fielder's glove with a ball in the pocket |
| dbl_plate | Home plate between the batter's boxes |
| dbl_k | K, the strikeout |
| dbl_salty | A salt shaker |
| dbl_crown | A crown |
| dbl_trash | A trash can (trash talk) |
| dbl_faab | A money bag with a $ (FAAB) |
| dbl_contract | A signed contract with a wax seal |
| dbl_pick | A red "1ST" draft-pick ticket |
| dbl_scout | A magnifying glass over a prospect star |
| dbl_lineup | The lineup card on a clipboard |
| dbl_medal | A gold medal |
| dbl_spoon | The Wooden Spoon |
| dbl_pot | The Dynasty Pot: a cauldron of gold coins |
| dbl_rally_cap | A rally cap |
| dbl_tooth | A big grin with a missing front tooth |
| dbl_injury | A first-aid kit |
| dbl_hotdog | A ballpark hot dog |
| dbl_beard | A playoff beard |
| dbl_w | A big W |
| dbl_l | A big L |
| dbl_gg | GG |
| dbl_bullpen | The bullpen phone |
| dbl_error | E6 on the scoreboard |
| dbl_chirp | A red bird mid-chirp |
| dbl_apple | An apple (an assist) |
| dbl_sauce | Hot sauce (bringing the heat) |
| dbl_lock | A red padlock (lock it in) |

## Animated (50)

| Name | What happens |
|---|---|
| dbl_cheers | Two pints swing in and clink, foam splashes |
| dbl_confetti | A popper fires a burst of confetti |
| dbl_jackpot | Slot reels spin and land on three baseballs, coins pour out |
| dbl_breaking | A TV with a scrolling BREAKING ticker |
| dbl_hourglass | Sand drains, then the glass flips |
| dbl_fire | A flame flickers |
| dbl_rally | The rally meter charges bar by bar, then a lightning bolt crackles |
| dbl_laugh | Laughing so hard the tears fly |
| dbl_cry | Crying a river |
| dbl_mindblown | The top of the head blows off |
| dbl_sweat | A nervous grin, sweat dripping |
| dbl_sideeye | The eyes slide over and narrow |
| dbl_facepalm | A hand slaps over the face, then slides off |
| dbl_clap | Hands clap |
| dbl_hello | A hand waves |
| dbl_fistpump | A fist pumps, YES! |
| dbl_dice | Two dice are thrown, tumble and land |
| dbl_lottery | Balls tumble in the draft-lottery drum and one pops out |
| dbl_popcorn | Popcorn keeps popping |
| dbl_dumpsterfire | A dumpster burns |
| dbl_typing | The typing dots |
| dbl_rocket | A rocket lifts off on a column of smoke |
| dbl_stonks | A green line climbs the chart |
| dbl_tank | A red line crashes down the chart |
| dbl_spotlight | A spotlight swings onto a star |
| dbl_fireworks | A shell rises and bursts |
| dbl_micdrop | The mic drops and bounces |
| dbl_whiteflag | A white flag waves (I surrender) |
| dbl_vote | A ballot drops into the box |
| dbl_ghosted | A ghost fades away and comes back |
| dbl_skull | A skull laughs, eyes glowing |
| dbl_lfg | L, F, G stamp down one by one |
| dbl_drag | The grounds-crew tractor drags the infield smooth |
| dbl_homer | The ball sails over the outfield fence, HR lights up |
| dbl_paint | The target closes on the low, outside corner and the pitch paints it |
| dbl_foulpole | The ball clangs off the foul pole: a home run |
| dbl_heater | The radar gun climbs to 101 as a flaming fastball zips past |
| dbl_bunt | The bat squares and the ball dribbles up the line |
| dbl_knuckler | A knuckleball floats in, wobbling |
| dbl_swing | Wind-up, swing, crack, and the ball rockets out |
| dbl_brokenbat | The pitch jams the hitter and the bat snaps in two |
| dbl_brawl | Two batting helmets come off, then the fists come up |
| dbl_cycle | Single, double, triple, home run: each base lights up |
| dbl_slide | Feet first into the bag, dirt flying, SAFE |
| dbl_robbed | A glove reaches over the wall and steals the home run |
| dbl_punchout | The umpire rings him up: strike three |
| dbl_batflip | The bat goes end over end |
| dbl_railbang | Fists pound the dugout rail |
| dbl_scoreboard | The home team puts up a run and the bulbs chase |
| dbl_squirrel | The rally squirrel dashes across the infield |
