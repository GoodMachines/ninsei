"""Tall Tales: a bluffing game. Pure functions only; the host's engine drives the clock.

Round flow: the host agent posts an obscure question whose true answer only the host's machine knows.
Every player (people and agents, not the host) posts a fake answer. The host shuffles the truth in
with the fakes and opens voting. People vote. Points: 2 for finding the truth, 1 to a fake's team for
every person it fooled. A team is a person plus their own agent, keyed by the person's pubkey.
"""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from typing import Optional

FAKE_SECONDS = 45
VOTE_SECONDS = 30
REVEAL_SECONDS = 9
ROUNDS = 3
MAX_ROUNDS = 5       # a host can't ask for more; players only fake for rounds 1..MAX_ROUNDS
MAX_OPTIONS = 12     # clients show at most 12 options (A-L), so the host never sends more


# Hyphens, dashes and the minus sign all read as "-" before a number: "−40" is "-40".
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63"), "-")


def norm(text) -> str:
    """Comparable form of an answer. Fakes come from strangers, so any type is accepted.

    Letters, digits and marks of every script count, case and width folded (NFKC + casefold), so
    "ゴジラ" and "Été" are answers too. Punctuation drops out, except a minus sign before a number
    and a decimal point between digits: "-40" is not "40" and "3.14" is not "314". An answer with
    nothing left after that (an emoji, "?!") compares by its own trimmed text instead of vanishing."""
    text = text if isinstance(text, str) else ("" if text is None else str(text))
    text = unicodedata.normalize("NFKC", text[:400]).translate(_DASHES).casefold()   # options show 80 chars
    out = []
    for i, ch in enumerate(text):
        prev = text[i - 1] if i else " "
        nxt = text[i + 1] if i + 1 < len(text) else " "
        if unicodedata.category(ch)[0] in "LNM":
            out.append(ch)
        elif ch.isspace():
            out.append(" ")
        elif ch == "-" and nxt.isdigit() and not prev.isalnum():   # a minus sign, not a hyphen in covid-19
            out.append(ch)
        elif ch == "." and prev.isdigit() and nxt.isdigit():
            out.append(ch)
    kept = re.sub(r"\b(the|a|an)\b", " ", "".join(out))
    kept = re.sub(r"\s+", " ", kept).strip()
    if kept:
        return kept
    bare = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    return re.sub(r"\s+", " ", bare).strip() or re.sub(r"\s+", " ", text).strip()


def build_options(truth: str, fakes: dict[str, str], seed: str,
                  preferred: Optional[set] = None) -> tuple[list[dict], str, dict[str, str], list[str]]:
    """Shuffle truth + fakes into options. Returns (options, truth_id, option_author, lucky_authors).

    `seed` must be secret to the host: option order and ids would otherwise reveal the truth.

    A fake that matches the truth (after normalising) is dropped and its author is "lucky": they
    guessed the real answer while trying to bluff. Duplicate fakes collapse into one option, credited
    to everyone who wrote it, shown in the first writer's spelling. The truth follows the same rule
    when someone matched it: it shows the first lucky writer's spelling, not the host's. Otherwise a
    lucky writer could read the raw event, see their claim token on an option that isn't spelled
    their way, and know it is the truth (and tell a second team to vote for it). At most MAX_OPTIONS options go out and the truth is always one of them.
    When there are more fakes than fit, fakes by `preferred` authors (the players present when the
    round opened) go first, and the rest are picked by a shuffle seeded with the host's secret: never
    by arrival order, which whoever floods the round first would control."""
    truth_n = norm(truth)
    preferred = preferred or set()
    by_text: dict[str, list[str]] = {}
    shown: dict[str, str] = {}
    lucky = []
    lucky_text = ""
    for author, text in fakes.items():
        text = text if isinstance(text, str) else ("" if text is None else str(text))
        n = norm(text)
        if not n:
            continue
        if n == truth_n:
            lucky.append(author)
            lucky_text = lucky_text or text.strip()[:80]
            continue
        by_text.setdefault(n, []).append(author)
        shown.setdefault(n, text.strip()[:80])
    if len(by_text) > MAX_OPTIONS - 1:
        pick = random.Random(seed + ":pick")
        keys = sorted(by_text)
        pick.shuffle(keys)
        keys.sort(key=lambda k: not any(a in preferred for a in by_text[k]))  # stable: preferred first
        by_text = {k: by_text[k] for k in keys[:MAX_OPTIONS - 1]}
    rng = random.Random(seed)
    items = [("truth", lucky_text or truth.strip()[:80], [])] + [(n, shown[n], a) for n, a in by_text.items()]
    rng.shuffle(items)
    options, author_of, truth_id = [], {}, ""
    for i, (key, text, authors) in enumerate(items):
        oid = hashlib.sha256(f"{seed}:{i}".encode()).hexdigest()[:8]
        options.append({"id": oid, "text": text})
        if key == "truth":
            truth_id = oid
        else:
            author_of[oid] = ",".join(sorted(authors))
    return options, truth_id, author_of, lucky


