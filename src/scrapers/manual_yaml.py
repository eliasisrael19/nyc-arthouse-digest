from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dateutil import parser as date_parser
import yaml

from src.models import Showing
from src.scrapers.base import Scraper


class ManualYamlScraper(Scraper):
    venue = "Manual Highlights"

    def __init__(self, yaml_path: str | Path = "data/manual_highlights.yaml") -> None:
        self.yaml_path = Path(yaml_path)

    def scrape(self) -> list[Showing]:
        if not self.yaml_path.exists():
            return []
        with self.yaml_path.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        items = doc.get("items", []) if isinstance(doc, dict) else []

        results: list[Showing] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            venue = str(item.get("venue", "Manual")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue

            start: datetime | None = None
            raw_start = item.get("start")
            if raw_start:
                try:
                    start = date_parser.parse(str(raw_start))
                except (ValueError, TypeError, OverflowError):
                    start = None

            notes = str(item.get("notes", "")).strip() or None
            results.append(Showing(title=title, venue=venue, start=start, url=url, notes=notes))

        return results
