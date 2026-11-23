# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Read Westminster Leningrad Codex verses from the OSHB (morphhb) OSIS XML.

Uses the qere reading where the text has a ketiv/qere pair (that is what a
reader says aloud). Returns, per verse, a list of (word, followed_by_maqaf).
"""
import xml.etree.ElementTree as ET

NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"


def verses(path):
    root = ET.parse(path).getroot()
    for v in root.iter(NS + "verse"):
        words = []
        for el in v.iter():
            tag = el.tag.replace(NS, "")
            if tag == "w":
                if el.get("type") == "x-ketiv":
                    continue
                words.append([(el.text or "").replace("/", ""), False])
            elif tag == "seg" and el.get("type") == "x-maqqef" and words:
                words[-1][1] = True
        yield v.get("osisID"), [tuple(w) for w in words if w[0]]
