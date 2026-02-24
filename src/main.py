from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.agents.openai_extractor import OpenAIExtractor
from src.agents.venue_agent import AgentVenueConfig, AgentVenueScraper
from src.config import load_config, load_dotenv
from src.emailer import send_email
from src.enrich import enrich_missing_summaries
from src.models import Showing, dedupe_showings
from src.render import render_digest
from src.scrapers.manual_yaml import ManualYamlScraper
from src.scrapers.metrograph import MetrographScraper


class EmptyScraper:
    def __init__(self, venue: str, note: str) -> None:
        self.venue = venue
        self.note = note

    def scrape(self) -> list[Showing]:
        return []


def build_scrapers() -> dict[str, Callable[[], object]]:
    return {
        "metrograph": MetrographScraper,
        "manual": ManualYamlScraper,
        "angelika": lambda: EmptyScraper("Angelika Film Center", "Placeholder"),
        "angelika-nyc": lambda: EmptyScraper("Angelika New York", "Placeholder"),
        "ifc": lambda: EmptyScraper("IFC Center", "Placeholder"),
        "village-east": lambda: EmptyScraper("Village East by Angelika", "Placeholder"),
        "cinema123": lambda: EmptyScraper("Cinema123 by Angelika", "Placeholder"),
        "lincoln-center": lambda: EmptyScraper("Film at Lincoln Center", "Placeholder"),
        "film-forum": lambda: EmptyScraper("Film Forum", "Placeholder"),
        "a24-cherry-lane": lambda: EmptyScraper("A24 Cherry Lane", "Placeholder"),
    }


def build_agent_configs() -> dict[str, AgentVenueConfig]:
    return {
        "metrograph": AgentVenueConfig(
            name="Metrograph",
            url="https://metrograph.com/nyc/",
            cache_key="metrograph_nyc",
        ),
        "lincoln-center": AgentVenueConfig(
            name="Film at Lincoln Center",
            url="https://www.filmlinc.org/",
            cache_key="filmlinc",
            source_mode="filmlinc_embedded",
        ),
        "ifc": AgentVenueConfig(
            name="IFC Center",
            url="https://www.ifccenter.com/",
            cache_key="ifc_center",
        ),
        "angelika-nyc": AgentVenueConfig(
            name="Angelika New York",
            url="https://angelikafilmcenter.com/nyc/now-playing",
            cache_key="angelika_nyc",
            source_mode="reading_api",
            country_id="6",
            cinema_slug="0000000005",
        ),
        "village-east": AgentVenueConfig(
            name="Village East by Angelika",
            url="https://angelikafilmcenter.com/villageeast/now-playing",
            cache_key="angelika_village_east",
            source_mode="reading_api",
            country_id="6",
            cinema_slug="0000000004",
        ),
        "cinema123": AgentVenueConfig(
            name="Cinema123 by Angelika",
            url="https://angelikafilmcenter.com/cinemas123/now-playing",
            cache_key="angelika_cinema123",
            source_mode="reading_api",
            country_id="6",
            cinema_slug="21",
        ),
        "film-forum": AgentVenueConfig(
            name="Film Forum",
            url="https://filmforum.org/now_playing",
            cache_key="film_forum",
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NYC arthouse digest generator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Write digest_preview.html locally")
    mode.add_argument("--send", action="store_true", help="Send digest email via SMTP")

    parser.add_argument(
        "--venues",
        nargs="+",
        default=[
            "metrograph",
            "lincoln-center",
            "ifc",
            "angelika-nyc",
            "village-east",
            "cinema123",
            "film-forum",
        ],
        help="Venue sources (metrograph lincoln-center ifc angelika-nyc village-east cinema123 film-forum manual)",
    )
    parser.add_argument(
        "--mode",
        choices=["scraper", "agent", "hybrid"],
        default="agent",
        help="Collection mode: scraper, agent, or hybrid (agent first with scraper fallback)",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--preview-path", default="digest_preview.html", help="Preview file output path for --dry-run")
    return parser.parse_args()


def collect_showings(venue_names: list[str], mode: str) -> list[Showing]:
    factories = build_scrapers()
    agent_configs = build_agent_configs()
    extractor = OpenAIExtractor.from_env() if mode in {"agent", "hybrid"} else None

    effective_mode = mode
    if mode in {"agent", "hybrid"} and not extractor:
        print("[warn] OPENAI_API_KEY not found; falling back to scraper mode")
        effective_mode = "scraper"

    showings: list[Showing] = []
    for venue_name in venue_names:
        if venue_name == "manual":
            showings.extend(_run_scraper_only(venue_name, factories))
            continue

        if effective_mode == "agent":
            showings.extend(_run_agent_only(venue_name, extractor, agent_configs))
            continue

        if effective_mode == "hybrid":
            agent_results = _run_agent_only(venue_name, extractor, agent_configs)
            showings.extend(agent_results if agent_results else _run_scraper_only(venue_name, factories))
            continue

        showings.extend(_run_scraper_only(venue_name, factories))

    return dedupe_showings(showings)


def _run_agent_only(
    venue_name: str,
    extractor: OpenAIExtractor | None,
    configs: dict[str, AgentVenueConfig],
) -> list[Showing]:
    if not extractor:
        return []

    config = configs.get(venue_name)
    if not config:
        print(f"[info] {venue_name}: no agent config, skipping")
        return []

    try:
        scraper = AgentVenueScraper(extractor=extractor, config=config)
        venue_showings = scraper.scrape()
        print(f"[info] {venue_name}: agent collected {len(venue_showings)} entries")
        return venue_showings
    except Exception as exc:
        print(f"[warn] Agent extraction failed for {venue_name}: {exc}")
        return []


def _run_scraper_only(
    venue_name: str,
    scraper_factories: dict[str, Callable[[], object]],
) -> list[Showing]:
    factory = scraper_factories.get(venue_name)
    if not factory:
        print(f"[warn] Unknown venue '{venue_name}', skipping")
        return []

    scraper = factory()
    try:
        venue_showings = scraper.scrape()
        print(f"[info] {venue_name}: scraper collected {len(venue_showings)} entries")
        return venue_showings
    except Exception as exc:  # broad by design: never fail the whole digest
        print(f"[warn] Scraper failed for {venue_name}: {exc}")
        return []


def main() -> None:
    load_dotenv()
    args = parse_args()
    showings = collect_showings(args.venues, mode=args.mode)
    showings = enrich_missing_summaries(showings)

    digest = render_digest(showings, generated_at=datetime.now())

    if args.dry_run:
        preview_path = Path(args.preview_path)
        preview_path.write_text(digest.html, encoding="utf-8")
        print(f"[ok] Wrote preview HTML to {preview_path.resolve()}")
        print(f"[ok] Generated digest with {len(showings)} deduped listings")
        return

    config = load_config(args.config)
    send_email(config, digest.subject, digest.html, digest.text)
    print(f"[ok] Sent digest email to: {', '.join(config.recipients)}")


if __name__ == "__main__":
    main()
