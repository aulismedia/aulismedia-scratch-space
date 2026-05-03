#!/usr/bin/env python3
"""
Downloader for prlib.ru item 460802
Assembles tiles from IIPImage server at max zoom level 4 (true 1718x2631 resolution)
"""

import json
import math
import os
import time
from io import BytesIO

import requests
from PIL import Image

MANIFEST_URL = (
    "https://content.prlib.ru/metadata/public"
    "/75338AC2-181E-4BBE-AFC0-D8A2738263A9/5382727"
    "/75338AC2-181E-4BBE-AFC0-D8A2738263A9.json"
)
IIP_SERVER = "https://content.prlib.ru/fcgi-bin/iipsrv.fcgi"
IMAGE_DIR = "/var/data/scans/public/75338AC2-181E-4BBE-AFC0-D8A2738263A9/5382727"
TILE_SIZE = 256
ZOOM_LEVEL = 4
DELAY_SECONDS = 5
OUTPUT_DIR = "/Users/sergeymishenev/Desktop/Media Labs/книги/Берх, Василий Николаевич часть 2"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.prlib.ru/item/460802",
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_manifest():
    resp = session.get(MANIFEST_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_tile(fif_path, zoom, tile_num):
    url = (
        f"{IIP_SERVER}"
        f"?FIF={fif_path}"
        f"&JTL={zoom},{tile_num}"
    )
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content))


def assemble_page(fif_path, width, height):
    cols = math.ceil(width / TILE_SIZE)
    rows = math.ceil(height / TILE_SIZE)
    canvas = Image.new("RGB", (width, height))

    for row in range(rows):
        for col in range(cols):
            tile_num = row * cols + col
            tile = download_tile(fif_path, ZOOM_LEVEL, tile_num)
            x = col * TILE_SIZE
            y = row * TILE_SIZE
            canvas.paste(tile, (x, y))

    return canvas


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Загрузка манифеста...")
    manifest = fetch_manifest()
    pages = manifest["pgs"]
    total = len(pages)
    print(f"Всего страниц: {total}")

    existing = [
        f for f in os.listdir(OUTPUT_DIR)
        if f.startswith("page_") and f.endswith(".jpg")
    ]
    print(f"Уже загружено: {len(existing)}\n")

    for i, page in enumerate(pages):
        page_num = i + 1
        out_path = os.path.join(OUTPUT_DIR, f"page_{page_num:04d}.jpg")

        if os.path.exists(out_path):
            print(f"[{page_num}/{total}] Пропуск (уже есть): {out_path}")
            continue

        filename = page["f"]
        dims = page["d"][ZOOM_LEVEL]
        width = int(dims["w"])
        height = int(dims["h"])
        fif_path = f"{IMAGE_DIR}/{filename}"

        cols = math.ceil(width / TILE_SIZE)
        rows = math.ceil(height / TILE_SIZE)
        tile_count = cols * rows

        print(
            f"[{page_num}/{total}] {filename}  "
            f"{width}x{height}  {tile_count} тайлов"
        )

        try:
            img = assemble_page(fif_path, width, height)
            img.save(out_path, "JPEG", quality=95)
            print(f"  -> Сохранено: {out_path}")
        except Exception as e:
            print(f"  ОШИБКА на странице {page_num}: {e}")
            # Save partial progress marker so we can retry
            continue

        if page_num < total:
            print(f"  Пауза {DELAY_SECONDS} сек...")
            time.sleep(DELAY_SECONDS)

    print("\nГотово!")


if __name__ == "__main__":
    main()
