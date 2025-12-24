#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Haodoo EPUB crawler/downloader.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)


DEFAULT_START_URL = "https://www.haodoo.net/?M=hd"
DEFAULT_OUTPUT = "haodoo_books.csv"
DEFAULT_DOWNLOAD_DIR = "~/電子書"
DEFAULT_SLEEP = 2.0
DEFAULT_TIMEOUT = 20
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

CSV_FIELDS = [
    "category",
    "author",
    "title",
    "book_url",
    "download_url",
    "download_name",
    "status",
    "filepath",
    "error",
]


@dataclass
class BookEntry:
    category: str
    author: str
    title: str
    book_url: str
    download_url: str = ""
    download_name: str = ""
    status: str = ""
    filepath: str = ""
    error: str = ""

    def to_row(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "author": self.author,
            "title": self.title,
            "book_url": self.book_url,
            "download_url": self.download_url,
            "download_name": self.download_name,
            "status": self.status,
            "filepath": self.filepath,
            "error": self.error,
        }


class DownloadAsset:
    def __init__(self, url: str, name: str, media_type: str):
        self.url = url
        self.name = name
        self.media_type = media_type


def get_html(session: requests.Session, url: str, timeout: int) -> str:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_author_title(text: str) -> Tuple[str, str]:
    text = normalize_space(text)
    if not text:
        return "", ""

    match = re.match(r"^(?P<author>[^《]+)《(?P<title>[^》]+)》", text)
    if match:
        return match.group("author").strip(), match.group("title").strip()

    for sep in [" / ", "/", "｜", "|", " - ", "—", "－", "·", "　"]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            if len(parts) >= 2:
                return parts[0], " ".join(parts[1:])

    parts = text.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])

    return "", text


def safe_filename(name: str, fallback: str = "unknown") -> str:
    name = normalize_space(name)
    if not name:
        name = fallback
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    return name.strip(". ")


def extract_categories(start_url: str, session: requests.Session, timeout: int) -> List[Dict[str, str]]:
    html = get_html(session, start_url, timeout)
    soup = BeautifulSoup(html, "html.parser")
    categories = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = urljoin(start_url, link["href"])
        parsed = urlparse(href)
        if parsed.netloc and "haodoo.net" not in parsed.netloc:
            continue
        params = parse_qs(parsed.query)
        if params.get("M", [""])[0] != "hd":
            continue
        if "P" not in params:
            continue
        name = normalize_space(link.get_text())
        if not name:
            continue
        key = (name, href)
        if key in seen:
            continue
        seen.add(key)
        categories.append({"category": name, "url": href})
    return categories


def extract_book_links(
    category: str,
    category_url: str,
    session: requests.Session,
    timeout: int,
) -> List[BookEntry]:
    html = get_html(session, category_url, timeout)
    soup = BeautifulSoup(html, "html.parser")
    entries: List[BookEntry] = []
    seen = set()
    for link in soup.find_all("a", href=True):
        text = normalize_space(link.get_text())
        if not text:
            continue
        if any(token in text for token in ["下载", "下載", "回", "返回", "首页", "首頁", "分類", "榜"]):
            continue

        href = urljoin(category_url, link["href"])
        if href == category_url:
            continue
        parsed = urlparse(href)
        if parsed.netloc and "haodoo.net" not in parsed.netloc:
            continue
        params = parse_qs(parsed.query)
        mode = params.get("M", [""])[0].lower()
        if mode not in {"book", "share"}:
            continue

        author, title = split_author_title(text)
        if not title:
            continue
        key = (title, href)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            BookEntry(
                category=category,
                author=author,
                title=title,
                book_url=href,
            )
        )
    return entries


def extract_author_title_from_html(html: str) -> Tuple[str, str]:
    match = re.search(r">\s*([^<]+?)\s*</font>\s*《\s*([^》]+?)\s*》", html)
    if match:
        author = normalize_space(match.group(1))
        title = normalize_space(match.group(2))
        return author, title
    title_match = re.search(r'SetTitle\("([^"]+)"\)', html)
    if title_match:
        raw = normalize_space(title_match.group(1))
        bracket = re.match(r"^(?P<author>[^【]+)【(?P<title>[^】]+)】", raw)
        if bracket:
            return normalize_space(bracket.group("author")), normalize_space(bracket.group("title"))
        angle = re.match(r"^(?P<author>[^《]+)《(?P<title>[^》]+)》", raw)
        if angle:
            return normalize_space(angle.group("author")), normalize_space(angle.group("title"))
    return "", ""


