"""
Step 4: Deduplicate and merge albums from both sources into aquarium_lyrics.json.

Rules:
- "Разные песни" → "Песни Вне Альбомов" (placed last)
- Albums with 0 songs are dropped
- Albums with normalized-name similarity >= 0.82 are merged into one
- Songs merged by normalized title; keep the version with more lyrics on conflict
- Canonical album name: prefer accords_site, strip year suffix
- Canonical year: prefer accords_site year
"""

import json
import re
import difflib
from pathlib import Path

BASE = Path(__file__).parent
COOLLIB_FILE = BASE / "coollib" / "coollib_albums.json"
ACCORDS_FILE = BASE / "accords" / "accords_albums.json"
OUTPUT = BASE / "aquarium_lyrics.json"

SIMILARITY_THRESHOLD = 0.82

# ё/Ё → е/Е, common Latin homoglyphs that appear in OCR/FB2 data
YO_MAP = str.maketrans("ёЁ", "еЕ")


def norm_album(s: str) -> str:
    """Normalize album name for similarity comparison."""
    s = s.translate(YO_MAP).lower()
    s = re.sub(r"\s*\(\d{4}\)\s*", " ", s)   # remove (YEAR)
    s = re.sub(r"\.?\s*том\s+\d+\b\.?", "", s)  # remove "Том N"
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_song(s: str) -> str:
    """Normalize song title for deduplication."""
    s = s.translate(YO_MAP).lower().strip()
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)     # remove parentheticals
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def album_sim(a: str, b: str) -> float:
    na, nb = norm_album(a), norm_album(b)
    if na == nb:
        return 1.0

    # If both names contain a bare 2-digit number (year-in-name like "Боб - 87")
    # and those numbers differ → definitely different albums, don't merge
    ya = re.search(r"\b(\d{2})\b", na)
    yb = re.search(r"\b(\d{2})\b", nb)
    if ya and yb and ya.group(1) != yb.group(1):
        return 0.0

    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if short:
        # Prefix match (e.g. "Черная Роза" vs full album title): strong bonus
        if long_.startswith(short):
            return min(1.0, len(short) / len(long_) + 0.35)
        # Substring match: weaker
        if short in long_:
            return len(short) / len(long_)

    return difflib.SequenceMatcher(None, na, nb).ratio()


def clean_name(name: str) -> str:
    """Strip trailing ' (YEAR)' and cleanup punctuation."""
    name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip()
    name = re.sub(r"[\.\s]+$", "", name).strip()
    return name


def merge_songs(song_groups: list[list[dict]]) -> list[dict]:
    """Union of song lists from multiple albums, deduped by normalized title."""
    seen: dict[str, dict] = {}
    for songs in song_groups:
        for song in songs:
            key = norm_song(song["title"])
            if key not in seen:
                seen[key] = song
            else:
                # Prefer the version with more (non-empty) lyrics
                if len(song.get("lyrics", "")) > len(seen[key].get("lyrics", "")):
                    seen[key] = song
    return list(seen.values())


def pick_canonical(cluster: list[dict]) -> dict:
    """
    From a cluster of duplicate albums, build a single merged album:
    - name: prefer accords_site, strip year suffix
    - year: prefer accords_site year, then any non-None
    - songs: union of all
    - sources: set of all source strings
    """
    accords = [a for a in cluster if a.get("source") == "accords_site"]

    # Canonical name
    if accords:
        name = clean_name(accords[0]["album"])
    else:
        name = clean_name(cluster[0]["album"])

    # Canonical year: prefer accords, then any
    year = None
    for a in accords:
        if a.get("year"):
            year = a["year"]
            break
    if year is None:
        for a in cluster:
            if a.get("year"):
                year = a["year"]
                break

    # Merge songs
    songs = merge_songs([a.get("songs", []) for a in cluster])

    sources = sorted({a.get("source", "?") for a in cluster})
    source = sources[0] if len(sources) == 1 else "merged"

    return {"album": name, "year": year, "source": source, "songs": songs}


