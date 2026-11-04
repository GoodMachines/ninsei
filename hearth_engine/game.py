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
from typing import Optional

FAKE_SECONDS = 45
VOTE_SECONDS = 30
REVEAL_SECONDS = 9
ROUNDS = 3


def norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", "", (text or "").lower())
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_options(truth: str, fakes: dict[str, str], seed: str) -> tuple[list[dict], str, dict[str, str], list[str]]:
    """Shuffle truth + fakes into options. Returns (options, truth_id, option_author, lucky_authors).

    A fake that matches the truth (after normalising) is dropped and its author is "lucky": they
    guessed the real answer while trying to bluff. Duplicate fakes collapse into one option, credited
    to everyone who wrote it."""
    truth_n = norm(truth)
    by_text: dict[str, list[str]] = {}
    shown: dict[str, str] = {}
    lucky = []
    for author, text in fakes.items():
        n = norm(text)
        if not n:
            continue
        if n == truth_n:
            lucky.append(author)
            continue
        by_text.setdefault(n, []).append(author)
        shown.setdefault(n, text.strip()[:80])
    rng = random.Random(seed)
    items = [("truth", truth.strip()[:80], [])] + [(n, shown[n], a) for n, a in by_text.items()]
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
