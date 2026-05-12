"""
Step 5: Strip chord annotations and guitar diagrams from all lyrics in aquarium_lyrics.json.

Patterns removed:
  1. Guitar diagram lines:  +-+-+-+-+-+  /  | | | 0 | |  /  0 0 0 | II
  2. Chord-name-only lines: C  Cm  G  F# F  E  (also F+c E+h style)
  3. Guitar tab lines:      e|--0==---  Am ---0---1---
  4. Trailing diagram/chord noise on lyric lines:
       "Мой ум сдох     +-+-+-+-+"    (trailing box diagram)
       "Со стрессом в груди,   0 0 | II"  (trailing tab)
       "текст; +-+-+-+-+"  (1 space before diagram)
  5. Leading/trailing chord tokens on lyric lines:
       "D D/G D Hm Долгая память - хуже чем сифилис,  Em(II) A(V)"
  6. Leading credit lines: (Б.Гребенщиков) / (А.Гуницкий)  (названия ...)
"""

import json
import re
from pathlib import Path

IN_OUT = Path(__file__).parent / "aquarium_lyrics.json"

CYR_RE = re.compile(r"[а-яёА-ЯЁ]")

# Diagram line: made entirely of box-drawing/tab symbols, digits, roman numerals, spaces
DIAGRAM_ONLY_RE = re.compile(r"^[\s+\-|0IVXivxoO*\d]+$")

# Guitar tab line: starts with string name + | + tab chars (or embedded anywhere)
GUITAR_TAB_LEADING_RE = re.compile(r"^[eEbBgGdDhHaA]\|[-0\d=|xhp~\s]{4,}")
GUITAR_TAB_EMBEDDED_RE = re.compile(r"[eEbBgGhH]\|[-0\d=|xhp~\s]{4,}")  # e.g. "Intro: e|--0==="

# Standard chord token: Am G C7 F#m D/A Hm G7sus4 Am(V) etc.
# Quality: optional letter-based (m, maj, dim...) + optional digits + optional sus2/sus4 suffix
# Bass note: optional /X or /x with accidental
# Fret position: optional (III), (V) etc. in parens
CHORD_TOKEN = (
    r"[A-H][#b]?"
    r"(?:m(?:aj|in)?|dim|aug|sus|add)?"   # letter quality
    r"\d*"                                  # chord number (7, 9, 11...)
    r"(?:sus[24])?"                         # sus4 / sus2 suffix
    r"(?:[/\\][A-Ha-h][#b]?)?"             # bass note D/F# or D/f#
    r"(?:\([IVX]+\))?"                      # fret position (III), (V)
)
CHORD_LINE_RE = re.compile(rf"^[\s]*({CHORD_TOKEN}\s*){{1,}}\s*$")
# Non-standard chord line: no lowercase, no Cyrillic
NON_STANDARD_CHORD_LINE_RE = re.compile(r"^[\s]*[A-H+#b\d\s/\\]+\s*$")
# Inline tab: |-x-| or |---| or |--0-| pattern present → it's a tab/diagram line
INLINE_TAB_RE = re.compile(r"\|[-oOxX0\d]{1,4}\|")
# Chord followed by long tab: "Am ---0---1-0"
CHORD_THEN_TAB_RE = re.compile(rf"^({CHORD_TOKEN}\s*|\*\d\s*)+[-0\d=|xXoOhp~\s*\-]{{5,}}$")
# Bracket-style guitar tab: e[6(0)],g[6(3)] notation
BRACKET_TAB_RE = re.compile(r"[a-h]\[\d+\(\d+\)\]")
# Comma/arrow chord progressions: "G(III),Em(II),D,Hm" or "D,Hm -> D"
COMMA_CHORD_LINE_RE = re.compile(
    rf"^[\s]*(?:{CHORD_TOKEN}[\s,]*|->[\s]*)+[\s]*$"
)
# Melodic tab with lowercase note letters: "a - - - g f e - - d"
MELODIC_TAB_RE = re.compile(r"(?:[a-h][#b]?\s*[-\s]){3,}")
# Email/attribution header lines
EMAIL_LINE_RE = re.compile(r"(?:^From:)|(?:@[\w.]+\.\w{2,})")
# Structural markers (not lyrics) — checked at start of line OR [Instr] anywhere
STRUCTURAL_RE = re.compile(r"^\s*(?:instr(?:umental)?:|intro:|outro:|Bonus\s+tracks?:)", re.I)
INSTR_TAG_RE = re.compile(r"\[Instr(?:umental)?\]", re.I)
# Lines with chord quality keywords (sus2, add9, etc.) and no Cyrillic → chord line
CHORD_QUALITY_RE = re.compile(r"(?:sus[24]|add\d|aug\d?)(?:\b|$)")

