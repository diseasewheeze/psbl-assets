#!/usr/bin/env python3
"""PSBL The Wire: source collectors and the headline classifier.

Shared by the engine (engine.py), which does the dedupe, roster tags and
Discord delivery. Collectors turn each source in sources.yaml into entries
(title, link, published, external_id; structured sources also give the player,
his MLB team and the channel):

  rss               any RSS or Atom feed. feedparser is imported only when an
                    RSS source is read, so the classifier and the transaction
                    rules load (and are tested) without it.
  mlb_transactions  MLB's official transaction log (MLB Stats API, through
                    core/mlb_people.py). Injured-list placements, activations
                    and transfers, and rehab assignments, go to injury-report;
                    recalls, options, contract selections, designations for
                    assignment, outrights, trades, releases, waiver claims and
                    signings go to mlb-transactions. A minor-league deal or a
                    plain draft-pick signing is posted only when the player is
                    on a PSBL roster. Other
                    records (status changes that aren't injured-list moves,
                    ordinary minor-league assignments) are left out.

Headlines from news feeds are classified by classify_title, in route priority:
breaking-news, injury-report, mlb-transactions, prospect-wire, mlb-news.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "sources.yaml"
USER_AGENT = "PSBL-The-Wire/1.0 (+https://github.com/diseasewheeze/psbl-assets)"
LEAGUE_TZ = ZoneInfo("America/New_York")

if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
from core import mlb_people as mp  # noqa: E402

BREAKING = (
    "out for the season", "out for season", "season-ending", "tommy john surgery", "suspended indefinitely",
    "suspended for the season", "retires", "announces retirement", "fired", "dismissed", "blockbuster trade",
    "lifetime ban",
)
# Long absences that belong in Breaking News even without a classic keyword,
# e.g. "Strider will miss rest of season with torn UCL" or "Alvarez out six to eight months".
BREAKING_EVENT_PATTERNS = (
    r"\b(?:miss(?:es|ing)?|out|sidelined|done)\b.{0,40}\b(?:rest|remainder|balance) of (?:the )?(?:regular )?season\b",
    r"\bout (?:at least )?(?:\w+(?:-\w+)? )?(?:to \w+ )?months?\b",
    r"\btorn (?:acl|achilles|ucl)\b",
    r"\btommy john\b",
)
INJURY = (
    "injury", "injured", "injured list", "torn", "acl", "ucl", "achilles", "oblique", "hamstring", "strain",
    "sprain", "likely to miss", "day-to-day", "surgery", "concussion", "fractured", "fracture", "setback",
    "rehab assignment", "rehab start", "returns from injury", "cleared to", "mri", "not expected to play",
    "will not play", "will miss", "expected to miss", "ruled out", "scratched", "exits with", "leaves game",
    "left the game",
)
INJURY_EVENT_PATTERNS = (
    # Injured-list moves written the short way: "lands on 10-day IL", "activated off the IL".
    r"\b(?:on|to|off|from) the (?:\d{1,2}-day )?il\b",
    r"\b\d{1,2}-day il\b",
    # A concrete absence without a classic injury word, e.g. "Buxton out for Twins' next two games".
    r"\bout for\b(?:\s+[a-z0-9][a-z0-9'\-]*){1,8}\s+(?:games?|days?|weeks?|months?)\b",
    r"\bout (?:for|at least) (?:\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:games?|days?|weeks?|months?)\b",
    r"\bout (?:\d+|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:-|to)\s*(?:\d+|two|three|four|five|six|seven|eight|nine|ten))?\s+(?:games?|days?|weeks?|months?)\b",
    r"\bmiss(?:es|ing)? (?:the )?(?:first |next )?\w*(?:\s+\w+){0,3}\s+(?:games?|starts?|days?|weeks?|months?)\b",
)

# Action-oriented patterns rather than broad nouns such as "trade" or
# "contract", so analysis headlines about a move stay in MLB News.
TRANSACTION_EVENT_PATTERNS = (
    r"\btraded\b",
    r"\btrades?\b.+\bto\b",
    r"\bacquire[sd]?\b",
    r"\bsign(?:s|ed)?\b",
    r"\bre-sign(?:s|ed)?\b",
    r"\bdesignate[sd]?\b.{0,40}\bfor assignment\b",
    r"\bdfa(?:'d|ed|s)?\b",
    r"\boutright(?:s|ed)?\b",
    r"\boptioned\b",
    r"\boptions?\b.+\bto (?:triple-a|double-a|the minors|minors)\b",
    r"\brecall(?:s|ed)?\b",
    r"\bcall(?:s|ed)? up\b",
    r"\bcall-up\b",
    r"\bselect(?:s|ed)? (?:the )?contract\b",
    r"\bwaive[sd]\b",
    r"\bwaivers\b",
    r"\bclaim(?:s|ed)\b",
    r"\breleas(?:e|es|ed)\b",
    r"\bagrees? to\b",
    r"\bagreed to\b",
    r"\bnon-tender(?:s|ed)?\b",
    r"\bopt(?:s|ed)? out\b",
    r"\b(?:exercise[sd]?|decline[sd]?|pick(?:s|ed)? up)\b.{0,30}\boption\b",
    r"\bcontract extension\b",
    r"\bextends?\b.+\bcontract\b",
)
TRANSACTION_ANALYSIS_PATTERNS = (
    r"\?\s*$",
    # Explainers and opinion pieces ("Why the Mets need to sign ...").
    # Not "will", "can" or "is": they start player names ("Will Smith signs ...").
    r"^(?:why|how|what|should|could|would)\b",
    r"\bneeds? to (?:sign|trade|re-sign|extend)\b",
    r"\bconsider(?:ing)? (?:a )?trade\b",
    r"\btrade (?:value|values|target|targets|rumor|rumors|rumour|rumours|market|ideas?|proposal|proposals|candidates?)\b",
    r"\b(?:possible|potential|hypothetical|mock) trade\b",
    r"\b(?:could|would|should|might|may) trade\b",
    r"\bimpact of\b.+\btrade\b",
    r"\bafter (?:the |a )?trade\b",
    r"\bgrading (?:the |a )?trade\b",
    r"\btrade analysis\b",
    r"\binterested in\b",
    r"\bpursu(?:e|es|ed|ing)\b",
)
PROSPECT = (
    "prospect", "prospects", "rookie", "minor league", "minor-league", "milb", "triple-a", "double-a", "high-a",
    "single-a", "low-a", "arizona fall league", "fall league", "futures game", "mlb draft", "draft prospect",
    "draft class", "farm system", "pipeline", "top 100", "first-round pick", "mlb debut",
)

GENERIC_TITLES = {
    "mlb news", "mlb headlines", "featured", "headlines", "latest news", "skip to main content",
}
IGNORE_PATTERNS = (
    r"^daily .*thread",
    r"^game thread",
    r"^game day thread",
    r"^post ?game thread",
    r"^pre ?game thread",
    r"^skip to main content$",
    r"promo code",
    r"bonus bets",
    r"\bbest bets?\b",
    r"\bpicks?,? (?:odds|predictions?)\b",
    r"\bodds,? (?:picks|predictions?)\b",
    r"\bpicks:",
    r"^today's top games to watch",
    r"^live:",
    r"\bstart times?\b",
    r"\bhow to watch\b",
    r"\bstarting lineups?\b",
    r"\bchat transcript\b",
    r"\bprospects? chat\b",
    r"^poll:",
    r"\bmailbag\b",
    r"\bnotes:",
    r"^minor mlb transactions",
)
REPORTER_PREFIX = re.compile(r"^\[[^\]]{2,40}\]\s+")


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text.lower()).strip()


def fingerprint(title: str) -> str:
    clean = re.sub(r"[^a-z0-9 ]", "", normalize(title))
    return hashlib.sha256(clean.encode()).hexdigest()[:16]


def term_matches(hay: str, term: str) -> bool:
    term = normalize(term)
    if re.fullmatch(r"[a-z0-9-]+", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", hay) is not None
    return term in hay


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    hay = normalize(text)
    return any(term_matches(hay, term) for term in terms)


def _matches(title: str, patterns: tuple[str, ...]) -> bool:
    text = normalize(title)
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def is_injury_event(title: str) -> bool:
    return _matches(title, INJURY_EVENT_PATTERNS)


def is_breaking_event(title: str) -> bool:
    return _matches(title, BREAKING_EVENT_PATTERNS)


def is_transaction_event(title: str) -> bool:
    if _matches(title, TRANSACTION_ANALYSIS_PATTERNS):
        return False
    return _matches(title, TRANSACTION_EVENT_PATTERNS)


def classify_title(title: str, breaking_allowed: bool) -> str:
    if breaking_allowed and (contains_any(title, BREAKING) or is_breaking_event(title)):
        return "breaking-news"
    if contains_any(title, INJURY) or is_injury_event(title) or is_breaking_event(title):
        return "injury-report"
    if is_transaction_event(title):
        return "mlb-transactions"
    if contains_any(title, PROSPECT):
        return "prospect-wire"
    return "mlb-news"


def route(title: str, source: dict) -> str:
    if source.get("force_channel"):
        return str(source["force_channel"])
    return classify_title(title, bool(source.get("breaking_allowed")))


def should_ignore(title: str, source_id: str, target: str) -> bool:
    t = normalize(title)
    if not t or t in GENERIC_TITLES or len(t) < 12:
        return True
    if any(re.search(pattern, t, re.I) for pattern in IGNORE_PATTERNS):
        return True
    # Community feeds: only reporter-attributed posts ("[Passan] ...") may count as news.
    if source_id.startswith("reddit_") and target == "mlb-news" and REPORTER_PREFIX.search(title.strip()) is None:
        return True
    return False


# --------------------------------------------------------------------- RSS
def get(url: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == 0:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(max(float(retry_after), 1.0), 5.0)
                    except ValueError:
                        delay = 2.0
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise
    raise RuntimeError(f"request failed: {last_error}")


def _http_url(value: object) -> str:
    text = str(value or "").strip()
    return text if re.match(r"^https?://", text, re.I) else ""


def _rss_entry_link(entry: object) -> str:
    """Find a usable article URL for an RSS entry.

    Some feeds do not always set ``entry.link``. Fall back to alternate link
    elements, then to the GUID/ID only when it is itself an HTTP(S) URL. Never
    invents a destination.
    """
    if not hasattr(entry, "get"):
        return ""
    direct = _http_url(entry.get("link", ""))
    if direct:
        return direct
    preferred: list[str] = []
    fallback: list[str] = []
    for row in entry.get("links") or []:
        if not hasattr(row, "get"):
            continue
        href = _http_url(row.get("href", ""))
        if not href:
            continue
        rel = str(row.get("rel") or "").strip().lower()
        (preferred if rel in ("", "alternate") else fallback).append(href)
    if preferred or fallback:
        return (preferred or fallback)[0]
    for key in ("id", "guid"):
        identifier = _http_url(entry.get(key, ""))
        if identifier:
            return identifier
    return ""


def fetch_rss(url: str) -> list[dict[str, str]]:
    import feedparser  # only needed to read feeds; the classifier and tests load without it

    response = get(url)
    feed = feedparser.parse(response.content)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(f"Feed parse failed: {getattr(feed, 'bozo_exception', 'unknown error')}")
    items: list[dict[str, str]] = []
    for entry in feed.entries:
        link = _rss_entry_link(entry)
        items.append({
            "title": " ".join(str(entry.get("title", "(untitled)")).split()),
            "link": link,
            "published": entry.get("published", entry.get("updated", "")),
            "external_id": entry.get("id", entry.get("guid", link)) or link,
        })
    return items


# --------------------------------------------------------------------- MLB transactions
INJURED_LIST = re.compile(r"\binjured list\b", re.I)
REHAB = re.compile(r"\brehab assignment\b", re.I)
MINOR_LEAGUE_DEAL = re.compile(r"\bminor league (?:contract|deal)\b", re.I)
MAJOR_LEAGUE_DEAL = re.compile(r"\b(?:major league (?:contract|deal)|extension)\b", re.I)
POSITIONS = r"RHP|LHP|P|C|1B|2B|3B|SS|LF|CF|RF|OF|IF|INF|DH|UT|UTIL"
ROSTER_MOVES = {"CU", "OPT", "SE", "DES", "OUT", "TR", "REL", "CLW", "SFA", "SGN"}
SIGNINGS = {"SFA", "SGN"}
MOVE_LABELS = {
    "SC": "Injured list", "ASG": "Rehab assignment", "CU": "Recalled", "OPT": "Optioned",
    "SE": "Contract selected", "DES": "Designated for assignment", "OUT": "Outrighted", "TR": "Trade",
    "REL": "Released", "CLW": "Claimed off waivers", "SFA": "Signed", "SGN": "Signed",
}
PLAYER_PAGE = "https://www.mlb.com/player/{id}"


def transaction_channel(move: mp.Transaction) -> str | None:
    """Where an MLB transaction is posted, or None when the Wire leaves it out."""
    if move.type_code == "SC":
        return "injury-report" if INJURED_LIST.search(move.description) else None
    if move.type_code == "ASG":
        return "injury-report" if REHAB.search(move.description) else None
    return "mlb-transactions" if move.type_code in ROSTER_MOVES else None


def rostered_only(move: mp.Transaction) -> bool:
    """Signings worth a post only for a player on a PSBL roster.

    Minor-league deals, and plain "signed" (SGN) records that name no
    major-league deal or extension: after the MLB Draft these are mostly draft
    picks signing, hundreds of them.
    """
    if move.type_code not in SIGNINGS:
        return False
    if MINOR_LEAGUE_DEAL.search(move.description):
        return True
    return move.type_code == "SGN" and not MAJOR_LEAGUE_DEAL.search(move.description)


def position_in(description: str, name: str) -> str:
    """The position MLB writes before a player's name ("placed CF Byron Buxton" -> "CF")."""
    match = re.search(rf"\b({POSITIONS})\s+{re.escape(name)}", description)
    return match.group(1) if match else ""


