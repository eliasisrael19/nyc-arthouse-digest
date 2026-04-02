from __future__ import annotations

from src.agents.openai_extractor import OpenAIConfig, OpenAIExtractor, _parse_start
from src.agents.venue_agent import _clean_filmlinc_rich_text, _filmlinc_landing_url_by_season_id


def test_parse_start_supports_common_formats() -> None:
    assert _parse_start("2026-03-01 19:30") is not None
    assert _parse_start("2026-03-01T19:30") is not None
    assert _parse_start("2026-03-01") is not None
    assert _parse_start("not-a-date") is None


def test_filmlinc_landing_map_prefers_cta_url() -> None:
    html = (
        '\\"ctaButton\\":{\\"url\\":\\"https://www.filmlinc.org/films/12-days/\\"}'
        '\\"ctaRelatedFilm\\":{\\"nodes\\":[{\\"slug\\":\\"12-days\\",\\"filmDetails\\":{\\"productionSeasonIds\\":\\"81134\\"}}]}'
    )
    mapping = _filmlinc_landing_url_by_season_id(html)
    assert mapping["81134"] == "https://www.filmlinc.org/films/12-days/"


def test_filmlinc_rich_text_cleanup() -> None:
    raw = "\\u003cp\\u003eA portrait of a city in transition.\\u003c/p\\u003e"
    cleaned = _clean_filmlinc_rich_text(raw)
    assert cleaned == "A portrait of a city in transition."


def test_parse_records_keeps_multiple_showtimes_for_same_film_url() -> None:
    extractor = OpenAIExtractor(OpenAIConfig(api_key="test"))
    raw_items = [
        {
            "title": "TWO PROSECUTORS",
            "url": "https://filmforum.org/film/two-prosecutors",
            "start": "2026-03-30 12:20",
            "notes": None,
            "summary": None,
        },
        {
            "title": "TWO PROSECUTORS",
            "url": "https://filmforum.org/film/two-prosecutors",
            "start": "2026-03-30 15:00",
            "notes": None,
            "summary": None,
        },
    ]

    results = extractor._parse_records(
        raw_items,
        venue="Film Forum",
        source_url="https://filmforum.org/now_playing",
    )

    assert len(results) == 2
    assert [showing.start.strftime("%H:%M") for showing in results if showing.start] == ["12:20", "15:00"]
