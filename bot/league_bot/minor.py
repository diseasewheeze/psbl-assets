"""/minor: is a player PSBL minor-eligible? (Article VII)

7.2  A player is minor-eligible while his career MLB regular-season totals stay
     within MLB's rookie limits: no more than sport.MINORS_MAX_AB at-bats and no
     more than sport.MINORS_MAX_OUTS outs pitched (50 innings). No age limit.
7.3  Career totals keep accumulating during the Season. At-bats count only from
     the player's own plate appearances (his hitting stats; the at-bats he
     faced as a pitcher never count). The Commissioner's determination is final.

The rule is sport.minor_eligible, the same one the nightly watch uses
(automation/commissioner/minors.py), and the lookups go through
core/mlb_people.py: a search across every level, so a prospect without MLB time
is found too, and career MLB totals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import embeds as E
from . import shared  # noqa: F401  (puts automation/ on the path)

from core import mlb_people as mp  # noqa: E402
from core import sport  # noqa: E402

NOTE = "By MLB's official career statistics. The Commissioner's determination is final (7.3)."
FOOTER = "PSBL LEAGUE BOT • MINOR ELIGIBILITY"
NEAR_AB = 20      # "close to the limit" note within this many at-bats
NEAR_OUTS = 15    # or this many outs (5 innings)


@dataclass(frozen=True)
class Verdict:
    at_bats: int
    outs: int
    eligible: bool
    reasons: tuple[str, ...]

    @property
    def innings(self) -> str:
        return mp.innings_text(self.outs)


def verdict(at_bats: int, outs: int) -> Verdict:
    """The Article VII test on career MLB regular-season at-bats (hitting only) and outs pitched."""
    reasons = []
    if at_bats > sport.MINORS_MAX_AB:
        reasons.append(f"{at_bats} career MLB at-bats (limit {sport.MINORS_MAX_AB})")
    if outs > sport.MINORS_MAX_OUTS:
        reasons.append(f"{mp.innings_text(outs)} career MLB innings (limit {sport.MINORS_MAX_OUTS // 3})")
    return Verdict(at_bats, outs, sport.minor_eligible(at_bats, outs), tuple(reasons))


# ------------------------------------------------------------ MLB lookups
def query_name(query: str) -> str:
    """Accept Fantrax-style "Last, First" as well as "First Last"."""
    query = " ".join(query.split())
    return mp.display_name(query) if "," in query else query


def candidates(people: list[mp.Person], query: str, team: str | None = None) -> list[mp.Person]:
    """Players from the MLB search that match the query, best tier first.

    Tiers: exact full name, then exact last name, then a partial name. When
    several share the exact name and only one is active, that one wins.
    """
    rows = [p for p in people if isinstance(p, mp.Person)]
    if team:
        wanted = mp.team_code(team)
        rows = [p for p in rows if p.team == wanted]
    q = mp.norm_name(query_name(query))
    if not q:
        return []
    tiers = (
        lambda p: mp.norm_name(p.name) == q,
        lambda p: mp.norm_name(mp.split_name(p.name)[1]) == q,
        lambda p: q in mp.norm_name(p.name),
    )
    for test in tiers:
        found = [p for p in rows if test(p)]
        if found:
            active = [p for p in found if p.active]
            return active if len(found) > 1 and len(active) == 1 else found
    return []


def _where(p: mp.Person) -> str:
    if p.team and p.level_team and p.level_team != mp.TEAM_NAMES.get(p.team):
        return f"{p.team}, {p.level_team}"
    return p.team or p.level_team or "no team"


def ambiguous_message(query: str, found: list[mp.Person]) -> str:
    shown = ", ".join(f"{p.name} ({_where(p)}, {p.position or '?'})" for p in found[:6])
    more = f" and {len(found) - 6} more" if len(found) > 6 else ""
    return (f"More than one player matches “{E.clip(query, 60)}”: {shown}{more}. "
            "Use the full name, or add the MLB team, e.g. `team: LAD`.")


def unknown_message(query: str) -> str:
    return (f"No player matches “{E.clip(query, 60)}”. Check the spelling. The lookup uses MLB's player "
            "search, which covers the majors and the affiliated minor leagues; an amateur who hasn't signed "
            "can't be found.")


def lookup(mlb: Any, query: str, team: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """(embed, None) for one matched player, or (None, message) when unknown or ambiguous.

    ``mlb`` is an MlbLookup (search and career totals); blocking, so run it in a thread.
    """
    found = candidates(mlb.search(query_name(query)), query, team)
    if not found:
        return None, unknown_message(query + (f" ({team})" if team else ""))
    if len(found) > 1:
        return None, ambiguous_message(query, found)
    hit = found[0]
    got = mlb.career(hit.id)
    if got is None:
        return None, f"MLB has no record for {hit.name} right now, so the bot can't check eligibility."
    person, career = got
    v = verdict(career.at_bats, career.outs)
    return embed(person or hit, v), None


def embed(player: mp.Person, v: Verdict) -> dict[str, Any]:
    about = " • ".join(x for x in (_where(player), player.position,
                                    f"born {player.birth_date}" if player.birth_date else "",
                                    f"MLB debut {player.debut}" if player.debut else "no MLB debut yet") if x)
    note = NOTE
    if v.eligible:
        near = []
        if v.at_bats >= sport.MINORS_MAX_AB - NEAR_AB:
            near.append(f"{sport.MINORS_MAX_AB - v.at_bats} at-bats")
        if v.outs >= sport.MINORS_MAX_OUTS - NEAR_OUTS:
            near.append(f"{mp.innings_text(sport.MINORS_MAX_OUTS - v.outs)} innings")
        if near:
            note += f" Within {' and '.join(near)} of a limit; career totals keep counting during the Season (7.3)."
    fields = [
        ("CAREER MLB AT-BATS", f"**{v.at_bats}** of {sport.MINORS_MAX_AB} (regular season, as a hitter; at-bats "
                               "faced as a pitcher don't count)"),
        ("CAREER MLB INNINGS", f"**{v.innings}** of {sport.MINORS_MAX_OUTS // 3} (regular season)"),
        ("THRESHOLD", f"No more than {sport.MINORS_MAX_AB} career MLB at-bats and no more than "
                      f"{sport.MINORS_MAX_OUTS // 3} career MLB innings: MLB's rookie limits. No age limit (7.2)."),
    ]
    if not v.eligible:
        why = "; ".join(v.reasons)
        fields.append(("WHY NOT", why[:1].upper() + why[1:] + "."))
    fields.append(("NOTE", note))
    return E.card(
        f"MINOR ELIGIBILITY — {player.name.upper()}",
        f"{about}\n\n**PSBL minor-eligible: {'YES' if v.eligible else 'NO'}**",
        fields,
        FOOTER,
    )
