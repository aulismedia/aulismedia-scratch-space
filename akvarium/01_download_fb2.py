"""
Step 1: Download FB2 book with Aquarium/BG lyrics (1973-1995) from KulLib.
Output: coollib/akvarium_bg.fb2
"""

import io
import sys
import zipfile
import requests
from pathlib import Path

OUT_DIR = Path(__file__).parent / "coollib"
OUT_FILE = OUT_DIR / "akvarium_bg.fb2"
# coollib.net/flibusta.site mirror — direct static link (no auth needed)
DOWNLOAD_URL = "http://static.flibusta.site/b.fb2/Grebenshchikov_Teksty-pesen-Akvarium-.20562.fb2.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def download():
    print(f"Downloading FB2 zip from flibusta.site...")
    try:
        r = requests.get(DOWNLOAD_URL, headers=HEADERS, timeout=60, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        fb2_names = [n for n in zf.namelist() if n.endswith(".fb2")]
        if not fb2_names:
            print("ZIP содержит:", zf.namelist(), file=sys.stderr)
            sys.exit(1)
        OUT_FILE.write_bytes(zf.read(fb2_names[0]))

    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"Извлечено {size_kb:.1f} KB → {OUT_FILE}")


if __name__ == "__main__":
    download()
