from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import html as html_lib
import json
import re

from bs4 import BeautifulSoup
import requests

from src.agents.openai_extractor import OpenAIExtractor
from src.models import Showing
from src.scrapers.base import fetch_with_cache


@dataclass(slots=True)
class AgentVenueConfig:
    name: str
    url: str
    cache_key: str
    source_mode: str = "html"
    country_id: str | None = None
    cinema_slug: str | None = None


class AgentVenueScraper:
    def __init__(self, extractor: OpenAIExtractor, config: AgentVenueConfig) -> None:
        self.extractor = extractor
        self.config = config

    def scrape(self) -> list[Showing]:
        source_blob, direct_showings = self._build_source_blob()
        if direct_showings:
            return direct_showings
        week_label = _week_label(datetime.now())
        return self.extractor.extract_showings(
            venue=self.config.name,
            source_url=self.config.url,
            html=source_blob,
            week_label=week_label,
            cache_key=f"agent_{self.config.cache_key}",
        )

    def _build_source_blob(self) -> tuple[str, list[Showing] | None]:
        html = fetch_with_cache(self.config.url, cache_key=self.config.cache_key, ttl_hours=168)
        if self.config.source_mode == "filmlinc_embedded":
            direct = _parse_filmlinc_showings_from_html(html, venue=self.config.name)
            if direct:
                return html, direct

        if self.config.source_mode != "reading_api":
            return html, None

        if not self.config.country_id or not self.config.cinema_slug:
            return html, None

        api_payload = _fetch_reading_now_playing(
            country_id=self.config.country_id,
            cinema_slug=self.config.cinema_slug,
        )
        if not api_payload:
            return html, None

        return (
            "\n\n".join(
                [
                    f"URL: {self.config.url}",
                    "HTML:",
                    html,
                    "READING_API_NOW_PLAYING_JSON:",
                    json.dumps(api_payload, ensure_ascii=True),
                ]
            ),
            None,
        )


def _week_label(now: datetime) -> str:
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday:%Y-%m-%d} to {sunday:%Y-%m-%d}"


def _fetch_reading_now_playing(country_id: str, cinema_slug: str) -> dict[str, object] | None:
    base = "https://production-api.readingcinemas.com"
    settings_url = f"{base}/settings/{country_id}"
    try:
        settings = requests.get(settings_url, timeout=25).json()
        token = settings["data"]["settings"]["token"]
    except Exception:
        return None


def _parse_filmlinc_showings_from_html(html: str, venue: str) -> list[Showing]:
    # The homepage embeds escaped JSON with nested day-based showtimes.
    week = _current_week()
    landing_by_season_id = _filmlinc_landing_url_by_season_id(html)
    summary_by_season_id = _filmlinc_summary_by_season_id(html)
    object_pattern = re.compile(
        r'\{\\"id\\":\\"[^\\"]+\\",.{0,26000}?'
        r'\\"description\\":\\"[^\\"]+\\",.{0,16000}?'
        r'\\"dateTimeET\\":\\"[^\\"]+\\"',
        re.DOTALL,
    )
    showings: list[Showing] = []
    seen: set[tuple[str, str, str]] = set()

    for m in object_pattern.finditer(html):
        block = m.group(0)
        tickets_url = _decode_escaped_json_text(_extract_escaped_field(block, "ticketsUrl") or "").strip()
        season_id = _decode_escaped_json_text(_extract_escaped_field(block, "productionSeasonId") or "").strip()
        description = _decode_escaped_json_text(_extract_escaped_field(block, "description") or "").strip()
        date_time = _decode_escaped_json_text(_extract_escaped_field(block, "dateTimeET") or "").strip()
        screening_venue = _decode_escaped_json_text(_extract_escaped_field(block, "venue") or "").strip()
        open_captions = _extract_bool_field(block, "openCaptions")

        if not tickets_url or not description or not date_time:
            continue

        try:
            dt = datetime.fromisoformat(date_time)
        except ValueError:
            continue

        if not (week["start"] <= dt.date() <= week["end"]):
            continue

        notes_parts: list[str] = []
        if screening_venue:
            notes_parts.append(screening_venue)
        if open_captions is True:
            notes_parts.append("Open Captions")
        notes = " | ".join(notes_parts) if notes_parts else None

        # Normalize timezone-aware datetimes into local naive datetime for existing model consistency.
        start_dt = dt.replace(tzinfo=None)
        key = (description.lower(), start_dt.isoformat(), tickets_url)
        if key in seen:
            continue

        landing_url = landing_by_season_id.get(season_id, "")
        canonical_url = landing_url or tickets_url
        summary = summary_by_season_id.get(season_id)
        showings.append(
            Showing(
                title=description,
                venue=venue,
                start=start_dt,
                url=canonical_url,
                notes=notes,
                summary=summary,
            )
        )
        seen.add(key)

    return sorted(showings, key=lambda s: (s.start or datetime.max, s.title.lower()))


