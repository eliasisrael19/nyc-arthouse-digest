from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable

_TITLE_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_TITLE_SPACE_RE = re.compile(r"\s+")
_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+")


@dataclass(slots=True)
class Showing:
    title: str
    venue: str
    start: datetime | None
    url: str
    notes: str | None = None
    summary: str | None = None

    @property
    def normalized_title(self) -> str:
        return normalize_title(self.title)


def normalize_title(title: str) -> str:
    cleaned = title.strip().lower()
    cleaned = _TITLE_PUNCT_RE.sub(" ", cleaned)
    cleaned = _TITLE_SPACE_RE.sub(" ", cleaned).strip()
    cleaned = _LEADING_ARTICLE_RE.sub("", cleaned)
    return cleaned


def dedupe_showings(showings: Iterable[Showing]) -> list[Showing]:
    seen: dict[tuple[str, str, str], Showing] = {}
    for showing in showings:
        start_key = showing.start.isoformat() if showing.start else ""
        key = (showing.normalized_title, showing.venue.strip().lower(), start_key)
        existing = seen.get(key)
        if not existing:
            seen[key] = showing
            continue

        # Merge notes if we encountered duplicate records from the same source.
        if showing.notes and (not existing.notes or showing.notes not in existing.notes):
            merged = [p for p in [existing.notes, showing.notes] if p]
            existing.notes = " | ".join(merged)
        if showing.summary and not existing.summary:
            existing.summary = showing.summary

    return sorted(
        seen.values(),
        key=lambda s: (s.venue.lower(), s.start or datetime.max, s.normalized_title),
    )


def unique_titles_across_venues(showings: Iterable[Showing]) -> dict[str, set[str]]:
    by_title: dict[str, set[str]] = {}
    for showing in showings:
        by_title.setdefault(showing.normalized_title, set()).add(showing.venue)
    return by_title
