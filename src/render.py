from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import Showing, unique_titles_across_venues


@dataclass(slots=True)
class RenderedDigest:
    subject: str
    html: str
    text: str


@dataclass(slots=True)
class VenueListing:
    title: str
    normalized_title: str
    url: str
    schedule_lines: list[str]
    summary: str | None = None


TOP_PICK_HINTS = ["q&a", "35mm", "70mm", "one-night", "one night", "premiere", "restored"]
_VENUE_NOTE_RE = re.compile(r"\b(theater|theatre|cinema|screen|auditorium|venue)\b", re.IGNORECASE)


def _week_label(now: datetime) -> str:
    monday = now - timedelta(days=now.weekday())
    next_monday = monday + timedelta(days=7)
    return f"{monday:%b %d, %Y} - {next_monday:%b %d, %Y}"


def _is_top_pick(showing: Showing) -> bool:
    notes = (showing.notes or "").lower()
    title = showing.title.lower()
    return any(h in notes or h in title for h in TOP_PICK_HINTS)


def _top_picks(showings: list[Showing]) -> list[Showing]:
    by_title: dict[str, Showing] = {}
    for showing in sorted(showings, key=lambda s: (s.start or datetime.max, s.title.lower())):
        existing = by_title.get(showing.normalized_title)
        if existing is None:
            by_title[showing.normalized_title] = showing
            continue
        if existing.start is None and showing.start is not None:
            by_title[showing.normalized_title] = showing

    picks = [s for s in by_title.values() if _is_top_pick(s)]
    if len(picks) < 5:
        remaining = [s for s in by_title.values() if s not in picks]
        picks.extend(sorted(remaining, key=lambda s: (s.start or datetime.max))[: 5 - len(picks)])
    return sorted(picks, key=lambda s: (s.start or datetime.max, s.title.lower()))[:5]


def _clean_note(note: str | None) -> str | None:
    if not note:
        return None
    parts = [part.strip() for part in note.split("|")]
    keep = [part for part in parts if part and not _VENUE_NOTE_RE.search(part)]
    if not keep:
        return None
    return " | ".join(keep)


def _format_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _build_schedule_lines(showings: list[Showing]) -> list[str]:
    grouped: dict[date | None, list[str]] = defaultdict(list)

    for showing in sorted(showings, key=lambda s: (s.start or datetime.max)):
        if showing.start is None:
            label = "TBA"
            if label not in grouped[None]:
                grouped[None].append(label)
            continue

        time_label = _format_time(showing.start)
        note = _clean_note(showing.notes)
        entry = f"{time_label} ({note})" if note else time_label
        day_key = showing.start.date()
        if entry not in grouped[day_key]:
            grouped[day_key].append(entry)

    lines: list[str] = []
    for day_key in sorted([k for k in grouped.keys() if k is not None]):
        day_label = day_key.strftime("%a %b %d").upper()
        lines.append(f"{day_label}, {', '.join(grouped[day_key])}")

    if None in grouped:
        lines.extend(grouped[None])
    return lines


def _group_by_venue(showings: list[Showing]) -> dict[str, list[VenueListing]]:
    grouped_by_venue: dict[str, dict[str, VenueListing]] = defaultdict(dict)

    title_showings_by_venue: dict[str, dict[str, list[Showing]]] = defaultdict(lambda: defaultdict(list))

    for showing in sorted(showings, key=lambda s: (s.venue.lower(), s.start or datetime.max, s.title.lower())):
        venue_map = grouped_by_venue[showing.venue]
        title_showings_by_venue[showing.venue][showing.normalized_title].append(showing)
        listing = venue_map.get(showing.normalized_title)
        if listing is None:
            listing = VenueListing(
                title=showing.title,
                normalized_title=showing.normalized_title,
                url=showing.url,
                schedule_lines=[],
                summary=showing.summary,
            )
            venue_map[showing.normalized_title] = listing
        elif showing.summary and not listing.summary:
            listing.summary = showing.summary

    for venue, title_map in grouped_by_venue.items():
        for normalized_title, listing in title_map.items():
            listing.schedule_lines = _build_schedule_lines(title_showings_by_venue[venue][normalized_title])

    result: dict[str, list[VenueListing]] = {}
    for venue, title_map in grouped_by_venue.items():
        items = list(title_map.values())
        items.sort(key=lambda i: (i.title.lower(), i.schedule_lines[0] if i.schedule_lines else ""))
        result[venue] = items
    return dict(sorted(result.items(), key=lambda item: item[0].lower()))


def _top_pick_reason(showing: Showing, cross_venue: dict[str, set[str]]) -> str:
    notes = (showing.notes or "").lower()
    if "q&a" in notes:
        return "Includes a live Q&A, which usually makes for a more memorable screening."
    if "70mm" in notes or "35mm" in notes:
        return "Special-format presentation (35mm/70mm), which is rare and worth prioritizing."
    if "premiere" in notes:
        return "Premiere screening with higher buzz and limited repeat opportunities."
    if "restored" in notes:
        return "Restored presentation, a strong chance to see a definitive version on the big screen."
    venues = cross_venue.get(showing.normalized_title, set())
    if len(venues) > 1:
        return "Playing at multiple venues this week, a good signal of strong programming momentum."
    if showing.start:
        return "Early-week slot that is easier to plan around before schedules get crowded."
    return "High-signal pick based on this week’s programming patterns."


def render_digest(showings: list[Showing], generated_at: datetime | None = None) -> RenderedDigest:
    now = generated_at or datetime.now()
    week_label = _week_label(now)
    cross_venue = unique_titles_across_venues(showings)

    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )
    template = env.get_template("email.html.j2")

    grouped = _group_by_venue(showings)
    picks = _top_picks(showings)
    for pick in picks:
        pick.notes = _clean_note(pick.notes)
    subject = f"NYC Arthouse Digest ({week_label})"

    html = template.render(
        generated_at=now,
        week_label=week_label,
        by_venue=grouped,
        top_picks=picks,
        top_pick_reasons={pick.normalized_title: _top_pick_reason(pick, cross_venue) for pick in picks},
        cross_venue=cross_venue,
    )

    lines = [
        subject,
        "",
        f"Generated: {now:%Y-%m-%d %H:%M}",
        "",
        "Top Picks:",
    ]
    for pick in picks:
        when = pick.start.strftime("%Y-%m-%d %H:%M") if pick.start else "TBA"
        lines.append(f"- {pick.title} ({pick.venue}, {when}) -> {pick.url}")
        lines.append(f"  Why pick: {_top_pick_reason(pick, cross_venue)}")

    lines.append("")
    for venue, items in grouped.items():
        lines.append(f"{venue}:")
        for item in items:
            lines.append(f"- {item.title} -> {item.url}")
            if item.summary:
                lines.append(f"  {item.summary}")
            for schedule_line in item.schedule_lines:
                lines.append(f"  - {schedule_line}")
        lines.append("")

    return RenderedDigest(subject=subject, html=html, text="\n".join(lines).strip() + "\n")