def find_download_assets(
    book_url: str, session: requests.Session, timeout: int
) -> Tuple[List[DownloadAsset], str, str]:
    html = get_html(session, book_url, timeout)
    page_author, page_title = extract_author_title_from_html(html)

    soup = BeautifulSoup(html, "html.parser")
    audio_sources = []
    for source in soup.find_all("source", src=True):
        src = source["src"].strip()
        if src.lower().endswith(".mp3"):
            audio_sources.append(urljoin(book_url, src))

    if audio_sources:
        assets = []
        for src in audio_sources:
            name = os.path.basename(urlparse(src).path)
            assets.append(DownloadAsset(src, name, "mp3"))
        return assets, page_author, page_title

    ve_match = re.search(r"DownloadVEpub\('([^']+)'\)", html)
    e_match = re.search(r"DownloadEpub\('([^']+)'\)", html)
    book_code = ""
    if ve_match:
        book_code = ve_match.group(1)
    elif e_match:
        book_code = e_match.group(1)

    if book_code:
        download_url = f"https://www.haodoo.net/PDB/{book_code[0]}/{book_code[1:]}.epub"
        download_name = f"{book_code}.epub"
        return [DownloadAsset(download_url, download_name, "epub")], page_author, page_title

    candidates = []
    for link in soup.find_all("a", href=True):
        text = normalize_space(link.get_text()).lower()
        href = link["href"]
        if "epub" not in text and "epub" not in href.lower():
            continue
        candidates.append((text, href))

    preferred = None
    fallback = None
    for text, href in candidates:
        if "直式" in text or "竖" in text or "vertical" in text:
            preferred = href
            break
        fallback = href

    final = preferred or fallback
    if not final:
        return [], page_author, page_title
    download_url = urljoin(book_url, final)
    parsed = urlparse(download_url)
    download_name = os.path.basename(parsed.path)
    return [DownloadAsset(download_url, download_name, "epub")], page_author, page_title


def write_csv(path: str, rows: Iterable[Dict[str, str]]) -> None:
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(temp_path, path)


def read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            normalized = {field: row.get(field, "") for field in CSV_FIELDS}
            rows.append(normalized)
    return rows


def download_file(
    session: requests.Session,
    url: str,
    dest_path: str,
    timeout: int,
) -> None:
    resp = session.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    temp_path = dest_path + ".part"
    with open(temp_path, "wb") as handle:
        for chunk in resp.iter_content(chunk_size=1024 * 64):
            if chunk:
                handle.write(chunk)
    os.replace(temp_path, dest_path)


