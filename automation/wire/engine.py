#!/usr/bin/env python3
"""PSBL The Wire: routing, dedupe, roster tags and Discord delivery.

Architecture:
  GitHub Actions = brain
  Discord webhooks = delivery
  MLB's official transaction log = the one source for mlb-transactions
  (wire.py's mlb_transactions collector); other outlets' transaction
  headlines are recorded but not posted, so a move is announced once
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

import roster
import wire

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.league import load_league  # noqa: E402

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "sources.yaml"
STATE_DIR = ROOT / "state"
STATE_TTL_HOURS = 24 * 30
# After this long without a live run (the automation was paused, or down), the
# stories in the feeds are old news: record them as seen instead of posting.
REBASELINE_AFTER = timedelta(days=3)
FUZZY_DEDUPE_WINDOW_HOURS = 48
# MLB's transaction log posts each injured-list move with the player's name.
# Another source's injury story about the same player within this window
# repeats it, unless it says something worse (ESCALATION_TERMS).
SAME_PLAYER_WINDOW_HOURS = 12
# The same news from two outlets in MLB News / Breaking News: titles sharing
# most of their words within this window.
SAME_STORY_WINDOW_HOURS = 6
SAME_STORY_MIN_OVERLAP = 0.40
SAME_STORY_MIN_SHARED = 3
STORY_CHANNELS = {"mlb-news", "breaking-news"}
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from",
    "as", "is", "are", "be", "was", "his", "her", "their", "its", "it", "after", "vs", "has",
    "have", "he", "will", "into", "over", "up", "out", "off", "this", "that", "mlb", "new",
}
STRUCTURED_SOURCE = "mlb_transactions"
DEFAULT_COLOR = 0xBD3039  # league red
DEFAULT_MAX_SOURCE_ITEMS = 15
MAX_SOURCE_WORKERS = 4

# Production flood guards. Normal 15-minute runs should produce only a handful
# of truly new items. If a feed/parser suddenly exposes a backlog, these limits
# cap how many individual story posts go out. Anything over the limit is
# rolled into one roundup post per channel instead of being dropped, and is
# only remembered once that roundup has been delivered.
MAX_LIVE_POSTS_PER_RUN = 6
MAX_LIVE_POSTS_PER_CHANNEL = 3
# Leave headroom under Discord's 4096-character embed description limit.
DIGEST_MAX_CHARS = 3900

# Channels with one primary source: other sources' stories routed there are
# recorded in the dedupe state but not posted (logged as PRIMARY-SOURCE SKIP).
COLLECTOR_PRIMARY = {"mlb-transactions": STRUCTURED_SOURCE}

WEBHOOK_ENV = {
    "breaking-news": "LEAGUE_WEBHOOK_BREAKING_NEWS",
    "mlb-news": "LEAGUE_WEBHOOK_MLB_NEWS",
    "injury-report": "LEAGUE_WEBHOOK_INJURY_REPORT",
    "mlb-transactions": "LEAGUE_WEBHOOK_MLB_TRANSACTIONS",
    "prospect-wire": "LEAGUE_WEBHOOK_PROSPECT_WIRE",
    "media": "LEAGUE_WEBHOOK_MEDIA",
}

CHANNEL_LABELS = {
    "breaking-news": "🚨 BREAKING NEWS",
    "mlb-news": "📰 MLB NEWS",
    "injury-report": "🏥 INJURY REPORT",
    "mlb-transactions": "🔄 MLB TRANSACTIONS",
    "prospect-wire": "🌱 PROSPECT WIRE",
    "media": "🎧 PODCASTS",
}

CHANNEL_TITLES = {
    "breaking-news": "Breaking News",
    "mlb-news": "MLB News",
    "injury-report": "Injury Report",
    "mlb-transactions": "MLB Transactions",
    "prospect-wire": "Prospect Wire",
    "media": "New Podcast Episodes",
}

CHANNEL_COLORS = {
    "breaking-news": 0xC73E3A,
    "mlb-news": DEFAULT_COLOR,
    "injury-report": 0xD97706,
    "mlb-transactions": DEFAULT_COLOR,
    "prospect-wire": 0xC68F15,
    "media": DEFAULT_COLOR,
}

WEBHOOK_AVATAR = (
    "https://raw.githubusercontent.com/diseasewheeze/psbl-assets/main/"
    "discord/webhooks/avatar/psbl-webhook-avatar-512.png?v=8bit-1"
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def stable_key(source_id: str, entry: dict) -> str:
    external = entry.get("external_id") or canonical_url(entry.get("link", "")) or entry.get("title", "")
    raw = f"{source_id}|{external}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def empty_state() -> dict:
    return {"version": 1, "initialized": False, "updated_at": "", "seen": []}


def load_state(mode: str) -> tuple[dict, Path]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{mode}.json"
    if not path.exists():
        return empty_state(), path
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("seen"), list):
            raise ValueError("invalid state shape")
        return state, path
    except Exception as exc:
        print(f"WARNING: could not read {path}: {exc}; starting clean")
        return empty_state(), path


def save_state(state: dict, path: Path) -> None:
    state["updated_at"] = iso_now()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_seen_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def needs_rebaseline(state: dict, now: datetime) -> bool:
    """True when a live state hasn't been saved for REBASELINE_AFTER (a pause or long outage)."""
    last = parse_seen_time(str(state.get("updated_at") or ""))
    return bool(state.get("initialized")) and last is not None and now - last > REBASELINE_AFTER