def cluster_albums(albums: list[dict]) -> list[list[dict]]:
    """
    Greedy clustering: each new album is added to the first existing cluster
    whose representative has similarity >= SIMILARITY_THRESHOLD.
    """
    clusters: list[list[dict]] = []
    reps: list[str] = []       # representative album name per cluster

    for album in albums:
        name = album["album"]
        best_idx = -1
        best_sim = 0.0

        for i, rep in enumerate(reps):
            s = album_sim(name, rep)
            if s >= SIMILARITY_THRESHOLD and s > best_sim:
                best_sim = s
                best_idx = i

        if best_idx >= 0:
            clusters[best_idx].append(album)
        else:
            clusters.append([album])
            reps.append(name)

    return clusters


def main():
    all_albums: list[dict] = []

    if ACCORDS_FILE.exists():
        data = json.loads(ACCORDS_FILE.read_text())
        print(f"accords.site: {len(data)} альбомов")
        all_albums.extend(data)
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {ACCORDS_FILE} не найден")

    if COOLLIB_FILE.exists():
        data = json.loads(COOLLIB_FILE.read_text())
        print(f"coollib FB2:  {len(data)} альбомов")
        all_albums.extend(data)
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {COOLLIB_FILE} не найден")

    if not all_albums:
        print("Нет данных. Запустите шаги 01–03.")
        return

    # Separate "Разные песни" out before clustering
    misc = [a for a in all_albums if norm_album(a["album"]) == "разные песни"]
    rest = [a for a in all_albums if norm_album(a["album"]) != "разные песни"]

    print(f"\nКластеризация {len(rest)} альбомов...")
    clusters = cluster_albums(rest)
    print(f"Получено {len(clusters)} кластеров")

    # Build merged list
    merged: list[dict] = []
    dropped = 0
    for cluster in clusters:
        album = pick_canonical(cluster)
        if not album["songs"]:
            dropped += 1
            continue
        merged.append(album)

    print(f"Удалено пустых (0 песен): {dropped}")

    # Drop bootleg/unofficial recordings: albums that exist ONLY in coollib FB2
    # (official albums always matched accords_site and got source="merged" or "accords_site")
    before = len(merged)
    merged = [a for a in merged if a.get("source") != "coollib_fb2"]
    print(f"Удалено бутлегов (только FB2): {before - len(merged)}")

    # Drop albums that are not Aquarium/BG releases
    EXCLUDED_ALBUMS = {
        "в объятиях джинсни иннокентий",  # рок-опера Ольги Першиной, не альбом Аквариума
    }
    before = len(merged)
    merged = [a for a in merged if norm_album(a["album"]) not in EXCLUDED_ALBUMS]
    print(f"Удалено сторонних релизов: {before - len(merged)}")

    # Add misc songs as "Песни Вне Альбомов" (if any)
    if misc:
        misc_merged = pick_canonical(misc)
        misc_merged["album"] = "Песни Вне Альбомов"
        misc_merged["year"] = None
        if misc_merged["songs"]:
            merged.append(misc_merged)

    # Sort: by year (None last), then album name
    merged.sort(key=lambda a: (a.get("year") or 9999, a["album"]))

    # Summary table
    total_songs = sum(len(a["songs"]) for a in merged)
    print(f"\n{'Год':>6}  {'Альбом':<50}  {'Песен':>6}  Ист.")
    print("-" * 85)
    for a in merged:
        year = str(a.get("year") or "????")
        songs = len(a.get("songs", []))
        print(f"  {year:>4}  {a['album']:<50}  {songs:>5}  {a['source']}")
    print(f"\nВсего: {len(merged)} альбомов, {total_songs} песен")

    OUTPUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    print(f"Сохранено → {OUTPUT}")


if __name__ == "__main__":
    main()