def is_blocked_error(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    return False


def is_blocked_status(status_code: int) -> bool:
    return status_code in {403, 429, 502, 503, 520, 521, 522}


def crawl(
    start_url: str,
    output_csv: str,
    session: requests.Session,
    timeout: int,
    max_categories: int = 0,
    max_books: int = 0,
) -> List[Dict[str, str]]:
    entries: List[BookEntry] = []
    categories = extract_categories(start_url, session, timeout)
    if max_categories and max_categories > 0:
        categories = categories[:max_categories]
    for category in categories:
        category_name = category["category"]
        category_url = category["url"]
        for entry in extract_book_links(category_name, category_url, session, timeout):
            assets, page_author, page_title = find_download_assets(entry.book_url, session, timeout)
            if page_author and not entry.author:
                entry.author = page_author
            if page_title and (not entry.title or entry.title == page_title or "【" in entry.title):
                entry.title = page_title

            if assets:
                for asset in assets:
                    item = BookEntry(
                        category=entry.category,
                        author=entry.author,
                        title=entry.title,
                        book_url=entry.book_url,
                        download_url=asset.url,
                        download_name=asset.name,
                    )
                    entries.append(item)
                    if max_books and max_books > 0 and len(entries) >= max_books:
                        break
            else:
                entries.append(entry)

            if max_books and max_books > 0 and len(entries) >= max_books:
                break
        if max_books and max_books > 0 and len(entries) >= max_books:
            break

    rows = [entry.to_row() for entry in entries]
    write_csv(output_csv, rows)
    return rows


def ensure_download_info(
    row: Dict[str, str],
    session: requests.Session,
    timeout: int,
) -> None:
    if row.get("download_url"):
        return
    book_url = row.get("book_url", "")
    if not book_url:
        row["status"] = "no_book_url"
        return
    assets, page_author, page_title = find_download_assets(book_url, session, timeout)
    if assets:
        row["download_url"] = assets[0].url
        row["download_name"] = assets[0].name
    if page_author and not row.get("author"):
        row["author"] = page_author
    if page_title and (not row.get("title") or "【" in row.get("title", "")):
        row["title"] = page_title


def download_from_csv(
    output_csv: str,
    download_dir: str,
    session: requests.Session,
    timeout: int,
    sleep_seconds: float,
) -> None:
    if not os.path.exists(output_csv):
        raise FileNotFoundError(f"CSV not found: {output_csv}")

    rows = read_csv(output_csv)
    download_root = os.path.expanduser(download_dir)

    for idx, row in enumerate(rows):
        status = row.get("status", "")
        if status == "done":
            if row.get("filepath") and os.path.exists(row["filepath"]):
                continue
            row["status"] = "missing"

        ensure_download_info(row, session, timeout)
        if not row.get("download_url"):
            row["status"] = row.get("status") or "no_epub"
            write_csv(output_csv, rows)
            continue

        category = safe_filename(row.get("category", ""), "UnknownCategory")
        author = safe_filename(row.get("author", ""), "UnknownAuthor")
        title = safe_filename(row.get("title", ""), "UnknownTitle")

        download_name = row.get("download_name", "")
        if download_name.lower().endswith(".mp3"):
            filename = f"{author} - {title} - {download_name}"
        else:
            filename = f"{author} - {title}.epub"
            if not filename.lower().endswith(".epub"):
                filename += ".epub"

        dest_dir = os.path.join(download_root, category, author)
        dest_path = os.path.join(dest_dir, filename)

        try:
            download_file(session, row["download_url"], dest_path, timeout)
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response else 0
            row["status"] = "blocked" if is_blocked_status(status_code) else "error"
            row["error"] = str(exc)
            write_csv(output_csv, rows)
            if is_blocked_status(status_code):
                print(f"Blocked by server at row {idx + 1}, stopping.")
                break
        except Exception as exc:
            row["status"] = "blocked" if is_blocked_error(exc) else "error"
            row["error"] = str(exc)
            write_csv(output_csv, rows)
            if is_blocked_error(exc):
                print(f"Connection issue at row {idx + 1}, stopping.")
                break
        else:
            row["status"] = "done"
            row["filepath"] = dest_path
            row["error"] = ""
            write_csv(output_csv, rows)

        time.sleep(sleep_seconds)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Haodoo EPUB crawler/downloader")
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV output path")
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--max-categories", type=int, default=0, help="Limit categories for crawl (0 = no limit)")
    parser.add_argument("--max-books", type=int, default=0, help="Limit total books for crawl (0 = no limit)")
    parser.add_argument("--crawl", action="store_true", help="Only crawl and build CSV")
    parser.add_argument("--download", action="store_true", help="Only download using CSV")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    do_crawl = args.crawl or (not args.crawl and not args.download)
    do_download = args.download or (not args.crawl and not args.download)

    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent})

    try:
        rows = []
        if do_crawl:
            rows = crawl(
                args.start_url,
                args.output,
                session,
                args.timeout,
                max_categories=args.max_categories,
                max_books=args.max_books,
            )
            print(f"Crawl complete: {len(rows)} items -> {args.output}")
        if do_download:
            download_from_csv(
                args.output,
                args.download_dir,
                session,
                args.timeout,
                args.sleep,
            )
            print("Download stage complete.")
    except KeyboardInterrupt:
        print("Interrupted. Progress saved.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