def transaction_entries(moves: Iterable[mp.Transaction]) -> list[dict[str, Any]]:
    """Wire entries for MLB transactions, newest first: one per move, one per trade (all its players)."""
    entries: dict[str, dict[str, Any]] = {}
    for move in sorted(moves, key=lambda m: (m.date, m.id), reverse=True):
        channel = transaction_channel(move)
        if channel is None or not move.person_id:
            continue
        player = {"player": move.name, "team": (move.mlb_teams or [""])[0], "teams": move.mlb_teams,
                  "position": position_in(move.description, move.name)}
        if move.type_code == "TR":
            key = f"mlb-tx|TR|{move.id}|{hashlib.sha1(move.description.encode('utf-8')).hexdigest()[:10]}"
            if key in entries:
                trade = entries[key]
                trade["players"].append(player)
                trade["teams"] = list(dict.fromkeys(trade["teams"] + move.mlb_teams))
                continue
        else:
            key = f"mlb-tx|{move.key}"
            if key in entries:
                continue  # MLB sometimes lists the same move twice under different ids
        entries[key] = {
            "title": move.description,
            "link": PLAYER_PAGE.format(id=move.person_id),
            "published": "",
            "external_id": key,
            "source_detail": MOVE_LABELS.get(move.type_code, move.type_text),
            "channel": channel,
            "structured": True,
            "only_if_rostered": rostered_only(move),
            **player,
            "players": [player],
        }
    return list(entries.values())