def prune_state(state: dict) -> None:
    cutoff = now_utc() - timedelta(hours=STATE_TTL_HOURS)
    kept = []
    for item in state.get("seen", []):
        seen_at = parse_seen_time(item.get("seen_at", ""))
        if seen_at is None or seen_at >= cutoff:
            kept.append(item)
    state["seen"] = kept[-5000:]


MLB_NICKNAMES = {
    "angels", "astros", "athletics", "a's", "blue", "jays", "braves", "brewers", "cardinals", "cubs",
    "d-backs", "diamondbacks", "dodgers", "giants", "guardians", "mariners", "marlins", "mets",
    "nationals", "nats", "orioles", "padres", "phillies", "pirates", "rangers", "rays", "red", "reds",
    "rockies", "royals", "sox", "tigers", "twins", "white", "yankees",
}
ROLE_WORDS = {
    "pitcher", "starter", "reliever", "closer", "catcher", "infielder", "outfielder", "shortstop",
    "slugger", "lefty", "righty", "ace", "rhp", "lhp", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf",
    "of", "dh", "sp", "rp", "captain", "rookie", "prospect", "star", "veteran",
}
# Words that make another outlet's story news beyond the official injured-list
# move ("10-day IL" then "out six weeks"); such a story is never treated as a repeat.
ESCALATION_TERMS = (
    "exit", "exits", "left", "leaves", "helped off", "carted off", "surgery", "tommy john", "60-day",
    "week", "weeks", "month", "months", "season", "torn", "tear", "fracture", "fractured", "broken",
    "concussion", "indefinitely", "setback", "career", "retire", "suspend",
)


_WEBHOOK_PATH = re.compile(r"(/api/(?:v\d+/)?webhooks/)[^\s'\"?)]+")


def redact(text: object) -> str:
    """Hide webhook ids and tokens that requests puts in its error messages."""
    return _WEBHOOK_PATH.sub(r"\1***", str(text))


def structured_player(prior: dict) -> tuple[str, str] | None:
    """(first name, last name) of the player an official injured-list record named.

    Last names shorter than five letters are skipped as too common.
    """
    words = wire.normalize(str(prior.get("player") or "")).replace(".", "").split()
    words = [w for w in words if w not in ("jr", "sr", "ii", "iii", "iv")]
    if len(words) < 2 or len(words[-1]) < 5:
        return None
    return words[0], words[-1]


