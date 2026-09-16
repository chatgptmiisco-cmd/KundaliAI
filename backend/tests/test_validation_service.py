from datetime import date, datetime, timedelta, timezone

from app.astro.dasha import Antardasha
from app.services.validation_service import _build_statement, _select_diverse_antardashas

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_ADULT_BIRTH_DATE = date(1990, 1, 1)  # 36 years old at _NOW — old enough for any window used below


def _antardasha(lord, start_days_ago, span_days):
    start = _NOW - timedelta(days=start_days_ago)
    end = start + timedelta(days=span_days)
    return Antardasha(lord=lord, start=start, end=end)


def test_select_diverse_antardashas_excludes_future_and_too_short_periods():
    completed = _antardasha("Su", start_days_ago=1000, span_days=200)
    future = Antardasha(lord="Mo", start=_NOW + timedelta(days=10), end=_NOW + timedelta(days=200))
    too_short = _antardasha("Ma", start_days_ago=500, span_days=10)
    result = _select_diverse_antardashas([completed, future, too_short], _ADULT_BIRTH_DATE, _NOW, max_count=4)
    assert result == [completed]


def test_select_diverse_antardashas_spreads_across_life_when_many_available():
    # All within the last ~8 years so every one clears the 10-year recency cap.
    many = [_antardasha(lord="Su", start_days_ago=(i + 1) * 150, span_days=100) for i in range(20)]
    # oldest-first order, as compute_mahadashas would naturally produce
    many = list(reversed(many))
    result = _select_diverse_antardashas(many, _ADULT_BIRTH_DATE, _NOW, max_count=4)
    assert len(result) == 4
    # must include the most recent completed one
    assert result[-1] == many[-1]
    # selections should span a wide range, not four adjacent entries
    assert result[0] != many[-4]


def test_select_diverse_antardashas_returns_empty_when_nothing_qualifies():
    assert _select_diverse_antardashas([], _ADULT_BIRTH_DATE, _NOW, max_count=4) == []


def test_select_diverse_antardashas_excludes_infancy_even_when_completed_and_long_enough():
    # Started the day the person was born — should never be asked about,
    # even though it's a completed, long-enough Antardasha.
    infancy = Antardasha(lord="Su", start=_NOW - timedelta(days=9000), end=_NOW - timedelta(days=8900))
    birth_date = (_NOW - timedelta(days=9000)).date()
    recent_adult = _antardasha("Me", start_days_ago=1000, span_days=200)  # ~24yo at start, within 10y recency
    result = _select_diverse_antardashas([infancy, recent_adult], birth_date, _NOW, max_count=4)
    assert infancy not in result
    assert recent_adult in result


def test_select_diverse_antardashas_prefers_recent_over_too_old_when_both_relatable():
    birth_date = date(1990, 1, 1)
    recent = _antardasha("Me", start_days_ago=1000, span_days=200)  # within last 10 years
    too_old = _antardasha("Ju", start_days_ago=8000, span_days=200)  # ~21.9 years ago — outside the recency cap
    result = _select_diverse_antardashas([too_old, recent], birth_date, _NOW, max_count=4)
    assert result == [recent]


def test_build_statement_mentions_lord_focus_and_dates_en():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    statement = _build_statement("Sa", house=10, start=start, end=end, language="en")
    assert "Mar 2015" in statement
    assert "Jan 2017" in statement
    assert "Saturn" in statement
    assert "career" in statement


def test_build_statement_avoids_astrology_jargon_en():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    statement = _build_statement("Sa", house=10, start=start, end=end, language="en")
    assert "Antardasha" not in statement
    assert "house" not in statement.lower()


def test_build_statement_hindi_uses_devanagari_month_and_lord_names():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    statement = _build_statement("Sa", house=10, start=start, end=end, language="hi")
    assert "मार्च 2015" in statement
    assert "जनवरी 2017" in statement
    assert "शनि" in statement
