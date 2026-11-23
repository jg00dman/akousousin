# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Choose a recording script: whole passages, chosen for sound coverage.

Units counted:
  * phones (a stressed vowel counts separately from an unstressed one)
  * diphones (adjacent phone pairs, including across word boundaries "#")

Fixed passages are always included; then candidate passages are added greedily,
each time picking the one that fills the most remaining coverage per second
of estimated reading time. Selection stops when every target is met and the
minimum duration is reached, or when nothing useful is left.
"""
import math
from collections import Counter

SYL_PER_SEC = 4.0      # unhurried storytelling pace; recalibrate after a test session
PAUSE_PER_VERSE = 0.7  # seconds
VOWELS = {"a", "e", "i", "o", "u", "y", "ɛ", "ɔ",
          "ai", "ei", "oi", "yi", "au", "eu", "ɛu"}   # Hebrew uses the first five
ACCENTS = {"ˈ", "ˆ"}   # stress / acute, and Greek circumflex
# Count sound pairs with accents kept (Hebrew) or stripped (Greek, where three
# accent states per vowel would multiply the pairs without helping much).
PAIR_ACCENTS = True


def fold(tokens):
    """Merge accent marks into the following vowel."""
    out, accent = [], ""
    for t in tokens:
        if t in ACCENTS:
            accent = t
            continue
        if accent and t in VOWELS:
            out.append(accent + t)
            accent = ""
        else:
            out.append(t)
    return out


def units(phone_words):
    seq = ["#"]
    for w in phone_words:
        seq += fold(w) + ["#"]
    c = Counter(p for p in seq if p != "#")
    pseq = seq if PAIR_ACCENTS else [p.lstrip("".join(ACCENTS)) for p in seq]
    c.update(("D", a, b) for a, b in zip(pseq, pseq[1:]) if not (a == "#" and b == "#"))
    return c


def seconds(phone_words, n_verses):
    syl = sum(1 for w in phone_words for t in w if t in VOWELS)
    return syl / SYL_PER_SEC + n_verses * PAUSE_PER_VERSE


class Passage:
    def __init__(self, pid, label, verses):
        self.pid, self.label, self.verses = pid, label, verses   # verses: [(vid, text, phone_words)]
        allw = [w for _, _, pw in verses for w in pw]
        self.units = units(allw)
        for _, _, pw in verses:   # verse-internal counting is already in units; fine for coverage
            pass
        self.secs = seconds(allw, len(verses))


def targets_for(pool_counts, phone_min, di_min, di_rare_min, rare_cut):
    t = {}
    for u, f in pool_counts.items():
        if isinstance(u, str):
            t[u] = min(phone_min, f)
        else:
            t[u] = min(di_min if f >= rare_cut else di_rare_min, f)
    return t


def select(fixed, candidates, phone_min=60, di_min=4, di_rare_min=1, rare_cut=4,
           min_minutes=0, max_minutes=None):
    pool = Counter()
    for p in fixed + candidates:
        pool.update(p.units)
    tgt = targets_for(pool, phone_min, di_min, di_rare_min, rare_cut)
    have = Counter()
    chosen = []
    for p in fixed:
        chosen.append(p); have.update(p.units)
    remaining = list(candidates)
    log = []

    def deficit():
        return sum(max(0, t - have[u]) for u, t in tgt.items())

    def gain(p):
        g = 0.0
        for u, c in p.units.items():
            need = tgt.get(u, 0) - have[u]
            if need > 0:
                w = 3.0 if isinstance(u, str) else 1.0
                g += w * min(need, c)
        return g

    log.append((sum(p.secs for p in chosen), deficit(), "fixed"))
    while remaining:
        total = sum(p.secs for p in chosen)
        d = deficit()
        if max_minutes is not None and total >= max_minutes * 60:
            break
        if d == 0 and total >= min_minutes * 60:
            break
        if d == 0:
            # coverage met; keep adding for quantity, preferring varied (triphone-rich) text
            best = max(remaining, key=lambda p: len(p.units) / p.secs)
        else:
            best = max(remaining, key=lambda p: getattr(p, "bonus", 1.0) * gain(p) / p.secs)
            if gain(best) == 0:
                break
        remaining.remove(best); chosen.append(best); have.update(best.units)
        log.append((sum(p.secs for p in chosen), deficit(), best.label))
    return chosen, have, tgt, pool, log