def mentions_player(title_norm: str, first: str, last: str) -> bool:
    """True when the title names this player, not just someone sharing his last name.

    The word before the last name must look like his first name (same first
    three letters, so "Sam" matches "Samuel"), or be a team name, a role
    ("pitcher"), a possessive or a colon; or the name opens the title.
    """
    for match in re.finditer(rf"(?<![a-z-]){re.escape(last)}(?![a-z])", title_norm):
        before = title_norm[: match.start()].split()
        prev = before[-1] if before else ""
        if (not prev or prev.endswith((":", "'", "'s")) or prev in ROLE_WORDS
                or prev in MLB_NICKNAMES or prev.startswith(first[:3])):
            return True
    return False


def escalates(title_norm: str, prior_title: str) -> bool:
    return any(wire.term_matches(title_norm, term) and not wire.term_matches(prior_title, term)
               for term in ESCALATION_TERMS)


def story_words(title_norm: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title_norm.replace("'s", "")) if w not in STOPWORDS and len(w) > 1}


def same_story(title_a: str, title_b: str) -> bool:
    a, b = story_words(title_a), story_words(title_b)
    shared = a & b
    return len(shared) >= SAME_STORY_MIN_SHARED and len(shared) / max(1, len(a | b)) >= SAME_STORY_MIN_OVERLAP


def duplicate_reason(candidate: dict, state: dict) -> str | None:
    now = now_utc()
    title_norm = wire.normalize(candidate["title"])
    url = canonical_url(candidate.get("link", ""))
    fp = wire.fingerprint(candidate["title"])

    for prior in reversed(state.get("seen", [])):
        if candidate["key"] == prior.get("key"):
            return "same-source-id"
        if candidate.get("structured"):
            # Official records are told apart by their own ids only: two moves can
            # read alike ("recalled RHP X from ...") and both be real.
            continue
        if candidate.get("dedupe_by_url", True) and url and url == prior.get("url"):
            return "same-url"
        if fp == prior.get("fingerprint"):
            return "same-headline"

        seen_at = parse_seen_time(prior.get("seen_at", ""))
        if seen_at and now - seen_at > timedelta(hours=FUZZY_DEDUPE_WINDOW_HOURS):
            continue
        if candidate["channel"] == "injury-report" and candidate.get("source_id") != STRUCTURED_SOURCE \
                and prior.get("source_id") == STRUCTURED_SOURCE and prior.get("channel") == "injury-report" \
                and seen_at and now - seen_at <= timedelta(hours=SAME_PLAYER_WINDOW_HOURS):
            prior_title = prior.get("title_norm", "")
            player = structured_player(prior)
            if player and mentions_player(title_norm, *player) and not escalates(title_norm, prior_title):
                return f"same-player:{player[1]}"
        if candidate["channel"] in STORY_CHANNELS and prior.get("channel") in STORY_CHANNELS \
                and candidate.get("source_id") != prior.get("source_id") \
                and not (candidate["channel"] == "breaking-news" and prior.get("channel") != "breaking-news") \
                and seen_at and now - seen_at <= timedelta(hours=SAME_STORY_WINDOW_HOURS) \
                and same_story(title_norm, prior.get("title_norm", "")):
            return "same-story"
        if candidate["channel"] == prior.get("channel") and not prior.get("structured"):
            prior_title = prior.get("title_norm", "")
            if prior_title:
                ratio = SequenceMatcher(None, title_norm, prior_title).ratio()
                if ratio >= 0.88:
                    return f"near-duplicate:{ratio:.2f}"
    return None


def remember(candidate: dict, state: dict) -> dict:
    record = {
        "key": candidate["key"],
        "url": canonical_url(candidate.get("link", "")),
        "fingerprint": wire.fingerprint(candidate["title"]),
        "title_norm": wire.normalize(candidate["title"]),
        "channel": candidate["channel"],
        "source_id": candidate["source_id"],
        "tier": candidate["tier"],
        "seen_at": iso_now(),
    }
    if candidate.get("structured"):
        record["structured"] = True
        record["player"] = candidate.get("player", "")
    state.setdefault("seen", []).append(record)
    return record