# Trailing noise patterns applied to Cyrillic lines
TRAILING_NOISE_PATS = [
    re.compile(r"\s+[+][-+|0\sIVXivx\d]{2,}$"),       # "; +-+-+-+"  (1+ space before +)
    re.compile(r"\s{2,}[-]{3,}$"),                      # "3 раза -----"
    re.compile(r"\s{3,}[0|][0+|\-\s|IVXivx\d]*$"),     # "text    0 0 | II"
    re.compile(rf"\s{{3,}}({CHORD_TOKEN}\s*){{2,}}$"),   # "text    Am G C"
]

# Leading credit line
CREDIT_LINE_RE = re.compile(r"^\s*(\([^)]+\)\s*)+$")


def strip_trailing_noise(s: str) -> str:
    for pat in TRAILING_NOISE_PATS:
        s = pat.sub("", s)
    return s.rstrip()


def strip_leading_chords(s: str) -> str:
    """Remove chord tokens that appear before the first Cyrillic character."""
    m = re.search(r"[а-яёА-ЯЁ]", s)
    if not m or m.start() == 0:
        return s
    prefix = s[:m.start()]
    if re.match(rf"^[\s]*(?:{CHORD_TOKEN}|\(.*?\)|[+\-|0IVX\d\s/\\])*[\s]*$", prefix):
        return s[m.start():]
    return s


def strip_trailing_chords(s: str) -> str:
    """Remove chord tokens that appear after the last Cyrillic+punctuation."""
    last_cyr = 0
    for m in re.finditer(r"[а-яёА-ЯЁ]", s):
        last_cyr = m.end()
    if not last_cyr:
        return s
    while last_cyr < len(s) and s[last_cyr] in ",.;:!?»)\"'":
        last_cyr += 1
    suffix = s[last_cyr:]
    # Extended diagram chars: include X, x, o, O for fret markers
    if re.match(rf"^[\s]*(?:{CHORD_TOKEN}|\([IVX\d]+\)|[+\-|0XxoO\s/\\])*[\s]*$", suffix):
        return s[:last_cyr]
    return s


def is_diagram_line(s: str) -> bool:
    return bool(DIAGRAM_ONLY_RE.match(s)) and not CYR_RE.search(s)


def is_chord_line(s: str) -> bool:
    if CYR_RE.search(s):
        return False
    if EMAIL_LINE_RE.search(s):
        return True
    if STRUCTURAL_RE.match(s) or INSTR_TAG_RE.search(s):
        return True
    if CHORD_QUALITY_RE.search(s):
        return True
    if BRACKET_TAB_RE.search(s):
        return True
    if GUITAR_TAB_LEADING_RE.match(s):
        return True
    if GUITAR_TAB_EMBEDDED_RE.search(s):
        return True
    if INLINE_TAB_RE.search(s):
        return True
    if CHORD_THEN_TAB_RE.match(s):
        return True
    if MELODIC_TAB_RE.search(s) and not re.search(r"\b\w{5,}\b", s):
        return True
    if CHORD_LINE_RE.match(s):
        return True
    if COMMA_CHORD_LINE_RE.match(s) and ("," in s or "->" in s):
        return True
    if not re.search(r"[a-z]", s) and NON_STANDARD_CHORD_LINE_RE.match(s):
        return True
    # Russian tab notation "F+c E+h": has '+', only 1-3 char lowercase tokens
    if "+" in s:
        lower_words = re.findall(r"[a-z]+", s)
        if lower_words and all(len(w) <= 3 for w in lower_words):
            return True
    return False


def clean_song_lyrics(raw: str) -> str:
    lines = raw.splitlines()
    result: list[str] = []

    for line in lines:
        s = line.strip()

        if not s:
            result.append("")
            continue

        has_cyr = bool(CYR_RE.search(s))

        if has_cyr:
            # Russian lyric line: strip noise from both ends, keep text
            s = strip_trailing_noise(s)
            s = strip_leading_chords(s)
            s = strip_trailing_chords(s)
            result.append(s.strip())
        else:
            # No Cyrillic: strip trailing noise, then classify
            s = strip_trailing_noise(s).strip()
            if not s:
                continue
            if is_diagram_line(s):
                continue
            if is_chord_line(s):
                continue
            if re.search(r"[a-z]", s):
                # Has lowercase → English lyrics
                result.append(s)
            # Otherwise (all-caps, no Cyrillic) → chord/symbol noise, drop

    # Remove leading credit/attribution lines
    while result and CREDIT_LINE_RE.match(result[0] or " "):
        result.pop(0)
    while result and result[0] == "":
        result.pop(0)

    # Collapse consecutive blank lines into one
    final: list[str] = []
    prev_blank = False
    for line in result:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        final.append(line)
        prev_blank = is_blank

    while final and not final[0]:
        final.pop(0)
    while final and not final[-1]:
        final.pop()

    return "\n".join(final)


def main():
    data = json.loads(IN_OUT.read_text())
    total_songs = sum(len(a["songs"]) for a in data)
    print(f"Обрабатываю {len(data)} альбомов, {total_songs} песен...")

    for album in data:
        for song in album["songs"]:
            song["lyrics"] = clean_song_lyrics(song.get("lyrics", ""))

    IN_OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Готово → {IN_OUT}")


if __name__ == "__main__":
    main()