def fetch_mlb_transactions(source: dict, today: date | None = None, api: mp.MlbApi | None = None) -> list[dict[str, Any]]:
    """Recent MLB transactions (today and ``lookback_days`` before it, league time) as Wire entries."""
    today = today or datetime.now(LEAGUE_TZ).date()
    days = max(0, int(source.get("lookback_days", 1)))
    moves = (api or mp.MlbApi()).transactions(today - timedelta(days=days), today)
    return transaction_entries(moves)


def fetch_source(source: dict) -> list[dict[str, Any]]:
    source_type = source.get("type", "rss")
    if source_type == "rss":
        return fetch_rss(source["url"])
    if source_type == "mlb_transactions":
        return fetch_mlb_transactions(source)
    raise RuntimeError(f"Unsupported source type: {source_type}")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    print("PSBL The Wire: DRY RUN")
    print("No Discord messages will be sent.\n")
    total = 0
    for source in cfg["sources"]:
        if not source.get("enabled", False):
            continue
        mode = "DISCOVERY" if source.get("discovery_only", False) else "LIVE-CANDIDATE"
        print(f"## {source['name']} [{mode}]")
        try:
            entries = fetch_source(source)
        except Exception as exc:
            print(f"ERROR: {exc}\n")
            continue
        emitted = 0
        max_items = int(source.get("max_items", 10))
        for entry in entries:
            title = entry.get("title", "(untitled)")
            target = entry.get("channel") or route(title, source)
            if should_ignore(title, source.get("id", ""), target):
                continue
            label = f"discovery->{target}" if source.get("discovery_only", False) else target
            print(f"[{label}] {title}")
            print(f"  {entry.get('link', '')}")
            if entry.get("source_detail"):
                print(f"  source-detail={entry['source_detail']}")
            print(f"  fingerprint={fingerprint(title)}")
            emitted += 1
            total += 1
            if emitted >= max_items:
                break
        if emitted == 0:
            print("No usable entries after filtering")
        print()
    print(f"Dry run complete: {total} usable items classified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
