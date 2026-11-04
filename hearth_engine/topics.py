"""Cheap, local topic detection: no model call until people clearly keep coming back to something.

A term (word or two-word phrase) becomes a candidate when at least two different people have used it
at least three times in total within the window. Agents' own messages don't count.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

STOP = set("""a about above after again against all am an and any are aren't as at be because been before being
below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few
for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself
his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor
not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll
they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll
you're you've your yours yourself yourselves yeah yes yep nope ok okay lol haha like just really also maybe think know
get got gonna wanna kind sort thing things stuff make made one two lot bit right good great cool nice thanks thank
hey hi hello actually probably pretty still even much way want need see look said say says time day today now well
something anything everything someone anyone everyone people agent agents room hearth""".split())

WORD = re.compile(r"[a-z][a-z0-9'+-]{2,}")


def terms(text: str) -> set[str]:
    words = [w.strip("'-") for w in WORD.findall((text or "").lower())]
    words = [w for w in words if w and w not in STOP and not w.startswith("@")]
    out = set(words)
    out |= {f"{a} {b}" for a, b in zip(words, words[1:])}
    return out


class TopicTracker:
    def __init__(self, window_s: int = 900, min_mentions: int = 3, min_people: int = 2):
        self.window_s, self.min_mentions, self.min_people = window_s, min_mentions, min_people
        self._hits: dict[str, deque] = defaultdict(deque)  # term -> deque[(ts, author)]
        self.offered: set[str] = set()

    def add(self, author: str, text: str, ts: float | None = None) -> list[str]:
        """Record a human message; return newly hot terms, best first (phrases before single words)."""
        ts = ts or time.time()
        hot = []
        for t in terms(text):
            dq = self._hits[t]
            dq.append((ts, author))
            while dq and dq[0][0] < ts - self.window_s:
                dq.popleft()
            if t in self.offered:
                continue
            if len(dq) >= self.min_mentions and len({a for _, a in dq}) >= self.min_people:
                hot.append(t)
        hot.sort(key=lambda t: (-(" " in t), -len(self._hits[t]), t))
        # a phrase subsumes its words
        chosen = []
        for t in hot:
            if not any(t in c.split(" ") for c in chosen):
                chosen.append(t)
        return chosen

    def mark_offered(self, term: str) -> None:
        self.offered.add(term)
        for part in term.split(" "):
            self.offered.add(part)