def _extract_escaped_field(block: str, field: str) -> str | None:
    pattern = re.compile(rf'\\"{re.escape(field)}\\":\\"((?:\\\\.|[^"\\\\])*)\\"')
    match = pattern.search(block)
    return match.group(1) if match else None


def _extract_bool_field(block: str, field: str) -> bool | None:
    pattern = re.compile(rf'\\"{re.escape(field)}\\":(true|false)')
    match = pattern.search(block)
    if not match:
        return None
    return match.group(1) == "true"


def _filmlinc_landing_url_by_season_id(html: str) -> dict[str, str]:
    mapping: dict[str, str] = {}

    film_uri_and_ids_pattern = re.compile(
        r'\\"uri\\":\\"(/films/[^\\"]+/)\\".{0,4000}?\\"productionSeasonIds\\":\\"([^\\"]+)\\"',
        re.DOTALL,
    )
    for match in film_uri_and_ids_pattern.finditer(html):
        url = _normalize_filmlinc_url(_decode_escaped_json_text(match.group(1)).strip())
        for season_id in [part.strip() for part in match.group(2).split(",") if part.strip()]:
            mapping[season_id] = url

    url_and_ids_pattern = re.compile(
        r'\\"ctaButton\\":\{.{0,1200}?\\"url\\":\\"([^\\"]+)\\".{0,6000}?\\"productionSeasonIds\\":\\"([^\\"]+)\\"',
        re.DOTALL,
    )
    for match in url_and_ids_pattern.finditer(html):
        raw_url = _decode_escaped_json_text(match.group(1)).strip()
        if not raw_url:
            continue
        url = _normalize_filmlinc_url(raw_url)
        for season_id in [part.strip() for part in match.group(2).split(",") if part.strip()]:
            mapping.setdefault(season_id, url)

    slug_and_ids_pattern = re.compile(
        r'\\"slug\\":\\"([^\\"]+)\\".{0,1200}?\\"productionSeasonIds\\":\\"([^\\"]+)\\"',
        re.DOTALL,
    )
    for match in slug_and_ids_pattern.finditer(html):
        slug = _decode_escaped_json_text(match.group(1)).strip().strip("/")
        if not slug:
            continue
        url = f"https://www.filmlinc.org/films/{slug}/"
        for season_id in [part.strip() for part in match.group(2).split(",") if part.strip()]:
            mapping.setdefault(season_id, url)

    return mapping


def _normalize_filmlinc_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.filmlinc.org{url}"
    return f"https://www.filmlinc.org/{url}"


def _filmlinc_summary_by_season_id(html: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    film_block_pattern = re.compile(
        r'\\"uri\\":\\"/films/[^\\"]+/\\".{0,40000}?\\"productionSeasonIds\\":\\"([^\\"]+)\\"',
        re.DOTALL,
    )
    for match in film_block_pattern.finditer(html):
        block = match.group(0)
        raw_ids = match.group(1)
        raw_excerpt = _extract_escaped_field(block, "excerpt") or ""
        raw_content = _extract_escaped_field(block, "content") or ""
        raw_text = raw_excerpt or raw_content
        if not raw_text:
            continue
        cleaned = _clean_filmlinc_rich_text(raw_text)
        if not cleaned:
            continue
        for season_id in [part.strip() for part in raw_ids.split(",") if part.strip()]:
            mapping.setdefault(season_id, cleaned)
    return mapping


def _clean_filmlinc_rich_text(value: str) -> str | None:
    decoded = _decode_escaped_json_text(value)
    decoded = html_lib.unescape(decoded)
    text = BeautifulSoup(decoded, "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if not text:
        return None
    text = _take_three_sentences(text)
    if _is_summary_junk(text):
        return None
    if len(text) > 520:
        text = text[:517].rstrip() + "..."
    return text


def _take_three_sentences(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    if not parts:
        return text
    return " ".join(parts[:3])


def _is_summary_junk(text: str) -> bool:
    if len(text) < 25:
        return True
    if len(re.findall(r"[A-Za-z]", text)) < 15:
        return True
    if re.fullmatch(r"[$€£]?\s*\d+([.,]\d+)?", text):
        return True
    return False


def _decode_escaped_json_text(value: str) -> str:
    # Decode escaped unicode/entities from embedded JSON snippets.
    try:
        return json.loads(f"\"{value}\"")
    except Exception:
        return (
            value.replace("\\u0026", "&")
            .replace("\\u003c", "<")
            .replace("\\u003e", ">")
            .replace("\\/", "/")
        )


def _current_week() -> dict[str, date]:
    now = datetime.now().date()
    monday = now - timedelta(days=now.weekday())
    return {"start": monday, "end": monday + timedelta(days=6)}

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "countryId": country_id,
        "cinemaId": cinema_slug,
        "status": "nowShowing",
        "requestType": "movies",
    }
    try:
        films_resp = requests.get(f"{base}/films", params=params, headers=headers, timeout=30)
        films_resp.raise_for_status()
        data = films_resp.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return None
