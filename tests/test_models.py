from datetime import datetime

from src.models import Showing, dedupe_showings, normalize_title


def test_normalize_title_strips_article_and_punctuation() -> None:
    assert normalize_title("The Red Shoes!!!") == "red shoes"
    assert normalize_title("  An Autumn Sonata ") == "autumn sonata"


def test_dedupe_showings_removes_exact_duplicate() -> None:
    start = datetime(2026, 2, 27, 19, 0)
    s1 = Showing("The Red Shoes", "Metrograph", start, "https://example.com/1", "35mm")
    s2 = Showing("The Red Shoes", "Metrograph", start, "https://example.com/1", "Q&A")
    s3 = Showing("The Red Shoes", "Anthology Film Archives", start, "https://example.com/2", None)

    deduped = dedupe_showings([s1, s2, s3])

    assert len(deduped) == 2
    merged = [s for s in deduped if s.venue == "Metrograph"][0]
    assert merged.notes is not None
    assert "35mm" in merged.notes
    assert "Q&A" in merged.notes
