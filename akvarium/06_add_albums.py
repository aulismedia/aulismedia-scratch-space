"""
Step 6: Scrape missing/new albums from bg-aquarium.com (official site, clean lyrics).

Handles:
  - Аквариум+ (2013) — supplements А+ with songs missing from accords.site
  - Странные Новости с Далёкой Звезды (2026) — new album

URL structure:
  /ru/music                 — discography index
  /ru/album/<slug>          — album page with track links
  /ru/lyrics/<slug>         — song page with clean lyrics (no chords)
"""

import json
import time
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://bg-aquarium.com"
DATA_FILE = Path(__file__).parent / "aquarium_lyrics.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
DELAY = 1.0

# Albums to scrape: (album_slug, canonical_name, year)
ALBUMS_TO_SCRAPE = [
    ("strannye-novosti-s-dalyokoy-zvezdy", "Странные Новости с Далёкой Звезды", 2026),
    ("akvarium", "Аквариум+", 2013),
]

# In aquarium_lyrics.json А+ is stored as "А+"
ALBUM_NAME_MAP = {
    "Аквариум+": "А+",
}


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.content, "html.parser")
        except requests.RequestException as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt + 1}: {e}")
                time.sleep(2)
            else:
                print(f"  FAILED {url}: {e}", file=sys.stderr)
                return None


def get_album_songs(album_slug):
    """Return list of (title, lyrics_url) from album page."""
    soup = fetch(f"{BASE}/ru/album/{album_slug}")
    if not soup:
        return []
    songs = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/ru/lyrics/" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or href in seen:
            continue
        seen.add(href)
        full_url = BASE + href if href.startswith("/") else href
        songs.append((title, full_url))
    return songs


FOOTER_WORDS = {
    "Главная", "Афиша", "Новости", "Группа", "Дискография", "Картины",
    "Книги", "Видео", "Иконы", "Аэростат", "Рекомендации", "Магазин",
    "Ссылки", "Контакты", "Russian", "English", "Facebook", "Bandcamp",
    "Twitter", "YouTube", "войти", "зарегистрироваться",
}


def get_song_lyrics(lyrics_url):
    """Extract clean lyrics text from a /ru/lyrics/<slug> page.

    Page structure: div.layout-content > ... > article (contains <p> stanzas)
    """
    soup = fetch(lyrics_url)
    if not soup:
        return ""

    # Lyrics live inside the <article> element in div.layout-content
    content = soup.find("div", class_="layout-content")
    if content:
        article = content.find("article")
    else:
        article = soup.find("article")

    if not article:
        return ""

    # Each stanza is a <p>; lines within stanzas are separated by <br> or newlines
    stanzas = []
    for p in article.find_all("p"):
        stanza = p.get_text(separator="\n").strip()
        # Collapse doubled blank lines within a stanza
        stanza = re.sub(r"\n{2,}", "\n", stanza)
        if stanza:
            stanzas.append(stanza)

    return "\n\n".join(stanzas)


def norm_title(s):
    """Normalize song title for deduplication (strip punctuation, ё→е)."""
    s = s.lower().strip().translate(str.maketrans("ёЁ", "еЕ"))
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    data = json.loads(DATA_FILE.read_text())

    # Build index of existing albums by normalized name
    album_idx = {re.sub(r"\s+", " ", a["album"].lower().strip()): i for i, a in enumerate(data)}

    for album_slug, scraped_name, year in ALBUMS_TO_SCRAPE:
        print(f"\n{'='*60}")
        print(f"Альбом: {scraped_name} ({year})")

        songs = get_album_songs(album_slug)
        if not songs:
            print("  Песни не найдены — пропускаю")
            continue
        print(f"  Найдено {len(songs)} песен на сайте")

        # Canonical name in the dataset
        dataset_name = ALBUM_NAME_MAP.get(scraped_name, scraped_name)
        norm_name = re.sub(r"\s+", " ", dataset_name.lower().strip())

        # Find existing album entry (or create new)
        existing_idx = album_idx.get(norm_name)
        if existing_idx is not None:
            album_entry = data[existing_idx]
            print(f"  Дополняем существующий альбом '{album_entry['album']}' "
                  f"({len(album_entry['songs'])} песен)")
            existing_titles = {norm_title(s["title"]) for s in album_entry["songs"]}
            new_songs = 0
            for title, lyrics_url in songs:
                if norm_title(title) in existing_titles:
                    continue
                print(f"    + {title}")
                time.sleep(DELAY)
                lyrics = get_song_lyrics(lyrics_url)
                album_entry["songs"].append({"title": title, "lyrics": lyrics})
                existing_titles.add(norm_title(title))
                new_songs += 1
            print(f"  Добавлено новых песен: {new_songs}")
        else:
            # New album — scrape all songs
            album_songs = []
            for title, lyrics_url in songs:
                print(f"  → {title}")
                time.sleep(DELAY)
                lyrics = get_song_lyrics(lyrics_url)
                album_songs.append({"title": title, "lyrics": lyrics})

            new_album = {
                "album": dataset_name,
                "year": year,
                "source": "bg_aquarium_site",
                "songs": album_songs,
            }
            data.append(new_album)
            album_idx[norm_name] = len(data) - 1
            print(f"  Добавлен новый альбом: {len(album_songs)} песен")

    # Re-sort by year
    data.sort(key=lambda a: (a.get("year") or 9999, a["album"]))

    total = sum(len(a["songs"]) for a in data)
    print(f"\nИтого: {len(data)} альбомов, {total} песен")
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Сохранено → {DATA_FILE}")


if __name__ == "__main__":
    main()
