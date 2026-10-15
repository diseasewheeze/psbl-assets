# DBL server emoji

94 original 8-bit emoji for the server: 44 static and 50 animated. With the 6 soundboard emoji in
`brand/sounds/emoji/`, that fills the 50 static and 50 animated slots an unboosted server has.

Every emoji is a different idea. No static emoji repeats another, no animated emoji is a static one that
just moves, and none repeats a soundboard emoji.

- `static/` — 44 PNG files, 128 × 128
- `animated/` — 50 GIF files, 128 × 128, looping, each under 256 KB
- `static_a_sheet.png`, `static_b_sheet.png`, `anim_a_sheet.png`, `anim_b_sheet.png` — contact sheets
  (each GIF is shown frame by frame)
- `pix.py` plus `static_a.py`, `static_b.py`, `anim_a.py`, `anim_b.py` — the scripts that draw them.
  `python3 static_a.py` (and so on) rewrites that group's files and its sheet. Pillow only.

Style: 32 × 32 pixel art enlarged 4×, hard pixels, brand palette, a black keyline on every subject so it
reads on Discord's dark and light themes. Our players wear gold, opponents blue. No real logos or people.

## Uploading

Open **Server Settings → Emoji** and drag the files from a folder onto that page. Discord uploads them all
at once and names each emoji after its file, so nothing needs typing. Drag the 44 static files first, then the
50 animated ones; the page counts the two kinds separately (50 slots each). If Discord stops partway
through a batch, wait a minute and drag in the ones that are missing.

Members use them as `:dbl_goal:` and so on, or from the server's tab in the emoji picker. Discord lets
everyone see animated emoji, but only members with Nitro can send them.

## Static (44)

| Name | Shows |
|---|---|
| dbl_b | The DBL "B" |
| dbl_puck | A puck with the B on it |
| dbl_stick | A stick |
| dbl_mask | A goalie mask |
| dbl_skate | A skate |
| dbl_helmet | A gold helmet with a visor |
| dbl_jersey | The gold DBL jersey |
| dbl_rink | The rink from above |
| dbl_cup | The championship trophy |
| dbl_banner | A championship banner |
| dbl_beer | A mug of beer |
| dbl_whistle | The referee's whistle |
| dbl_sinbin | The penalty box with a 2-minute sign |
| dbl_tape | A roll of stick tape |
| dbl_bottle | A water bottle |
| dbl_mitt | A player's glove |
| dbl_trapper | A goalie's catching glove |
| dbl_faceoff | A faceoff dot |
| dbl_ice | An ice cube (ice cold) |
| dbl_salty | A salt shaker |
| dbl_crown | A crown |
| dbl_trash | A trash can (trash talk) |
| dbl_faab | A money bag with a $ (FAAB) |
| dbl_contract | A signed contract with a wax seal |
| dbl_pick | A "1ST" draft-pick ticket |
| dbl_scout | A magnifying glass over a prospect star |
| dbl_lineup | A coach's clipboard with a play drawn on it |
| dbl_medal | A gold medal |
| dbl_spoon | The Wooden Spoon |
| dbl_pot | The Dynasty Pot: a cauldron of gold coins |
| dbl_octopus | An octopus (the playoff tradition) |
| dbl_tooth | A big grin with a missing front tooth |
| dbl_injury | A first-aid kit |
| dbl_mullet | Hockey flow, in profile |
| dbl_beard | A playoff beard |
| dbl_w | A big W |
| dbl_l | A big L |
| dbl_gg | GG |
| dbl_pylon | A traffic cone (a pylon) |
| dbl_sieve | A colander with pucks falling through (a leaky goalie) |
| dbl_chirp | A bird mid-chirp |
| dbl_apple | An apple (an assist) |
| dbl_sauce | Hot sauce (a saucer pass) |
| dbl_lock | A padlock (lock it in) |

## Animated (50)

| Name | What happens |
|---|---|
| dbl_zamboni | The resurfacer drives across and leaves fresh ice behind |
| dbl_goal | The puck flies in and the net bulges |
| dbl_snipe | A target locks onto the corner and the puck hits it |
| dbl_bardown | The puck rings off the crossbar and drops in |
| dbl_topshelf | The puck arcs onto the top shelf beside the cookie jar, which rocks |
| dbl_fivehole | The pads open, the puck slides through, the pads close too late |
| dbl_dangle | The stick handles the puck side to side |
| dbl_slapshot | Wind-up, slap, the puck rockets away |
| dbl_snapped | A shot, and the stick snaps in two |
| dbl_tilly | Two gloves drop, then the fists come up |
| dbl_hattrick | Three hats rain down and pile up |
| dbl_cheers | Two pints swing in and clink, foam splashes |
| dbl_hockeystop | A skate digs in sideways and throws snow |
| dbl_padsave | The goalie kicks out a pad and the puck deflects away |
| dbl_confetti | A popper fires a burst of confetti |
| dbl_jackpot | Slot reels spin and land on BBB, coins pour out |
| dbl_breaking | A TV with a scrolling BREAKING ticker |
| dbl_penalty | The referee raises an arm, then points to the box |
| dbl_hourglass | Sand drains, then the glass flips |
| dbl_fire | A flame flickers |
| dbl_powerplay | A battery charges bar by bar, then a lightning bolt crackles |
| dbl_laugh | Laughing so hard the tears fly |
| dbl_cry | Crying a river |
| dbl_mindblown | The top of the head blows off |
| dbl_sweat | A nervous grin, sweat dripping |
| dbl_sideeye | The eyes slide over and narrow |
| dbl_facepalm | A hand slaps over the face, then slides off |
| dbl_clap | Hands clap |
| dbl_hello | A hand waves |
| dbl_fistpump | A fist pumps, YES! |
| dbl_kneeslide | The goal celebration: a knee slide with spray |
| dbl_glassbang | Fists bang on the glass |
| dbl_boardcheck | A gold player checks a blue player into the boards |
| dbl_rat | A rat scurries across the ice |
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
| league_bot | A ballot drops into the box |
| dbl_ghosted | A ghost fades away and comes back |
| dbl_skull | A skull laughs, eyes glowing |
| dbl_lfg | L, F, G stamp down one by one |
