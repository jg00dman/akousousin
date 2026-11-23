# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Build the Hebrew recording script.

All of Jonah and Ruth, then whole psalms chosen for sound coverage up to a time
budget, then single psalm verses until every sound pair is heard RARE_TARGET
times. Writes the reader's script as Markdown (one file per session) plus the
training metadata (verse id, text, phonemes) and a coverage report.

    git clone --depth 1 https://github.com/openscriptures/morphhb.git
    python3 make_hebrew.py --wlc morphhb/wlc
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from hebrew_g2p import word_to_phones, tokens_to_text, strip_cantillation
from select_script import Passage, select, units, seconds
from wlc import verses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK_NAME = {"Jonah": "Jonah", "Ruth": "Ruth", "Ps": "Psalm"}


def load(wlc, book):
    chap = defaultdict(list)
    for vid, ws in verses(wlc / f"{book}.xml"):
        _, c, _ = vid.split(".")
        text = " ".join(strip_cantillation(w) + ("־" if m else "") for w, m in ws)
        text = text.replace("־ ", "־")
        phones = [word_to_phones(w, m) for w, m in ws]
        chap[int(c)].append((vid, text, phones))
    return chap


def fill_rare(chosen, ps, have, target):
    """Add single psalm verses until every sound pair in the pool is heard
    `target` times. Returned as one Passage per psalm, verses in order."""
    used = {vid for p in chosen for vid, _, _ in p.verses}
    rem = [(v, units(v[2]), seconds(v[2], 1)) for c in ps for v in ps[c] if v[0] not in used]
    pool = Counter()
    for p in chosen:
        pool.update(p.units)
    for _, u, _ in rem:
        pool.update(u)
    need = {u: min(target, f) for u, f in pool.items() if not isinstance(u, str)}
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
    by_ps = defaultdict(list)
    for v in picked:
        by_ps[int(v[0].split(".")[1])].append(v)
    return [Passage(f"Xs{c}", f"Psalm {c} (selected verses)",
                    sorted(by_ps[c], key=lambda v: int(v[0].split(".")[2])))
            for c in sorted(by_ps)]


def sessions(chosen, per_session_min=20):
    """Canonical order: Jonah and Ruth, then psalms by number, then the rare-pair verses."""
    extra = [p for p in chosen if p.pid.startswith("Xs")]
    fixed = [p for p in chosen if not p.pid.startswith(("Ps", "Xs"))]

    def key(p):
        a = p.pid[2:]
        return (int(a.split("-")[0]), int(a.split("-")[1]) if "-" in a else 0)

    out, cur, t = [fixed], [], 0.0
    for p in sorted((p for p in chosen if p.pid.startswith("Ps")), key=key):
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


def ref(vid):
    book, c, v = vid.split(".")
    return f"{BOOK_NAME[book]} {c}:{v}"


def write_markdown(sess, docs):
    docs.mkdir(parents=True, exist_ok=True)
    header = ("<!--\nSPDX-License-Identifier: GPL-3.0-or-later\n"
              "SPDX-FileCopyrightText: 2026 John Goodman\n-->\n\n")
    for i, s in enumerate(sess, 1):
        mins = round(sum(p.secs for p in s) / 60)
        nv = sum(len(p.verses) for p in s)
        lines = [header, f"# Hebrew recording script: session {i}\n\n",
                 f"About {mins} minutes of reading, {nv} verses. Read the "
                 "[recording instructions](../RECORDING.md) first.\n\n"]
        if any(p.pid.startswith("Xs") for p in s):
            lines.append("This session jumps between verses. Read each one as a "
                         "complete sentence on its own, in the same storytelling tone.\n\n")
        for p in s:
            lines.append(f"## {p.label}\n\n")
            for vid, text, _ in p.verses:
                lines.append(f"**{ref(vid)}**\n\n<p dir=\"rtl\" lang=\"he\">{text}</p>\n\n")
        (docs / f"session-{i}.md").write_text("".join(lines).rstrip() + "\n", encoding="utf8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wlc", type=Path, required=True, help="morphhb/wlc directory")
    ap.add_argument("--minutes", type=float, default=60, help="time budget for whole passages")
    ap.add_argument("--rare-target", type=int, default=2, help="times each sound pair must be heard")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "hebrew", help="metadata and report")
    ap.add_argument("--docs", type=Path, default=ROOT / "docs" / "custom-voices" / "hebrew",
                    help="where to write the session scripts")
    a = ap.parse_args()

    jonah, ruth, ps = load(a.wlc, "Jonah"), load(a.wlc, "Ruth"), load(a.wlc, "Ps")
    fixed = [Passage("Jonah", "Jonah 1–4", [v for c in sorted(jonah) for v in jonah[c]]),
             Passage("Ruth", "Ruth 1–4", [v for c in sorted(ruth) for v in ruth[c]])]
    cands = []
    for c in sorted(ps):
        vs = ps[c]
        if c == 119:   # 22 stanzas of 8 verses
            cands += [Passage(f"Ps119-{k + 1}", f"Psalm 119:{8 * k + 1}–{8 * k + 8}", vs[8 * k:8 * k + 8])
                      for k in range(22)]
        else:
            cands.append(Passage(f"Ps{c}", f"Psalm {c}", vs))

    chosen, have, tgt, pool, log = select(fixed, cands, max_minutes=a.minutes)
    extra = fill_rare(chosen, ps, have, a.rare_target)
    for p in extra:
        have.update(p.units)
    chosen += extra
    sess = sessions(chosen)

    a.out.mkdir(parents=True, exist_ok=True)
    di = [u for u in tgt if not isinstance(u, str)]
    rep = {
        "minutes": round(sum(p.secs for p in chosen) / 60, 1),
        "verses": sum(len(p.verses) for p in chosen),
        "sessions": [{"minutes": round(sum(p.secs for p in s) / 60, 1),
                      "passages": [p.label for p in s]} for s in sess],
        "phones": {p: have[p] for p in sorted(u for u in tgt if isinstance(u, str))},
        "sound_pair_types": len(di),
        "sound_pair_types_heard": sum(1 for u in di if have[u] > 0),
        "pct_of_running_speech_pairs_heard_4plus":
            round(100 * sum(pool[u] for u in di if have[u] >= 4) / sum(pool[u] for u in di), 2),
        "curve_minutes_vs_deficit": [(round(s / 60, 1), d, lab) for s, d, lab in log],
    }
    (a.out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf8")
    with open(a.out / "metadata.tsv", "w", encoding="utf8") as f:
        for s in sess:
            for p in s:
                for vid, text, pw in p.verses:
                    f.write(f"{vid}\t{text}\t{' '.join(tokens_to_text(w) for w in pw)}\n")
    write_markdown(sess, a.docs)
    print(json.dumps({k: rep[k] for k in ("minutes", "verses", "sessions", "sound_pair_types",
                                          "sound_pair_types_heard",
                                          "pct_of_running_speech_pairs_heard_4plus")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
