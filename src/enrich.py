from __future__ import annotations

from hashlib import sha1
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.models import Showing
from src.scrapers.base import fetch_with_cache

SUMMARY_HOST_ALLOWLIST = {
    "www.filmlinc.org",
    "filmlinc.org",
    "metrograph.com",
    "www.metrograph.com",
    "www.ifccenter.com",
    "ifccenter.com",
    "filmforum.org",
    "www.filmforum.org",
}
SUMMARY_FORCE_IMPROVE_HOSTS = {"metrograph.com", "www.metrograph.com"}


def enrich_missing_summaries(showings: list[Showing], max_fetches: int = 30) -> list[Showing]:
    by_url: dict[str, str | None] = {}
    fetches = 0

    for showing in showings:
        host = urlparse(showing.url).netloc.lower()
        should_force_improve = host in SUMMARY_FORCE_IMPROVE_HOSTS and _is_low_quality_summary(showing.summary)

        if showing.summary and not should_force_improve:
            by_url.setdefault(showing.url, showing.summary)
            continue
        if showing.url in by_url:
            replacement = by_url[showing.url]
            if replacement and (_is_low_quality_summary(showing.summary) or len(replacement) > len(showing.summary or "")):
                showing.summary = replacement
            continue
        if fetches >= max_fetches:
            continue
        if not showing.url.startswith("http"):
            continue
        if host not in SUMMARY_HOST_ALLOWLIST:
            continue

        summary = _fetch_summary_from_url(showing.url)
        by_url[showing.url] = summary
        if summary and (_is_low_quality_summary(showing.summary) or len(summary) > len(showing.summary or "")):
            showing.summary = summary
        fetches += 1

    return showings


def _fetch_summary_from_url(url: str) -> str | None:
    host_raw = urlparse(url).netloc.lower()
    host = host_raw.replace(".", "_")
    key = f"summary_{host}_{sha1(url.encode('utf-8')).hexdigest()[:10]}"
    html = fetch_with_cache(url, cache_key=key, ttl_hours=168, timeout_seconds=8)
    soup = BeautifulSoup(html, "html.parser")

    candidates: list[str] = []
    paragraph_selectors = ["article p", "main p", "p"]
    if host_raw in SUMMARY_FORCE_IMPROVE_HOSTS:
        paragraph_selectors = [".entry-content p", "article p", "main p", "p"]

    for selector in paragraph_selectors:
        for tag in soup.select(selector)[:8]:
            text = tag.get_text(" ", strip=True)
            if text:
                candidates.append(text)

    for selector in [
        "meta[property='og:description']",
        "meta[name='description']",
        "meta[name='twitter:description']",
    ]:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            candidates.append(str(tag["content"]))

    best: str | None = None
    best_score = -10_000
    for raw in candidates:
        cleaned = _clean_summary(raw)
        if not cleaned:
            continue
        score = _summary_score(cleaned)
        if score > best_score:
            best = cleaned
            best_score = score
    return best


def _clean_summary(text: str) -> str | None:
    out = " ".join(text.split())
    out = _take_three_sentences(out)
    if len(out) < 25:
        return None
    if len(re.findall(r"[A-Za-z]", out)) < 15:
        return None
    lowered = out.lower()
    if "cookie" in lowered or "privacy policy" in lowered:
        return None
    if len(out) > 520:
        out = out[:517].rstrip() + "..."
    return out


def _take_three_sentences(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    if not parts:
        return text
    return " ".join(parts[:3])


def _is_low_quality_summary(text: str | None) -> bool:
    if not text:
        return True
    cleaned = " ".join(text.split())
    if len(cleaned) < 80:
        return True
    low = cleaned.lower()
    if re.search(r"\b\d{4}\s+film\s+by\b", low):
        return True
    if cleaned.endswith("...") or "…" in cleaned:
        return True
    return False


def _summary_score(text: str) -> int:
    score = len(text)
    lowered = text.lower()
    if "back to films" in lowered or "sign up today" in lowered:
        score -= 200
    if re.search(r"\b\d{4}\s+film\s+by\b", lowered):
        score -= 180
    if " minutes." in lowered and len(text) < 120:
        score -= 100
    if 120 <= len(text) <= 260:
        score += 40
    return score
