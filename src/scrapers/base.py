from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path
import re
from typing import Iterable

from dateutil import parser as date_parser
import requests

from src.models import Showing

CACHE_DIR = Path("cache")


class Scraper(ABC):
    venue: str

    @abstractmethod
    def scrape(self) -> list[Showing]:
        raise NotImplementedError


def fetch_with_cache(
    url: str,
    cache_key: str,
    ttl_hours: int = 168,
    timeout_seconds: int = 20,
) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}_{sha1(url.encode('utf-8')).hexdigest()[:10]}.html"

    if cache_file.exists():
        modified = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if datetime.now() - modified < timedelta(hours=ttl_hours):
            return cache_file.read_text(encoding="utf-8", errors="ignore")

    headers = {
        "User-Agent": (
            "nyc-arthouse-digest/1.0 "
            "(+local use; respectful caching; contact via project README)"
        )
    }
    response = requests.get(url, timeout=timeout_seconds, headers=headers)
    response.raise_for_status()
    html = response.text
    cache_file.write_text(html, encoding="utf-8")
    return html


_DATE_HINT_RE = re.compile(
    r"(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?(?:\s+\d{1,2}:\d{2}\s*(?:am|pm))?)",
    re.IGNORECASE,
)


def parse_datetime_from_text(raw: str) -> datetime | None:
    if not raw:
        return None
    match = _DATE_HINT_RE.search(raw)
    if not match:
        return None
    chunk = match.group(1)
    try:
        dt = date_parser.parse(chunk, fuzzy=True)
        if dt.year == datetime.now().year:
            return dt
        # If date parser inferred an old default year, prefer current year.
        return dt.replace(year=datetime.now().year)
    except (ValueError, TypeError, OverflowError):
        return None


def pick_first(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None
