from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.models import Showing
from src.scrapers.base import Scraper, fetch_with_cache, parse_datetime_from_text, pick_first


class AnthologyScraper(Scraper):
    venue = "Anthology Film Archives"
    url = "https://anthologyfilmarchives.org/film_screenings/calendar"

    def scrape(self) -> list[Showing]:
        html = fetch_with_cache(self.url, cache_key="anthology_calendar", ttl_hours=168)
        soup = BeautifulSoup(html, "html.parser")

        showings: list[Showing] = []

        containers = soup.select(".calendar-item, .views-row, article, .event")
        if not containers:
            containers = soup.select("a[href*='film_screenings'], a[href*='screening']")

        seen = set()
        for item in containers:
            anchor = item if getattr(item, "name", None) == "a" else item.find("a", href=True)
            if not anchor:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue
            link = urljoin(self.url, href)
            if link in seen:
                continue

            title = pick_first(
                [
                    item.get("data-title"),
                    anchor.get("title"),
                    anchor.get_text(" ", strip=True),
                    item.get_text(" ", strip=True),
                ]
            )
            if not title:
                continue

            text_blob = item.get_text(" ", strip=True)
            start = parse_datetime_from_text(text_blob)

            notes = None
            lower = text_blob.lower()
            if any(token in lower for token in ["q&a", "35mm", "70mm", "premiere", "restored", "one night"]):
                notes = text_blob[:220]

            showings.append(Showing(title=title, venue=self.venue, start=start, url=link, notes=notes))
            seen.add(link)

        return showings