def baseline_new_sources(candidates: list[dict], cfg: dict, state: dict) -> list[dict]:
    """A source marked `baseline_first: true` posts nothing on its first live run.

    Its current items are only remembered, so adding a feed (for example a
    podcast with years of episodes) never floods a channel with old posts.
    """
    known = set(state.get("known_sources") or [])
    fresh = {str(s.get("id")) for s in cfg.get("sources") or []
             if s.get("baseline_first") and s.get("enabled", True) and str(s.get("id")) not in known}
    if not fresh:
        return candidates
    kept = []
    for candidate in candidates:
        if candidate["source_id"] in fresh:
            remember(candidate, state)
        else:
            kept.append(candidate)
    state["known_sources"] = sorted(known | fresh)
    print(f"NEW SOURCE BASELINE: {', '.join(sorted(fresh))} (current items recorded, nothing posted)")
    return kept


def build_candidate(source: dict, entry: dict) -> dict:
    title = entry.get("title", "(untitled)")
    channel = entry.get("channel") or wire.route(title, source)
    structured = bool(entry.get("structured"))
    return {
        "key": stable_key(source.get("id", "source"), entry),
        "title": title,
        "link": entry.get("link", ""),
        "published": entry.get("published", ""),
        "source_id": source.get("id", ""),
        "source_name": source.get("name", source.get("id", "Unknown")),
        "source_detail": entry.get("source_detail", ""),
        "tier": int(source.get("tier", 9)),
        "channel": channel,
        "discovery_only": bool(source.get("discovery_only", False)),
        "dedupe_by_url": bool(source.get("dedupe_by_url", True)) and not structured,
        "structured": structured,
        "only_if_rostered": bool(entry.get("only_if_rostered")),
        "player": entry.get("player", ""),
        "team": entry.get("team", ""),
        "teams": list(entry.get("teams") or []),
        "players": list(entry.get("players") or []),
        "status": entry.get("status", ""),
        "position": entry.get("position", ""),
        "fantasy_owner": "",
        "owners": [],
        "mentions": [],
    }


def source_candidates(source: dict) -> list[dict]:
    entries = wire.fetch_source(source)
    candidates: list[dict] = []
    max_items = int(source.get("max_items", DEFAULT_MAX_SOURCE_ITEMS))
    for entry in entries:
        candidate = build_candidate(source, entry)
        if wire.should_ignore(candidate["title"], candidate["source_id"], candidate["channel"]):
            continue
        candidates.append(candidate)
        if len(candidates) >= max_items:
            break
    return candidates


def fetch_candidates(config: dict, include_discovery: bool = False) -> list[dict]:
    sources = [
        source
        for source in config.get("sources", [])
        if source.get("enabled", False)
        and (include_discovery or not source.get("discovery_only", False))
    ]
    sources.sort(key=lambda source: (int(source.get("tier", 9)), source.get("name", "")))
    if not sources:
        return []

    by_id: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_SOURCE_WORKERS, len(sources))) as pool:
        future_to_source = {pool.submit(source_candidates, source): source for source in sources}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            source_id = str(source.get("id") or source.get("name") or id(source))
            try:
                by_id[source_id] = future.result()
            except Exception as exc:
                print(f"SOURCE ERROR [{source.get('name')}]: {exc}")
                by_id[source_id] = []

    candidates: list[dict] = []
    for source in sources:
        source_id = str(source.get("id") or source.get("name") or id(source))
        candidates.extend(by_id.get(source_id, []))
    return candidates


def primary_skip(candidate: dict) -> bool:
    """True when another source is the one that posts in this candidate's channel."""
    primary = COLLECTOR_PRIMARY.get(candidate["channel"])
    return bool(primary) and candidate.get("source_id") != primary


