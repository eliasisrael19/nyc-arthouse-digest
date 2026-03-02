from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from src.models import Showing
from src.scrapers.base import CACHE_DIR


@dataclass(slots=True)
class OpenAIConfig:
    api_key: str
    model: str = "gpt-5-mini"
    timeout_seconds: int = 120
    max_retries: int = 2


class OpenAIExtractor:
    def __init__(self, config: OpenAIConfig) -> None:
        self.config = config
        self.cache_dir = CACHE_DIR / "agent"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def from_env() -> "OpenAIExtractor | None":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
        timeout = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
        return OpenAIExtractor(
            OpenAIConfig(
                api_key=api_key,
                model=model,
                timeout_seconds=timeout,
                max_retries=max_retries,
            )
        )

    def extract_showings(
        self,
        venue: str,
        source_url: str,
        html: str,
        week_label: str,
        cache_key: str,
        max_items: int = 120,
    ) -> list[Showing]:
        prepared_html = _prepare_html_for_agent(html)
        payload = self._build_payload(
            venue=venue,
            source_url=source_url,
            html=prepared_html,
            week_label=week_label,
            max_items=max_items,
        )
        payload_string = json.dumps(payload, sort_keys=True)
        fingerprint = sha1(payload_string.encode("utf-8")).hexdigest()[:16]
        cache_file = self.cache_dir / f"{cache_key}_{fingerprint}.json"

        if cache_file.exists():
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            return self._parse_records(raw.get("items", []), venue=venue, source_url=source_url)

        response: requests.Response | None = None
        for attempt in range(self.config.max_retries + 1):
            response = requests.post(
                "https://api.openai.com/v1/responses",
                timeout=self.config.timeout_seconds,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code < 500 and response.status_code != 429:
                break
            if attempt < self.config.max_retries:
                time.sleep(1.5 * (attempt + 1))

        if response is None:
            raise RuntimeError("OpenAI request did not execute")

        response.raise_for_status()
        body = response.json()

        parsed_json = self._extract_structured_output(body)
        cache_file.write_text(json.dumps(parsed_json, indent=2), encoding="utf-8")
        return self._parse_records(parsed_json.get("items", []), venue=venue, source_url=source_url)

    def _build_payload(self, venue: str, source_url: str, html: str, week_label: str, max_items: int) -> dict[str, Any]:
        schema = {
            "name": "venue_showings",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "maxItems": max_items,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "start": {"type": ["string", "null"]},
                                "notes": {"type": ["string", "null"]},
                                "summary": {"type": ["string", "null"]},
                            },
                            "required": ["title", "url", "start", "notes", "summary"],
                        },
                    }
                },
                "required": ["items"],
            },
            "strict": True,
        }

        instructions = (
            "Extract only film/event showings from the provided venue page for the requested week. "
            "Ignore memberships, merchandise, static nav links, and unrelated promos. "
            "Use absolute URLs. start must be ISO-like if known (YYYY-MM-DD HH:MM preferred), else null. "
            "notes should include useful context like Q&A, 35mm, 70mm, one-night, premiere, restored. "
            "summary should be 2-3 concise sentences about what the film/event is; if unavailable, return null."
        )

        return {
            "model": self.config.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": instructions}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Venue: {venue}\nSource URL: {source_url}\nTarget week: {week_label}\nReturn only JSON schema output.",
                        },
                        {"type": "input_text", "text": html[:300000]},
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema["name"],
                    "schema": schema["schema"],
                    "strict": True,
                }
            },
        }

    def _extract_structured_output(self, body: dict[str, Any]) -> dict[str, Any]:
        # Responses API returns structured output in output_text when using text.format=json_schema.
        text = body.get("output_text", "")
        if not text:
            # Fallback to walking output content blocks if output_text is missing.
            for output_item in body.get("output", []):
                for content in output_item.get("content", []):
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        text = content["text"]
                        break
                if text:
                    break

        if not text:
            raise ValueError("OpenAI response did not contain structured output text")

        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("OpenAI structured output was not an object")
        return data

    def _parse_records(self, raw_items: list[dict[str, Any]], venue: str, source_url: str) -> list[Showing]:
        results: list[Showing] = []
        seen: set[str] = set()

        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title", "")).strip()
            url = str(raw.get("url", "")).strip()
            if not title or not url:
                continue
            url = urljoin(source_url, url)

            key = f"{title.lower()}|{url}"
            if key in seen:
                continue

            start = _parse_start(raw.get("start"))
            notes = _clean_optional(raw.get("notes"))
            summary = _clean_summary(raw.get("summary"))
            results.append(Showing(title=title, venue=venue, start=start, url=url, notes=notes, summary=summary))
            seen.add(key)

        return results


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _parse_start(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _clean_summary(value: Any) -> str | None:
    out = _clean_optional(value)
    if not out:
        return None
    out = out.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    clipped = _take_three_sentences(" ".join(out.split()))
    if _is_summary_junk(clipped):
        return None
    if len(clipped) > 520:
        clipped = clipped[:517].rstrip() + "..."
    return clipped


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


def _prepare_html_for_agent(html: str) -> str:
    # Keep extraction focused and fast by sending only high-signal sections when possible.
    soup = BeautifulSoup(html, "html.parser")
    day_blocks = soup.select("div.calendar-list-day")
    if day_blocks:
        trimmed = "\n".join(str(block) for block in day_blocks)
        return trimmed[:160000]

    main = soup.find("main")
    if main:
        return str(main)[:160000]
    return html[:160000]
