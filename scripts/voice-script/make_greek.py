# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Build the Koine Greek recording script from the SBL Greek New Testament.

Candidates are whole short books (preferred: the recording doubles as an
audiobook of that book) and single chapters of longer books. They are chosen
for sound coverage up to a time budget, then single verses are added until
every sound pair occurring at least --rare-min times in the NT is heard
--rare-target times.

    git clone --depth 1 https://github.com/LogosBible/SBLGNT.git
    python3 make_greek.py --sblgnt SBLGNT/data/sblgnt/text
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from greek_g2p import words, word_to_phones, tokens_to_text, clean_text
import select_script
from select_script import Passage, select, units, seconds

select_script.PAIR_ACCENTS = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAMES = {
    "Matt": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John", "Acts": "Acts",
    "Rom": "Romans", "1Cor": "1 Corinthians", "2Cor": "2 Corinthians", "Gal": "Galatians",
    "Eph": "Ephesians", "Phil": "Philippians", "Col": "Colossians",
    "1Thess": "1 Thessalonians", "2Thess": "2 Thessalonians", "1Tim": "1 Timothy",
    "2Tim": "2 Timothy", "Titus": "Titus", "Phlm": "Philemon", "Heb": "Hebrews",
    "Jas": "James", "1Pet": "1 Peter", "2Pet": "2 Peter", "1John": "1 John",
    "2John": "2 John", "3John": "3 John", "Jude": "Jude", "Rev": "Revelation",
}
ORDER = list(NAMES)


def load(text_dir):
    books = {}
    for f in sorted(Path(text_dir).glob("*.txt")):
        ch = defaultdict(list)
        for line in f.read_text(encoding="utf8").splitlines():
            if "\t" not in line:
                continue
            ref, t = line.split("\t", 1)
            b, cv = ref.rsplit(" ", 1)
            c, v = cv.split(":")
            ch[int(c)].append((f"{b}.{c}.{v}", clean_text(t),
                               [word_to_phones(w) for w in words(t)]))
        books[f.stem] = ch
    return books


def ref(vid):
    b, c, v = vid.split(".")
    return f"{NAMES[b]} {c}:{v}"


def fill_rare(chosen, books, have, target, rare_min):
    used = {vid for p in chosen for vid, _, _ in p.verses}
    rem = [(v, units(v[2]), seconds(v[2], 1))
           for b in books for c in books[b] for v in books[b][c] if v[0] not in used]
    pool = Counter()
    for p in chosen:
        pool.update(p.units)
    for _, u, _ in rem:
        pool.update(u)
    need = {u: min(target, f) for u, f in pool.items()
            if not isinstance(u, str) and f >= rare_min}
    h = Counter(have)

    def gain(x):
        return sum(min(c, need[u] - h[u]) for u, c in x[1].items()
                   if u in need and need[u] > h[u])

    picked = []
    while rem:
        best = max(rem, key=lambda x: gain(x) / x[2])
        if gain(best) == 0:
            break
        rem.remove(best)
        picked.append(best[0])
        h.update(best[1])
    groups = defaultdict(list)
    for v in picked:
        b, c, _ = v[0].split(".")
        groups[(ORDER.index(b), int(c), b)].append(v)
    return [Passage(f"X{b}{c}", f"{NAMES[b]} {c} (selected verses)",
                    sorted(groups[k], key=lambda v: int(v[0].split(".")[2])))
            for k in sorted(groups) for b, c in [(k[2], k[1])]]


def sessions(chosen, per_session_min=20):
    extra = [p for p in chosen if p.pid.startswith("X")]
    main = sorted((p for p in chosen if not p.pid.startswith("X")), key=lambda p: p.order)
    out, cur, t = [], [], 0.0
    for p in main:
        if cur and t + p.secs > per_session_min * 60:
            out.append(cur)
            cur, t = [], 0.0
        cur.append(p)
        t += p.secs
    if cur:
        out.append(cur)
    if extra:
        out.append(extra)
    return out


