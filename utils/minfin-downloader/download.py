#!/usr/bin/env python3
"""
minfin.gov.ru PDF library downloader
Downloads the PDF and renders each page as a high-resolution image.

Usage:
    python3 download.py <page_url> [--dpi 300] [--fmt png] [--out ./pages]

Examples:
    python3 download.py "https://minfin.gov.ru/ru/ministry/historylib/common/history/general?id_65=300878-..."
    python3 download.py "https://minfin.gov.ru/ru/ministry/historylib/common/history/general?id_65=300878-..." --dpi 400 --fmt jpeg
"""

import argparse
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9",
}

BASE_URL = "https://minfin.gov.ru"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_pdf_url(html: str) -> str | None:
    # iframe with PDF.js viewer
    m = re.search(r'viewer\.html\?file=([^"#&]+)', html)
    if m:
        return BASE_URL + m.group(1)
    # direct download link
    m = re.search(r'href="(/[^"]+\.pdf)"', html)
    if m:
        return BASE_URL + m.group(1)
    return None


def download_pdf(pdf_url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  PDF already downloaded: {dest}")
        return

    print(f"  Downloading PDF from {pdf_url}")
    print(f"  → {dest}")

    req = urllib.request.Request(pdf_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        chunk = 1024 * 256
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = done / total * 100
                    mb = done / 1024 / 1024
                    print(f"\r  {pct:.1f}%  {mb:.1f} MB", end="", flush=True)
    print()


def render_pages(pdf_path: Path, out_dir: Path, dpi: int, fmt: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check if already rendered
    existing = sorted(out_dir.glob(f"page-*.{fmt}"))
    if existing:
        print(f"  Found {len(existing)} existing pages, skipping render.")
        print("  Delete the output directory to re-render.")
        return

    prefix = str(out_dir / "page")

    cmd = ["pdftoppm", f"-r", str(dpi)]
    if fmt == "jpeg":
        cmd += ["-jpeg", "-jpegopt", "quality=95"]
    else:
        cmd += ["-png"]
    cmd += [str(pdf_path), prefix]

    print(f"  Rendering pages at {dpi} DPI ({fmt.upper()})...")
    print(f"  Command: {' '.join(cmd)}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"  ERROR: pdftoppm failed:\n{result.stderr}")
        sys.exit(1)

    pages = sorted(out_dir.glob(f"page-*.{fmt}"))
    print(f"  Done: {len(pages)} pages rendered in {elapsed:.1f}s")
    print(f"  Output: {out_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="minfin.gov.ru book page URL")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI (default: 300)")
    parser.add_argument("--fmt", choices=["png", "jpeg"], default="png", help="Output format (default: png)")
    parser.add_argument("--out", default=None, help="Output directory (default: ./pages_<id>)")
    args = parser.parse_args()

    # Derive a short ID from the URL for naming
    m = re.search(r"id_\d+=([^&]+)", args.url)
    book_id = m.group(1)[:60].rstrip(".") if m else "book"

    out_dir = Path(args.out) if args.out else Path(f"pages_{book_id}")
    pdf_dest = out_dir / "book.pdf"

    print(f"\n=== minfin downloader ===")
    print(f"Book: {book_id}")
    print(f"DPI:  {args.dpi}")
    print(f"Fmt:  {args.fmt.upper()}")
    print(f"Out:  {out_dir}\n")

    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/3] Fetching book page HTML...")
    html = fetch_html(args.url)

    print("[2/3] Locating PDF URL...")
    pdf_url = extract_pdf_url(html)
    if not pdf_url:
        print("  ERROR: could not find PDF URL in page HTML.")
        print("  Try opening the page in a browser and copying the PDF link manually.")
        sys.exit(1)
    print(f"  Found: {pdf_url}")
    download_pdf(pdf_url, pdf_dest)

    print("[3/3] Rendering pages with pdftoppm...")
    render_pages(pdf_dest, out_dir, args.dpi, args.fmt)

    print("\nDone.")


if __name__ == "__main__":
    main()
