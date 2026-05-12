"""
Step 3: Scrape accords.site for the full Aquarium/BG discography (1973-2022).

Site structure (HTTP only, SSL expired):
  Index page:  http://accords.site/txt.php?s=042
    → links to album pages: ?s=042&d=<id>
  Album page:  http://accords.site/txt.php?s=042&d=<id>
    → all songs on same page in <div id="v01">, <div id="v02">, ...
    → each div: <b><u>Title</u></b><br/><pre>lyrics with chords</pre>

Output:
  accords/album_index.json          — list of albums with metadata
  accords/<id>_<slug>.json          — one JSON file per album
  accords/accords_albums.json       — all albums merged into one list
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://accords.site"
INDEX_URL = "http://accords.site/txt.php?s=042"
OUT_DIR = Path(__file__).parent / "accords"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
DELAY = 1.0  # seconds between requests

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
SONG_DIV_RE = re.compile(r"^v\d+$")

CHORD_LINE_RE = re.compile(
    r"^\s*([A-H][#b]?(?:m|maj|min|dim|aug|sus|add|7|9|11|13)?\d*"
    r"(?:[/\\][A-H][#b]?)?\s*){1,8}\s*$"
)


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            try:
                text = r.content.decode("utf-8")
            except UnicodeDecodeError:
                text = r.content.decode(r.apparent_encoding or "cp1251", errors="replace")
            return BeautifulSoup(text, "html.parser")
        except requests.RequestException as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt + 1}/{retries}: {e}")
                time.sleep(2)
            else:
                print(f"  FAILED {url}: {e}", file=sys.stderr)
                return None


def absolute_url(href):
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def get_album_list():
    print(f"Загружаю список альбомов с {INDEX_URL} ...")
    soup = fetch(INDEX_URL)
    if soup is None:
        return []

    albums = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Album links: have d= but NOT a fragment (#), not jpg, not mailto
        if (
            "s=042" in href
            and re.search(r"[?&]d=\d+", href)
            and "#" not in href
            and ".jpg" not in href
        ):
            d_match = re.search(r"d=(\d+)", href)
            if not d_match:
                continue
            album_id = d_match.group(1)
            if album_id in seen:
                continue
            seen.add(album_id)

            name = a.get_text(strip=True)
            if not name:
                continue

            year = None
            m = YEAR_RE.search(name)
            if m:
                year = int(m.group())

            albums.append({
                "id": album_id,
                "name": name,
                "year": year,
                "url": absolute_url(href),
            })

    print(f"Найдено {len(albums)} альбомов")
    return albums


def clean_lyrics(raw_text):
    """Strip chord lines and normalize whitespace."""
    lines = raw_text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped and CHORD_LINE_RE.match(stripped):
            continue
        cleaned.append(stripped)

    # Collapse consecutive blank lines into one
    result = []
    prev_blank = False
    for line in cleaned:
        is_blank = not line
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    while result and not result[0]:
        result.pop(0)
    while result and not result[-1]:
        result.pop()

    return "\n".join(result)


def scrape_album_page(soup):
    """Extract all songs from an album page. Returns list of {title, lyrics}."""
    songs = []

    for div in soup.find_all("div", id=SONG_DIV_RE):
        # Title: first <b><u> inside the div
        title_el = div.find("b")
        title = title_el.get_text(strip=True) if title_el else "Без названия"

        # Lyrics: in <pre>
        pre = div.find("pre")
        raw = pre.get_text() if pre else ""
        lyrics = clean_lyrics(raw)

        songs.append({"title": title, "lyrics": lyrics})

    return songs


def safe_filename(album_id, album_name):
    slug = re.sub(r"[^\w\s-]", "", album_name).strip()
    slug = re.sub(r"\s+", "_", slug)[:50]
    return f"{album_id}_{slug}.json"


def scrape():
    albums_meta = get_album_list()
    if not albums_meta:
        print("Не удалось получить список альбомов.", file=sys.stderr)
        sys.exit(1)

    (OUT_DIR / "album_index.json").write_text(
        json.dumps(albums_meta, ensure_ascii=False, indent=2)
    )

    all_albums = []

    for i, meta in enumerate(albums_meta, 1):
        name = meta["name"]
        album_id = meta["id"]
        year = meta["year"]
        print(f"[{i}/{len(albums_meta)}] [{year or '????'}] {name}")

        time.sleep(DELAY)
        soup = fetch(meta["url"])
        if soup is None:
            songs = []
        else:
            songs = scrape_album_page(soup)

        print(f"  {len(songs)} песен")

        album_data = {
            "album": name,
            "year": year,
            "source": "accords_site",
            "songs": songs,
        }
        all_albums.append(album_data)

        fname = safe_filename(album_id, name)
        (OUT_DIR / fname).write_text(json.dumps(album_data, ensure_ascii=False, indent=2))

    out = OUT_DIR / "accords_albums.json"
    out.write_text(json.dumps(all_albums, ensure_ascii=False, indent=2))

    total = sum(len(a["songs"]) for a in all_albums)
    print(f"\nГотово: {len(all_albums)} альбомов, {total} песен → {out}")


if __name__ == "__main__":
    scrape()
