from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.models import Showing
from src.scrapers.base import Scraper, fetch_with_cache, pick_first


class MetrographScraper(Scraper):
    venue = "Metrograph"
    url = "https://metrograph.com/nyc/"

    def scrape(self) -> list[Showing]:
        html = fetch_with_cache(self.url, cache_key="metrograph_nyc", ttl_hours=168)
        soup = BeautifulSoup(html, "html.parser")

        showings: list[Showing] = []
        cards = soup.select("div.calendar-list-day div.item.film-thumbnail")
        if not cards:
            cards = soup.select("a[href*='/film/'], a[href*='/event/']")

        seen_urls: set[str] = set()
        for card in cards:
            anchor = card.find("h4 a.title", href=True) if getattr(card, "name", None) != "a" else card
            if not anchor:
                anchor = card if getattr(card, "name", None) == "a" else card.find("a", href=True)
            if not anchor:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue
            link = urljoin(self.url, href)
            if link in seen_urls:
                continue

            title = pick_first(
                [
                    anchor.get_text(" ", strip=True),
                    card.get("data-title"),
                    card.get_text(" ", strip=True),
                ]
            )
            if not title:
                continue

            start = _extract_start_datetime(card)

            notes_blob = pick_first(
                [
                    _safe_text(card.select_one(".film-description")),
                    _safe_text(card.select_one(".film-metadata")),
                ]
            )
            notes = None
            lower = (notes_blob or "").lower()
            if any(token in lower for token in ["q&a", "35mm", "70mm", "premiere", "restored", "one night"]):
                notes = (notes_blob or "")[:220] or None

            showings.append(Showing(title=title, venue=self.venue, start=start, url=link, notes=notes))
            seen_urls.add(link)

        return showings


def _safe_text(node: object) -> str | None:
    if not node:
        return None
    try:
        text = node.get_text(" ", strip=True)  # type: ignore[attr-defined]
    except Exception:
        return None
    return text or None


def _extract_start_datetime(card: object) -> datetime | None:
    if not card:
        return None
    parent = card
    day_node = getattr(parent, "find_parent", lambda *_args, **_kwargs: None)("div", class_="calendar-list-day")
    if not day_node:
        return None

    day_id = day_node.get("id", "")
    if not day_id.startswith("calendar-list-day-"):
        return None

    date_part = day_id.replace("calendar-list-day-", "")
    try:
        date_obj = datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return None

    time_link = card.select_one(".showtimes a")
    if not time_link:
        return date_obj

    raw_time = time_link.get_text(" ", strip=True).lower().replace(" ", "")
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            parsed = datetime.strptime(raw_time, fmt)
            return date_obj.replace(hour=parsed.hour, minute=parsed.minute)
        except ValueError:
            continue
    return date_obj
