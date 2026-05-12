"""
Step 2: Parse downloaded FB2 file into structured JSON (albums + songs + lyrics).
Covers the period 1973-1995.

The FB2 has a flat structure: one big <section> with all <p> elements.
Album markers: lines matching  * ALBUM NAME * (p)YEAR
Song markers:  lines starting with  - Song Title
Lyrics:        <p> lines that follow a song marker until the next marker.

Input:  coollib/akvarium_bg.fb2
Output: coollib/coollib_albums.json
"""

import json
import re
import sys
from pathlib import Path
from lxml import etree

IN_FILE = Path(__file__).parent / "coollib" / "akvarium_bg.fb2"
OUT_FILE = Path(__file__).parent / "coollib" / "coollib_albums.json"

NS = "http://www.gribuser.ru/xml/fictionbook/2.0"

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Album header: * NAME * (p)YEAR  or  * NAME * YEAR
ALBUM_RE = re.compile(r"^\*\s+(.+?)\s+\*.*?(\d{4})", re.IGNORECASE)
# Song title: starts with  -  (dash + space)
SONG_RE = re.compile(r"^-\s+(.+)$")

CHORD_LINE_RE = re.compile(
    r"^\s*([A-H][#b]?(?:m|maj|min|dim|aug|sus|add|7|9)?\d*"
    r"(?:[/\\][A-H][#b]?)?\s*){2,}\s*$"
)


def tag(name):
    return f"{{{NS}}}{name}"


def text_of(el):
    return "".join(el.itertext()).strip()


def clean_lyrics(lines):
    result = []
    for line in lines:
        if CHORD_LINE_RE.match(line) and line.strip():
            continue
        result.append(line)
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def parse_fb2(path):
    raw = path.read_bytes()
    parser = etree.XMLParser(encoding="windows-1251", recover=True)
    root = etree.fromstring(raw, parser=parser)

    body = root.find(tag("body"))
    if body is None:
        print("ERROR: no <body> found", file=sys.stderr)
        sys.exit(1)

    # Collect all <p> text lines from the flat section
    lines = []
    for p in body.iter(tag("p")):
        lines.append(text_of(p))

    # State machine: walk lines and emit albums / songs
    albums = []
    current_album = None
    current_song = None
    current_lyrics = []
    in_songs_area = False  # True once we've passed the index preamble

    def flush_song():
        if current_song and current_album is not None:
            lyrics = "\n".join(clean_lyrics(current_lyrics))
            current_album["songs"].append({"title": current_song, "lyrics": lyrics})

    for line in lines:
        album_m = ALBUM_RE.match(line)
        song_m = SONG_RE.match(line)

        if album_m:
            flush_song()
            current_song = None
            current_lyrics = []

            album_name = album_m.group(1).strip().title()
            year = int(album_m.group(2))

            current_album = {"album": album_name, "year": year, "source": "coollib_fb2", "songs": []}
            albums.append(current_album)
            in_songs_area = True

        elif song_m and in_songs_area:
            flush_song()
            current_song = song_m.group(1).strip()
            # Strip parenthetical author notes like "(А.Гуницкий)"
            current_song = re.sub(r"\s*\(.*?\)\s*$", "", current_song).strip()
            current_lyrics = []

        elif current_song is not None and in_songs_area:
            # Regular lyric line (or blank separator)
            current_lyrics.append(line)

    flush_song()
    return albums


def main():
    if not IN_FILE.exists():
        print(f"FB2 не найден: {IN_FILE}\nЗапустите сначала 01_download_fb2.py", file=sys.stderr)
        sys.exit(1)

    print(f"Парсинг {IN_FILE} ...")
    albums = parse_fb2(IN_FILE)

    for a in albums:
        print(f"  [{a['year']}] {a['album']}: {len(a['songs'])} песен")

    total_songs = sum(len(a["songs"]) for a in albums)
    print(f"\nИтого: {len(albums)} альбомов, {total_songs} песен")

    OUT_FILE.write_text(json.dumps(albums, ensure_ascii=False, indent=2))
    print(f"Сохранено → {OUT_FILE}")


if __name__ == "__main__":
    main()