def enrich_ownership(candidates: list[dict], config: dict, state: dict) -> None:
    """Tag new stories with the PSBL team that rosters the player.

    Only stories that will actually be posted are looked up, so the Fantrax
    player directory is fetched only when there is something new.
    """
    fantrax_cfg = config.get("fantrax") if isinstance(config.get("fantrax"), dict) else {}
    if not fantrax_cfg.get("roster_enrichment", False):
        return
    fresh = [
        c for c in candidates
        if not c["discovery_only"] and not primary_skip(c)
        and duplicate_reason(c, state) is None
    ]
    if not fresh:
        return
    try:
        league = load_league()
    except Exception as exc:
        print(f"ROSTER TAGS WARNING: could not read league.yaml: {exc}")
        return
    index = roster.load_index(league)
    if index is None:
        return
    tagged = roster.tag_candidates(fresh, index)
    for candidate in fresh:
        candidate["mentions"] = roster.owner_mentions(candidate, league)
    print(f"ROSTER TAGS: tagged {tagged}/{len(fresh)} new stories")


def published_timestamp(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    dt: datetime | None = None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def discord_payload(candidate: dict) -> dict:
    channel = candidate["channel"]
    source_line = candidate["source_name"]
    if candidate.get("source_detail"):
        source_line += f" • {candidate['source_detail']}"

    description = f"**Source:** {source_line}"
    if candidate.get("fantasy_owner"):
        label = "PSBL rosters" if len(candidate.get("owners") or []) > 1 else "PSBL roster"
        description += f"\n**{label}:** {candidate['fantasy_owner']}"

    timestamp = published_timestamp(candidate.get("published", ""))
    if not timestamp and candidate.get("published"):
        description += f"\n**Published:** {candidate['published']}"

    embed = {
        "title": candidate["title"][:256],
        "url": candidate.get("link", "") or None,
        "description": description[:4096],
        "color": CHANNEL_COLORS.get(channel, DEFAULT_COLOR),
        "footer": {"text": f"{CHANNEL_LABELS.get(channel, channel)} • PSBL THE WIRE"},
    }
    if timestamp:
        embed["timestamp"] = timestamp

    return with_mentions({
        "username": "PSBL News Wire",
        "avatar_url": WEBHOOK_AVATAR,
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }, candidate.get("mentions") or [])


def with_mentions(payload: dict, user_ids: list[str]) -> dict:
    """Ping opted-in owners. Only the listed users can be notified."""
    if user_ids:
        payload["content"] = " ".join(f"<@{uid}>" for uid in user_ids)
        payload["allowed_mentions"] = {"parse": [], "users": list(user_ids)}
    return payload


def _digest_link_text(title: str) -> str:
    # Square brackets would break Discord's [text](url) link syntax.
    return title.replace("[", "(").replace("]", ")")


def digest_payload(channel: str, items: list[dict]) -> tuple[dict, int]:
    """Build one roundup embed for stories that exceeded the per-run limits.

    Returns the payload and how many items fit in the embed. Items that do not
    fit are summarized as a count so nothing disappears without a trace.
    """
    count = len(items)
    noun = "update" if count == 1 else "updates"
    heading = CHANNEL_TITLES.get(channel, channel)
    intro = "*More news than usual arrived at once, so the rest is rounded up here.*\n"

    lines: list[str] = []
    used = len(intro)
    shown = 0
    for item in items:
        title = _digest_link_text(item["title"])[:200]
        link = (item.get("link") or "").replace(")", "%29")
        line = f"• [{title}]({link})" if link else f"• {title}"
        line += f" — {item['source_name']}"
        if item.get("fantasy_owner"):
            label = "PSBL rosters" if len(item.get("owners") or []) > 1 else "PSBL roster"
            line += f" · **{label}:** {item['fantasy_owner']}"
        # Reserve room for the "+N more" note.
        if used + len(line) + 1 > DIGEST_MAX_CHARS - 60:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1

    description = intro + "\n".join(lines)
    hidden = count - shown
    if hidden > 0:
        description += f"\n\n*+{hidden} more not shown.*"

    embed = {
        "title": f"{heading} — {count} more {noun}",
        "description": description[:4096],
        "color": CHANNEL_COLORS.get(channel, DEFAULT_COLOR),
        "footer": {"text": f"{CHANNEL_LABELS.get(channel, channel)} • PSBL THE WIRE • ROUNDUP"},
        "timestamp": now_utc().isoformat(),
    }
    payload = {
        "username": "PSBL News Wire",
        "avatar_url": WEBHOOK_AVATAR,
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }
    mentions: list[str] = []
    for item in items[:shown]:
        for uid in item.get("mentions") or []:
            if uid not in mentions:
                mentions.append(uid)
    return with_mentions(payload, mentions), shown


def deliver(candidate: dict) -> bool:
    return post_payload(candidate["channel"], discord_payload(candidate))


def post_payload(channel: str, payload: dict) -> bool:
    env_name = WEBHOOK_ENV.get(channel)
    if not env_name:
        print(f"DELIVERY SKIP: no webhook mapping for {channel}")
        return False
    webhook = os.getenv(env_name, "").strip()
    if not webhook:
        print(f"DELIVERY SKIP: missing GitHub Actions secret {env_name}")
        return False

    for attempt in range(3):
        try:
            response = requests.post(
                webhook,
                params={"wait": "true"},
                json=payload,
                timeout=20,
            )
        except requests.ReadTimeout:
            # Discord received the post but its reply was slow; it has most
            # likely posted. Retrying here (or next run) would post it twice.
            print("DELIVERY UNCERTAIN: Discord did not reply in time; treating the story as posted.")
            return True
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            print(f"DELIVERY ERROR: request failed after retries: {redact(exc)}")
            return False

        if response.status_code in (200, 204):
            return True

        if response.status_code == 429 and attempt < 2:
            delay = 1.0
            try:
                delay = float(response.json().get("retry_after", delay))
            except Exception:
                try:
                    delay = float(response.headers.get("Retry-After", delay))
                except ValueError:
                    pass
            time.sleep(min(max(delay, 0.5), 10.0))
            continue

        if 500 <= response.status_code <= 599 and attempt < 2:
            time.sleep(2 ** attempt)
            continue

        print(f"DELIVERY ERROR {response.status_code}: {redact(response.text[:300])}")
        return False

    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("shadow", "live"), default="shadow")
    parser.add_argument("--reset-state", action="store_true")
    parser.add_argument("--include-discovery", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    state, state_path = load_state(args.mode)
    if args.reset_state:
        state = empty_state()
        print(f"STATE RESET requested for {args.mode}")

    if args.mode == "live" and needs_rebaseline(state, now_utc()):
        print(f"LIVE RE-BASELINE: no Wire run since {state.get('updated_at')}; "
              "current feed items are recorded as seen, not posted.")
        state["initialized"] = False

    prune_state(state)
    candidates = fetch_candidates(cfg, include_discovery=args.include_discovery)
    enrich_ownership(candidates, cfg, state)
    print(
        f"PSBL THE WIRE — mode={args.mode.upper()} candidates={len(candidates)} "
        f"include_discovery={args.include_discovery}"
    )

    if args.mode == "live" and not state.get("initialized", False):
        baseline = 0
        for candidate in candidates:
            if candidate["discovery_only"]:
                continue
            remember(candidate, state)
            baseline += 1
        state["initialized"] = True
        save_state(state, state_path)
        print(f"LIVE BASELINE CREATED: {baseline} current items recorded; 0 Discord messages sent.")
        return 0

    if args.mode == "live":
        candidates = baseline_new_sources(candidates, cfg, state)

    counts = process_candidates(candidates, state, args.mode)

    state["initialized"] = True
    prune_state(state)
    save_state(state, state_path)

    print(
        f"SUMMARY mode={args.mode} posted={counts['posted']} shadowed={counts['shadowed']} "
        f"duplicates={counts['duplicates']} discovery={counts['discovery']} "
        f"primary_skipped={counts['primary_skipped']} unrostered_skipped={counts['unrostered_skipped']} "
        f"digested={counts['digested']} "
        f"digest_posts={counts['digest_posts']} suppressed={counts['suppressed']} "
        f"state={state_path.name}"
    )
    return 0


def process_candidates(candidates: list[dict], state: dict, mode: str) -> dict[str, int]:
    """Route, dedupe and deliver one run's candidates; returns counters.

    In live mode, the first MAX_LIVE_POSTS_PER_CHANNEL stories per channel (and
    MAX_LIVE_POSTS_PER_RUN overall) go out as individual posts. The rest of
    each channel's stories are sent as a single roundup post. Overflow stories
    are remembered immediately so later duplicates in the same run are caught,
    but that memory is rolled back if the roundup cannot be delivered, so
    those stories are retried on the next run instead of being lost.
    """
    counts = {
        "posted": 0, "shadowed": 0, "duplicates": 0, "discovery": 0, "primary_skipped": 0,
        "unrostered_skipped": 0, "digested": 0, "digest_posts": 0, "suppressed": 0,
    }
    posted_by_channel: dict[str, int] = {}
    overflow: dict[str, list[tuple[dict, dict]]] = {}

    # Stories about players on PSBL rosters get the individual posts first;
    # everything else keeps its source-priority order (the sort is stable).
    candidates = sorted(candidates, key=lambda c: 0 if c.get("owners") else 1)

    for candidate in candidates:
        prefix = f"[{candidate['channel']}] {candidate['source_name']}"

        if candidate["discovery_only"]:
            counts["discovery"] += 1
            if mode == "shadow":
                print(f"DISCOVERY {prefix}: {candidate['title']}")
            continue

        reason = duplicate_reason(candidate, state)
        if reason:
            counts["duplicates"] += 1
            continue

        if candidate.get("only_if_rostered") and not candidate.get("owners"):
            remember(candidate, state)  # a minor-league deal or draft-pick signing for nobody on a PSBL roster
            counts["unrostered_skipped"] += 1
            continue

        if mode == "shadow":
            owner_note = f" [PSBL roster: {candidate['fantasy_owner']}]" if candidate.get("fantasy_owner") else ""
            print(f"SHADOW {prefix}: {candidate['title']}{owner_note}")
            remember(candidate, state)
            counts["shadowed"] += 1
            continue

        if primary_skip(candidate):
            print(f"PRIMARY-SOURCE SKIP {prefix}: {candidate['title']}")
            remember(candidate, state)
            counts["primary_skipped"] += 1
            continue

        channel_count = posted_by_channel.get(candidate["channel"], 0)
        if counts["posted"] >= MAX_LIVE_POSTS_PER_RUN or channel_count >= MAX_LIVE_POSTS_PER_CHANNEL:
            print(f"RATE-GUARD ROUNDUP {prefix}: {candidate['title']}")
            record = remember(candidate, state)
            overflow.setdefault(candidate["channel"], []).append((candidate, record))
            continue

        if deliver(candidate):
            print(f"POSTED {prefix}: {candidate['title']}")
            remember(candidate, state)
            counts["posted"] += 1
            posted_by_channel[candidate["channel"]] = channel_count + 1
        else:
            print(f"NOT POSTED {prefix}: {candidate['title']}")

    for channel, entries in overflow.items():
        items = [candidate for candidate, _ in entries]
        payload, shown = digest_payload(channel, items)
        if post_payload(channel, payload):
            counts["digest_posts"] += 1
            counts["digested"] += shown
            print(f"ROUNDUP POSTED [{channel}]: {len(items)} stories ({shown} listed)")
            hidden = len(items) - shown
            if hidden > 0:
                counts["suppressed"] += hidden
                print(f"RATE-GUARD SUPPRESSED [{channel}]: {hidden} stories did not fit in the roundup")
        else:
            records = {id(record) for _, record in entries}
            state["seen"] = [row for row in state.get("seen", []) if id(row) not in records]
            print(f"ROUNDUP NOT POSTED [{channel}]: {len(items)} stories will retry next run")

    return counts


if __name__ == "__main__":
    sys.exit(main())
