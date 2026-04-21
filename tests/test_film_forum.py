from __future__ import annotations

from datetime import date

from src.scrapers.film_forum import _tab_dates_by_id, parse_film_forum_showings


def test_parse_film_forum_showings_keeps_all_times_for_same_title() -> None:
    html = """
    <ul class="ui-tabs-nav">
      <li class="thu"><a href="#tabs-0">THU</a></li>
      <li class="fri"><a href="#tabs-1">FRI</a></li>
      <li class="sat"><a href="#tabs-2">SAT</a></li>
      <li class="sun"><a href="#tabs-3">SUN</a></li>
      <li class="mon"><a href="#tabs-4">MON</a></li>
      <li class="tue"><a href="#tabs-5">TUE</a></li>
      <li class="wed"><a href="#tabs-6">WED</a></li>
    </ul>
    <div class="showtimes-container">
      <div id="tabs-0">
        <p><strong><a href="https://filmforum.org/film/two-prosecutors">TWO PROSECUTORS</a></strong><br />
        <span>12:20</span> <span>3:00</span> <span>5:30</span> <span>8:00</span></p>
      </div>
      <div id="tabs-3">
        <p><a href="https://filmforum.org/series/film-forum-jr.-series-page">FILM FORUM JR.</a><br />
        <strong><a href="https://filmforum.org/film/beetlejuice-ffjr-2026">BEETLEJUICE</a></strong><br />
        <span>11:00</span></p>
      </div>
    </div>
    """

    showings = parse_film_forum_showings(html, reference_date=date(2026, 4, 6))

    prosecutors = [s for s in showings if s.title == "TWO PROSECUTORS"]
    assert len(prosecutors) == 4
    assert [s.start.strftime("%Y-%m-%d %H:%M") for s in prosecutors if s.start] == [
        "2026-04-02 12:20",
        "2026-04-02 15:00",
        "2026-04-02 17:30",
        "2026-04-02 20:00",
    ]

    beetlejuice = next(s for s in showings if s.title == "BEETLEJUICE")
    assert beetlejuice.start is not None
    assert beetlejuice.start.strftime("%Y-%m-%d %H:%M") == "2026-04-05 11:00"
    assert beetlejuice.notes == "FILM FORUM JR."


def test_tab_dates_anchor_to_most_recent_first_weekday() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        """
        <ul class="ui-tabs-nav">
          <li class="thu"><a href="#tabs-0">THU</a></li>
          <li class="fri"><a href="#tabs-1">FRI</a></li>
          <li class="sat"><a href="#tabs-2">SAT</a></li>
          <li class="sun"><a href="#tabs-3">SUN</a></li>
          <li class="mon"><a href="#tabs-4">MON</a></li>
          <li class="tue"><a href="#tabs-5">TUE</a></li>
          <li class="wed"><a href="#tabs-6">WED</a></li>
        </ul>
        """,
        "html.parser",
    )

    dates = _tab_dates_by_id(soup, reference_date=date(2026, 4, 6))

    assert dates == {
        "tabs-0": date(2026, 4, 2),
        "tabs-1": date(2026, 4, 3),
        "tabs-2": date(2026, 4, 4),
        "tabs-3": date(2026, 4, 5),
        "tabs-4": date(2026, 4, 6),
        "tabs-5": date(2026, 4, 7),
        "tabs-6": date(2026, 4, 8),
    }
