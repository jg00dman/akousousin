# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Koine Greek (polytonic) -> phonemes, Polis "modified Erasmian" reading.

What the Polis Institute states: an early-Koine pronunciation close to
Erasmian, but φ [f], θ [θ], χ [x]; diphthongs kept distinct; circumflex and
acute accents distinguished. Everything else below is a DRAFT based on
standard Erasmian and must be checked against the freegreek.online videos.
Every choice is in the tables at the top.

Accent marks become tokens before the vowel: "ˈ" (acute or grave) and
"ˆ" (circumflex), so the voice can learn the two contours separately.
"""
import unicodedata

# ---- configurable choices -------------------------------------------------
VOWEL = {"α": "a", "ε": "e", "η": "ɛ", "ι": "i", "ο": "o", "υ": "y", "ω": "ɔ"}
DIPH = {"αι": "ai", "ει": "ei", "οι": "oi", "υι": "yi", "ου": "u",
        "αυ": "au", "ευ": "eu", "ηυ": "ɛu"}
CONS = {"β": ["b"], "γ": ["g"], "δ": ["d"], "ζ": ["z", "d"], "θ": ["θ"],
        "κ": ["k"], "λ": ["l"], "μ": ["m"], "ν": ["n"], "ξ": ["k", "s"],
        "π": ["p"], "ρ": ["r"], "σ": ["s"], "ς": ["s"], "τ": ["t"],
        "φ": ["f"], "χ": ["x"], "ψ": ["p", "s"]}
ZETA = ["z", "d"]          # "zd"; alternatives ["d", "z"] or ["z"]
NASAL_G_BEFORE = set("γκξχ")
ROUGH_H = "h"
ROUGH_RHO = False          # True -> ῥ read as "hr"
IOTA_SUBSCRIPT = ""        # "" silent; "i" to pronounce
GRAVE_AS_ACUTE = True

ACUTE, GRAVE, CIRC = "́", "̀", "͂"
SMOOTH, ROUGH, YPOG, DIAER = "̓", "̔", "ͅ", "̈"
STRESS, CIRCUM = "ˈ", "ˆ"
VOWELS_OUT = set(VOWEL.values()) | set(DIPH.values())


def letters(word):
    """[(base, marks)] in NFD, lower case, non-letters dropped."""
    out = []
    for ch in unicodedata.normalize("NFD", word.lower()):
        if "α" <= ch <= "ω" or ch == "ς":
            out.append([ch, set()])
        elif out and unicodedata.combining(ch):
            out[-1][1].add(ch)
    return out


def word_to_phones(word):
    ls = letters(word)
    out = []
    i = 0
    while i < len(ls):
        b, m = ls[i]
        nxt = ls[i + 1] if i + 1 < len(ls) else None
        if b in VOWEL:
            marks = set(m)
            if nxt and b + nxt[0] in DIPH and DIAER not in nxt[1] and YPOG not in m:
                v = DIPH[b + nxt[0]]
                marks |= nxt[1]
                i += 2
            else:
                v = VOWEL[b]
                i += 1
                if YPOG in m and IOTA_SUBSCRIPT:
                    v = v + IOTA_SUBSCRIPT
            if ROUGH in marks:
                out.append(ROUGH_H)
            if CIRC in marks:
                out.append(CIRCUM)
            elif ACUTE in marks or (GRAVE in marks and GRAVE_AS_ACUTE):
                out.append(STRESS)
            out.append(v)
            continue
        if b == "γ" and nxt and nxt[0] in NASAL_G_BEFORE:
            out.append("ŋ")
        elif b == "ζ":
            out += ZETA
        elif b == "ρ" and ROUGH in m and ROUGH_RHO:
            out += ["h", "r"]
        else:
            out += CONS[b]
        i += 1
    return _move_accents_before_onset(out)


def _move_accents_before_onset(toks):
    """Put the accent token before the syllable's onset consonants, for readability
    and so the stress mark sits at the start of the syllable as in IPA."""
    out = []
    for t in toks:
        if t in (STRESS, CIRCUM):
            k = len(out)
            # one onset consonant (two if a legal cluster like "pr", "st")
            if k and out[k - 1] not in VOWELS_OUT and out[k - 1] != "h":
                k -= 1
                if k and out[k - 1] in ("s", "p", "k", "t", "b", "g", "d", "f", "x", "θ") \
                        and out[k] in ("r", "l", "t", "p", "k", "n", "m", "θ") and \
                        (k - 1 == 0 or out[k - 2] in VOWELS_OUT):
                    k -= 1
            elif k and out[k - 1] == "h":
                k -= 1
            out.insert(k, t)
        else:
            out.append(t)
    return out


def tokens_to_text(toks):
    return "".join(toks)


def clean_text(text):
    """Reader's text: drop SBLGNT apparatus sigla and brackets."""
    drop = {chr(c) for c in range(0x2E00, 0x2E10)} | set("⟦⟧[]")
    return " ".join("".join(ch for ch in text if ch not in drop).split())


def words(text):
    return [w for w in clean_text(text).split() if letters(w)]


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:]:
        print(w, tokens_to_text(word_to_phones(w)))
