# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Biblical Hebrew (pointed, with cantillation) -> phonemes, Sephardic reading.

Pronunciation choices (match freehebrew.online / Aleph with Beth, Sephardic):
  ח ħ, ע ʕ (pharyngeal); ר r; ו v; ת/תּ t, ד/דּ d, ג/גּ g;
  ב/בּ v/b, כ/כּ x/k, פ/פּ f/p distinguished.
  Five vowels a e i o u; tsere = segol = e; qamets qatan = o; vocal shewa = e.
  No gemination for dagesh forte. Stress from the cantillation accents.
  Divine name: configurable (DIVINE_NAME below).

Every choice lives in the tables / constants near the top so it can be
changed and the script re-selected without touching the logic.
"""
import unicodedata

# ---- configurable choices -------------------------------------------------
DIVINE_NAME = ["a", "d", "o", "ˈ", "n", "a", "j"]  # reading for יהוה (alt: jahve)
ALEPH_HIATUS = "ʔ"     # aleph between vowels mid-word ("" to drop)

CONS = {  # letter: (plain, with dagesh)
    "א": ("ʔ", "ʔ"), "ב": ("v", "b"), "ג": ("g", "g"), "ד": ("d", "d"),
    "ה": ("h", "h"), "ו": ("v", "v"), "ז": ("z", "z"), "ח": ("ħ", "ħ"),
    "ט": ("t", "t"), "י": ("j", "j"), "כ": ("x", "k"), "ך": ("x", "k"),
    "ל": ("l", "l"), "מ": ("m", "m"), "ם": ("m", "m"), "נ": ("n", "n"),
    "ן": ("n", "n"), "ס": ("s", "s"), "ע": ("ʕ", "ʕ"), "פ": ("f", "p"),
    "ף": ("f", "p"), "צ": ("ts", "ts"), "ץ": ("ts", "ts"), "ק": ("k", "k"),
    "ר": ("r", "r"), "ת": ("t", "t"),
}
SHIN, SIN = "ʃ", "s"

SHEVA, HSEG, HPAT, HQAM = "\u05b0", "\u05b1", "\u05b2", "\u05b3"
HIRIQ, TSERE, SEGOL, PATAH, QAMETS = "\u05b4", "\u05b5", "\u05b6", "\u05b7", "\u05b8"
HOLAM, HOLAM_V, QUBUTS, DAGESH, METEG = "\u05b9", "\u05ba", "\u05bb", "\u05bc", "\u05bd"
RAFE, SHIN_DOT, SIN_DOT, QQATAN = "\u05bf", "\u05c1", "\u05c2", "\u05c7"
FULL_V = {HIRIQ: "i", TSERE: "e", SEGOL: "e", PATAH: "a", QAMETS: "a",
          HOLAM: "o", HOLAM_V: "o", QUBUTS: "u", QQATAN: "o"}
HATAF = {HSEG: "e", HPAT: "a", HQAM: "o"}
BGDKPT = set("בגדכךפףת")
GUTT_FURTIVE = set("חע")
ACCENTS = {chr(c) for c in range(0x0591, 0x05AF + 1)}
# Accents written on the first/last letter regardless of stress.
NON_STRESS_ACCENTS = {"\u0592", "\u0599", "\u05a9", "\u05ae",   # postpositive
                      "\u05a0", "\u059a", "\u05ad", "\u059d"}   # prepositive
PASHTA = chr(0x0599)
VOWELS = {"a", "e", "i", "o", "u"}


def clusters(word):
    """Split into [base_letter, set_of_marks, list_of_vowels_in_order]."""
    out = []
    for ch in unicodedata.normalize("NFD", word):
        if "א" <= ch <= "ת":
            out.append([ch, set(), []])
        elif out and ("\u0591" <= ch <= "\u05c7"):
            out[-1][1].add(ch)
            if ch in FULL_V or ch in HATAF or ch == SHEVA:
                out[-1][2].append(ch)
    return out


def _stress_letter(cl):
    """Index of letter carrying the stress accent, or None (-> final)."""
    idx = [i for i, c in enumerate(cl) if c[1] & (ACCENTS - NON_STRESS_ACCENTS)]
    if idx:
        return idx[-1]   # secondary accents (e.g. tsinnorit) come first
    pas = [i for i, c in enumerate(cl) if PASHTA in c[1]]
    if len(pas) >= 2:
        return pas[0]
    return None


def word_to_phones(word, next_is_maqaf=False):
    cl = clusters(word)
    if not cl:
        return []
    bare = "".join(c[0] for c in cl)
    if bare == "יהוה" or bare.endswith("יהוה") and len(bare) <= 6:
        pre = [t for t in word_to_phones("".join(_rebuild(c) for c in cl[:-4])) if t != "ˈ"]
        name = list(DIVINE_NAME)
        if pre and pre[-1] in VOWELS and name[0] in VOWELS:
            name = name[1:]            # לַיהוָה -> la-donaj
        elif pre and pre[-1] == "e" and name[0] in VOWELS:
            pre = pre[:-1]             # וַיהוה / לְ -> l-adonaj
        return pre + name

    n = len(cl)
    # ---- 1. classify each letter: consonant, mater (vowel letter) or silent
    role = ["C"] * n          # C consonant, M mater carrying vowel, S silent
    mvowel = [None] * n       # vowel produced by a mater
    for i, (b, m, v) in enumerate(cl):
        prev_has_v = i > 0 and bool(cl[i - 1][2]) and cl[i - 1][2][-1] != SHEVA
        if b == "ו" and not v:
            if DAGESH in m and (i == 0 or not cl[i - 1][2] or role[i - 1] != "C"):
                role[i], mvowel[i] = "M", "u"          # shureq
            elif HOLAM in m or HOLAM_V in m:
                if i > 0 and not cl[i - 1][2]:
                    role[i], mvowel[i] = "M", "o"      # holam male
        elif b == "ו" and (HOLAM in m) and i > 0 and not cl[i - 1][2] and len(v) == 1:
            role[i], mvowel[i] = "M", "o"
        elif b == "י" and not v and DAGESH not in m and i > 0:
            pv = cl[i - 1][2][-1] if cl[i - 1][2] else None
            nxt_vav_final = (i == n - 2 and cl[i + 1][0] == "ו" and not cl[i + 1][2]
                             and DAGESH not in cl[i + 1][1])
            if pv in (HIRIQ, TSERE, SEGOL) or (pv == QAMETS and nxt_vav_final):
                role[i] = "S"
        elif b == "ה" and i == n - 1 and DAGESH not in m and not v:
            role[i] = "S"
        elif b == "א" and not v:
            role[i] = "S"
    # holam written on the letter before a silent aleph etc. is fine as-is.

    # ---- 2. stress position (letter index of stressed nucleus)
    nuclei = [i for i in range(n) if role[i] == "M" or
              (role[i] == "C" and any(x != SHEVA for x in cl[i][2]))]
    sl = _stress_letter(cl)
    if sl is None or not nuclei:
        stress = nuclei[-1] if nuclei else None
        # furtive patah never stressed
        if stress is not None and stress == n - 1 and cl[-1][0] in GUTT_FURTIVE \
                and cl[-1][2] == [PATAH] and len(nuclei) > 1:
            stress = nuclei[-2]
    else:
        cand = [k for k in nuclei if k >= sl]
        stress = sl if sl in nuclei else (cand[0] if cand else nuclei[-1])
        # accent on consonant before a mater -> the mater is the nucleus
        if sl not in nuclei and sl + 1 < n and role[sl + 1] == "M":
            stress = sl + 1
    if next_is_maqaf and _stress_letter(cl) is None and len(nuclei) <= 1:
        stress = None   # short proclitic before maqaf: unstressed

    # ---- 3. shewa vocal / silent
    def has_full_v(i):
        return any(x != SHEVA for x in cl[i][2]) or role[i] == "M"

    vocal = [False] * n
    for i, (b, m, v) in enumerate(cl):
        if SHEVA not in v or role[i] != "C":
            continue
        last = all(role[k] == "S" for k in range(i + 1, n))
        if last and i != 0:
            continue
        if i == 0 or (i == 1 and role[0] == "M" and cl[0][0] == "ו"):
            vocal[i] = True; continue
        p = i - 1
        while p > 0 and role[p] == "S":
            p -= 1
        forte = DAGESH in m and (b not in BGDKPT or has_full_v(p)) and b not in "ה"
        if forte:
            vocal[i] = True
        elif SHEVA in cl[p][2] and not has_full_v(p) and not vocal[p]:
            vocal[i] = True                       # second of two shewas
        elif i + 1 < n and cl[i + 1][0] == b:      # identical consonants
            vocal[i] = True
        elif METEG in cl[p][1] and (role[p] == "M" or (set(cl[p][2]) & {QAMETS, TSERE, HOLAM})
                                    or (p + 1 < n and role[p + 1] == "S")):
            vocal[i] = True                       # ga'ya after long vowel

    # ---- 4. qamets qatan
    def closed_after(i):
        j = i + 1
        while j < n and role[j] == "S":
            j += 1
        if j >= n:
            return True
        bj, mj, vj = cl[j]
        if SHEVA in vj and not vocal[j] and role[j] == "C":
            return True
        if HQAM in vj:
            return True
        if DAGESH in mj and bj not in "ו" and role[j] == "C":
            return True
        return False

    qatan = set()
    for i, (b, m, v) in enumerate(cl):
        if QAMETS in v and i != stress and METEG not in m and closed_after(i):
            if i == n - 1 or all(role[k] == "S" for k in range(i + 1, n)):
                continue
            if i == n - 2 and not next_is_maqaf and stress is not None:
                continue
            qatan.add(i)
    if bare in ("כל",) and next_is_maqaf:
        qatan.add(0)

    # ---- 5. emit
    out = []
    for i, (b, m, v) in enumerate(cl):
        st = (i == stress)
        if role[i] == "S":
            continue
        if role[i] == "M":
            _emit_vowel(out, mvowel[i], st)
            continue
        if b == "ש":
            c = SIN if SIN_DOT in m else SHIN
        else:
            c = CONS[b][1] if (DAGESH in m and b in BGDKPT and RAFE not in m) else CONS[b][0]
        furtive = (i == n - 1 and PATAH in v and (b in GUTT_FURTIVE or (b == "ה" and DAGESH in m))
                   and i > 0 and (has_full_v(i - 1) or role[i - 1] == "M"))
        if furtive:
            out.append("a"); out.append(c); continue
        if b == "א":
            if out and out[-1] in VOWELS and ALEPH_HIATUS:
                out.append(ALEPH_HIATUS)
        else:
            out.append(c)
        vowels = [x for x in v]
        if PATAH in vowels and HIRIQ in vowels:      # יְרוּשָׁלִַם -> -laim
            vowels = [PATAH, HIRIQ]
            if st:
                _emit_vowel(out, "a", True); out.append("i"); continue
        for k, x in enumerate(vowels):
            if x == SHEVA:
                if vocal[i]:
                    out.append("e")
            elif x in HATAF:
                out.append(HATAF[x])
            else:
                q = "o" if (x == QAMETS and i in qatan) else FULL_V[x]
                _emit_vowel(out, q, st and k == len(vowels) - 1)
        # final yod after a/o/u as glide is handled as consonant j (role C)
    return out


def _emit_vowel(out, vw, stressed):
    if stressed:
        # stress mark goes before the onset consonant if there is one
        if out and out[-1] not in VOWELS and out[-1] != "ˈ":
            out.insert(len(out) - 1, "ˈ")
        else:
            out.append("ˈ")
    out.append(vw)


def _rebuild(c):
    return c[0] + "".join(sorted(c[1]))


def tokens_to_text(toks):
    """Join phone tokens into a readable IPA-ish string."""
    s = "".join(toks)
    return s.replace("ts", "t͡s")


def strip_cantillation(word):
    """Text for the reader: keep vowels, dagesh, shin/sin dots, maqaf; drop accents & meteg."""
    w = unicodedata.normalize("NFD", word)
    w = "".join(ch for ch in w if ch not in ACCENTS and ch != METEG)
    return unicodedata.normalize("NFC", w)


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:]:
        print(w, tokens_to_text(word_to_phones(w)))