def write_markdown(sess, docs):
    docs.mkdir(parents=True, exist_ok=True)
    header = ("<!--\nSPDX-License-Identifier: GPL-3.0-or-later\n"
              "SPDX-FileCopyrightText: 2026 John Goodman\n-->\n\n")
    for i, s in enumerate(sess, 1):
        mins = round(sum(p.secs for p in s) / 60)
        nv = sum(len(p.verses) for p in s)
        lines = [header, f"# Greek recording script: session {i}\n\n",
                 f"About {mins} minutes of reading, {nv} verses. Read the "
                 "[recording instructions](../RECORDING.md) first.\n\n"]
        if any(p.pid.startswith("X") for p in s):
            lines.append("This session jumps between verses. Read each one as a "
                         "complete sentence on its own, in the same storytelling tone.\n\n")
        for p in s:
            lines.append(f"## {p.label}\n\n")
            for vid, text, _ in p.verses:
                lines.append(f"**{ref(vid)}** {text}\n\n")
        lines.append("---\n\nText: [The Greek New Testament: SBL Edition](https://sblgnt.com) "
                     "(SBLGNT), © 2010 Society of Biblical Literature and Logos Bible "
                     "Software, CC BY 4.0. Apparatus marks removed.\n")
        (docs / f"session-{i}.md").write_text("".join(lines).rstrip() + "\n", encoding="utf8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sblgnt", type=Path, required=True, help="SBLGNT/data/sblgnt/text directory")
    ap.add_argument("--minutes", type=float, default=60, help="time budget for books and chapters")
    ap.add_argument("--max-book-minutes", type=float, default=22, help="longest book offered whole")
    ap.add_argument("--book-bonus", type=float, default=2.0, help="preference for whole books")
    ap.add_argument("--rare-target", type=int, default=2)
    ap.add_argument("--rare-min", type=int, default=3,
                    help="ignore sound pairs occurring fewer times than this in the whole NT")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "greek")
    ap.add_argument("--docs", type=Path, default=ROOT / "docs" / "custom-voices" / "greek")
    a = ap.parse_args()

    books = load(a.sblgnt)
    cands = []
    for b in ORDER:
        ch = books[b]
        whole = Passage(b, NAMES[b], [v for c in sorted(ch) for v in ch[c]])
        if whole.secs <= a.max_book_minutes * 60:
            whole.bonus, whole.order = a.book_bonus, (ORDER.index(b), 0)
            if len(ch) == 1:
                whole.label = NAMES[b]
            cands.append(whole)
        else:
            for c in sorted(ch):
                p = Passage(f"{b}{c}", f"{NAMES[b]} {c}", ch[c])
                p.order = (ORDER.index(b), c)
                cands.append(p)

    chosen, have, tgt, pool, log = select([], cands, max_minutes=a.minutes)
    extra = fill_rare(chosen, books, have, a.rare_target, a.rare_min)
    for p in extra:
        have.update(p.units)
    chosen += extra
    sess = sessions(chosen)

    a.out.mkdir(parents=True, exist_ok=True)
    allpool = Counter()
    for b in books:
        for c in books[b]:
            allpool.update(units([w for v in books[b][c] for w in v[2]]))
    di = [u for u in allpool if not isinstance(u, str)]
    rep = {
        "minutes": round(sum(p.secs for p in chosen) / 60, 1),
        "verses": sum(len(p.verses) for p in chosen),
        "sessions": [{"minutes": round(sum(p.secs for p in s) / 60, 1),
                      "passages": [p.label for p in s]} for s in sess],
        "phones": {p: have[p] for p in sorted(u for u in allpool if isinstance(u, str))},
        "sound_pair_types_in_nt": len(di),
        "sound_pair_types_heard": sum(1 for u in di if have[u] > 0),
        "sound_pair_types_with_3plus_in_nt_heard_2plus":
            f"{sum(1 for u in di if allpool[u] >= 3 and have[u] >= 2)}/{sum(1 for u in di if allpool[u] >= 3)}",
        "pct_of_running_speech_pairs_heard_4plus":
            round(100 * sum(allpool[u] for u in di if have[u] >= 4) / sum(allpool[u] for u in di), 2),
        "curve_minutes_vs_deficit": [(round(s / 60, 1), d, lab) for s, d, lab in log],
    }
    (a.out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf8")
    with open(a.out / "metadata.tsv", "w", encoding="utf8") as f:
        for s in sess:
            for p in s:
                for vid, text, pw in p.verses:
                    f.write(f"{vid}\t{text}\t{' '.join(tokens_to_text(w) for w in pw)}\n")
    write_markdown(sess, a.docs)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("curve_minutes_vs_deficit",)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
