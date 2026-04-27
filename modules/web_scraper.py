# -*- coding: utf-8 -*-
"""
modules/web_scraper.py
Lightweight web scraper — extracts readable text from a URL.
No extra dependencies: uses urllib.request + html.parser (stdlib).
"""
import re
import urllib.request
from html.parser import HTMLParser
from core.logger import get_logger

logger = get_logger("web_scraper")

_MAX_CHARS   = 4000
_MAX_BYTES   = 512 * 1024   # 512 KB read limit
_TIMEOUT_SEC = 12
_SKIP_TAGS   = {"script", "style", "head", "nav", "footer",
                "noscript", "svg", "iframe", "aside", "form"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip  = 0
        self._parts: list[str] = []
        self.title  = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "title":
            self._in_title = True
        if t in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "title":
            self._in_title = False
        if t in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        s = data.strip()
        if not s:
            return
        if self._in_title:
            self.title = s
            return
        if self._skip:
            return
        self._parts.append(s)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        return re.sub(r'\s{2,}', ' ', raw).strip()


def scrape_url(url: str, max_chars: int = _MAX_CHARS) -> str:
    """
    Fetch URL and return cleaned readable text.
    Raises Exception on network or parse failure.
    """
    logger.info("Scraping: %s", url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0 Safari/537.36"})

    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        ctype    = resp.headers.get("Content-Type", "")
        raw_data = resp.read(_MAX_BYTES)

    # Detect charset
    encoding = "utf-8"
    if "charset=" in ctype:
        enc = ctype.split("charset=")[-1].strip().split(";")[0].strip()
        if enc:
            encoding = enc

    try:
        html = raw_data.decode(encoding, errors="replace")
    except Exception:
        html = raw_data.decode("utf-8", errors="replace")

    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    parts = []
    if parser.title:
        parts.append("Judul: {}".format(parser.title))
    body = parser.get_text()
    if body:
        parts.append(body)

    result = "\n\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [konten terpotong]"

    return result.strip() or "(Tidak ada teks yang bisa diekstrak dari halaman ini)"