def score_round(truth_id: str, author_of: dict[str, str], votes: dict[str, str],
                team_of: dict[str, str], lucky: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    """votes: voter pk -> option id. team_of: any player pk -> team (person pk).
    Returns (points per team, voters per option)."""
    points: dict[str, int] = {}
    picks: dict[str, list[str]] = {}

    def add(team: Optional[str], n: int):
        if team:
            points[team] = points.get(team, 0) + n

    for voter, oid in votes.items():
        picks.setdefault(oid, []).append(voter)
        if oid == truth_id:
            add(team_of.get(voter, voter), 2)
            continue
        for author in filter(None, author_of.get(oid, "").split(",")):
            if team_of.get(author, author) != team_of.get(voter, voter):
                add(team_of.get(author, author), 1)
    for author in lucky:
        add(team_of.get(author, author), 1)
    return points, picks


def vote_allowed(voter_team: str, oid: str, author_of: dict[str, str], team_of: dict[str, str]) -> bool:
    """You can't vote for your own team's fake."""
    return all(team_of.get(a, a) != voter_team for a in filter(None, author_of.get(oid, "").split(",")))


# ================================================================================================
# Who's the Agent? A second mode on the same rounds, clock and events (tales_*, with mode "agent").
#
# Round flow: the host posts a prompt anyone can answer from their own life. Everyone answers, people
# and agents (the host's own agent too), and the agents try to pass as people. The host shuffles the
# answers, unsigned, and people flag the ones they think an agent wrote. Scoring, per voter and per
# answer from another team: a right call is 1 point to the voter's team; a wrong call is 1 point to
# the answer's team (an agent that passed as a person, or a person who passed as an agent).
# ================================================================================================
MODES = ("tales", "agent")

PROMPTS = [
    "Your first computer or phone, in a few words",
    "The worst haircut you've ever had",
    "A food you hated as a kid and love now",
    "What's in your fridge right now?",
    "The last thing that made you laugh out loud",
    "Your go-to karaoke song",
    "A small thing that ruins your whole day",
    "The most useless thing you own",
    "What you'd do with a free afternoon tomorrow",
    "The first concert you went to",
    "A smell that takes you straight back to childhood",
    "Your most-used emoji and why",
    "The best thing you ate this week",
    "A hobby you picked up and dropped within a month",
    "What your desk looks like right now",
    "The weirdest job you've had",
    "Something you're irrationally scared of",
    "Your comfort TV show",
    "A word you always misspell",
    "The last thing you googled",
    "Your coffee or tea order",
    "A place you'd go back to tomorrow",
    "The worst gift you've ever received",
    "Something you're weirdly good at",
    "How you'd describe your Monday in six words",
    "Your phone's battery percentage right now, and why",
    "The best advice you ignored",
    "A song you can't skip",
    "What you had for breakfast",
    "The app you open first in the morning",
]


def pick_prompts(seed: str, n: int) -> list[str]:
    """n distinct prompts, chosen with the host's secret seed so nobody can predict the next one."""
    rng = random.Random(seed + ":prompts")
    return rng.sample(PROMPTS, max(1, min(n, len(PROMPTS))))


def agent_options(answers: dict[str, str], seed: str,
                  preferred: Optional[set] = None) -> tuple[list[dict], dict[str, str]]:
    """Shuffle every answer into an option. Returns (options, option -> author pk). Unlike Tall Tales,
    equal answers are not merged: who wrote each one is the whole point. At most MAX_OPTIONS go out;
    past that, answers by `preferred` authors (present when the round opened) go first and a shuffle
    seeded with the host's secret picks the rest, never arrival order."""
    preferred = preferred or set()
    items = []
    for author, text in answers.items():
        text = text if isinstance(text, str) else ("" if text is None else str(text))
        text = re.sub(r"\s+", " ", text).strip()[:80]
        if text:
            items.append((author, text))
    items.sort()
    if len(items) > MAX_OPTIONS:
        pick = random.Random(seed + ":pick")
        pick.shuffle(items)
        items.sort(key=lambda x: x[0] not in preferred)  # stable: preferred first
        items = items[:MAX_OPTIONS]
    random.Random(seed).shuffle(items)
    options, author_of = [], {}
    for i, (author, text) in enumerate(items):
        oid = hashlib.sha256(f"{seed}:{i}".encode()).hexdigest()[:8]
        options.append({"id": oid, "text": text})
        author_of[oid] = author
    return options, author_of


def score_agent_round(author_of: dict[str, str], is_agent: dict[str, bool], flags: dict[str, set],
                      team_of: dict[str, str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    """flags: voter pk -> the option ids they think an agent wrote (every other option is a "person"
    call). A voter's own team's answers don't count either way. Returns (points per team, voters who
    flagged each option)."""
    points: dict[str, int] = {}
    flagged: dict[str, list[str]] = {}

    def add(team: Optional[str], n: int = 1):
        if team:
            points[team] = points.get(team, 0) + n

    for voter, picked in flags.items():
        vteam = team_of.get(voter, voter)
        for oid, author in author_of.items():
            ateam = team_of.get(author, author)
            if ateam == vteam:
                continue
            said_agent = oid in picked
            if said_agent:
                flagged.setdefault(oid, []).append(voter)
            add(vteam if said_agent == bool(is_agent.get(oid)) else ateam)
    return points, flagged
