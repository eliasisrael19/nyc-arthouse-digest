from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.models import Showing
from src.scrapers.base import Scraper, fetch_with_cache, pick_first

_WEEKDAY_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


class FilmForumScraper(Scraper):
    venue = "Film Forum"
    url = "https://filmforum.org/now_playing"

    def scrape(self) -> list[Showing]:
        html = fetch_with_cache(self.url, cache_key="film_forum", ttl_hours=168)
        return parse_film_forum_showings(html, reference_date=datetime.now().date())


def parse_film_forum_showings(html: str, reference_date: date) -> list[Showing]:
    soup = BeautifulSoup(html, "html.parser")
    tab_dates = _tab_dates_by_id(soup, reference_date)
    if not tab_dates:
        return []

    showings: list[Showing] = []
    for tab_id, tab_date in tab_dates.items():
        tab = soup.select_one(f"div.showtimes-container #{tab_id}")
        if not isinstance(tab, Tag):
            continue

        for row in tab.find_all("p", recursive=False):
            showing_title, showing_url = _extract_title_and_url(row)
            if not showing_title or not showing_url:
                continue

            notes = _extract_notes(row)
            time_nodes = row.find_all("span")
            if not time_nodes:
                showings.append(
                    Showing(
                        title=showing_title,
                        venue=FilmForumScraper.venue,
                        start=None,
                        url=showing_url,
                        notes=notes,
                    )
                )
                continue

            for time_node in time_nodes:
                raw_time = time_node.get_text(" ", strip=True)
                start = _parse_time(raw_time, tab_date)
                if start is None:
                    continue
                showings.append(
                    Showing(
                        title=showing_title,
                        venue=FilmForumScraper.venue,
                        start=start,
                        url=showing_url,
                        notes=notes,
                    )
                )

    return showings


def _tab_dates_by_id(soup: BeautifulSoup, reference_date: date) -> dict[str, date]:
    ordered_ids: list[str] = []
    tab_links = soup.select("li a[href^='#tabs-']")
    for link in tab_links:
        href = (link.get("href") or "").strip()
        if not href.startswith("#tabs-"):
            continue
        ordered_ids.append(href[1:])

    day_labels = [
        next(
            (
                css_class.lower()
                for css_class in tab.parent.get("class", [])
                if css_class.lower() in _WEEKDAY_INDEX
            ),
            None,
        )
        for tab in tab_links
    ]

    if not ordered_ids or len(ordered_ids) != len(day_labels):
        return {}

    first_label = day_labels[0]
    if not first_label:
        return {}

    first_date = _most_recent_weekday(reference_date, _WEEKDAY_INDEX[first_label])
    return {tab_id: first_date + timedelta(days=index) for index, tab_id in enumerate(ordered_ids)}


def _most_recent_weekday(reference_date: date, weekday_index: int) -> date:
    delta = (reference_date.weekday() - weekday_index) % 7
    return reference_date - timedelta(days=delta)


def _extract_title_and_url(row: Tag) -> tuple[str | None, str | None]:
    strong = row.find("strong")
    if not isinstance(strong, Tag):
        return None, None

    anchor = strong.find("a", href=True)
    if not isinstance(anchor, Tag):
        return None, None

    title = pick_first([anchor.get_text(" ", strip=True), strong.get_text(" ", strip=True)])
    href = (anchor.get("href") or "").strip()
    if not title or not href:
        return None, None

    return title, urljoin(FilmForumScraper.url, href)


def _extract_notes(row: Tag) -> str | None:
    parts: list[str] = []
    alert = row.find("span", class_="alert")
    if isinstance(alert, Tag):
        alert_text = alert.get_text(" ", strip=True)
        if alert_text:
            parts.append(alert_text)

    series_link = None
    for anchor in row.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if "/series/" in href:
            series_link = anchor
            break
        if anchor.find_parent("strong") is None:
            series_link = anchor
            break

    if isinstance(series_link, Tag):
        series_text = series_link.get_text(" ", strip=True)
        if series_text:
            parts.append(series_text)

    return " | ".join(parts) if parts else None


def _parse_time(raw_time: str, show_date: date) -> datetime | None:
    normalized = raw_time.strip().lower().replace(".", "")
    formats = ("%I:%M%p", "%I%p", "%H:%M")
    if normalized[-2:] not in {"am", "pm"}:
        normalized = f"{normalized}{_default_meridiem(normalized)}"

    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
            return datetime.combine(show_date, parsed.time())
        except ValueError:
            continue
    return None


def _default_meridiem(normalized: str) -> str:
    try:
        hour = int(normalized.split(":", 1)[0])
    except ValueError:
        return "am"
    if hour == 11:
        return "am"
    return "pm"
