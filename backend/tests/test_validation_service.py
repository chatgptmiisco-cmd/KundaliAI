from datetime import datetime, timedelta, timezone

from app.astro.dasha import Antardasha
from app.services.validation_service import _build_statement, _select_diverse_antardashas


def _antardasha(lord, start_days_ago, span_days):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start = now - timedelta(days=start_days_ago)
    end = start + timedelta(days=span_days)
    return Antardasha(lord=lord, start=start, end=end)


def test_select_diverse_antardashas_excludes_future_and_too_short_periods():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    completed = _antardasha("Su", start_days_ago=1000, span_days=200)
    future = Antardasha(lord="Mo", start=now + timedelta(days=10), end=now + timedelta(days=200))
    too_short = _antardasha("Ma", start_days_ago=500, span_days=10)
    result = _select_diverse_antardashas([completed, future, too_short], now, max_count=4)
    assert result == [completed]


def test_select_diverse_antardashas_spreads_across_life_when_many_available():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    many = [_antardasha(lord="Su", start_days_ago=(i + 1) * 300, span_days=200) for i in range(20)]
    # oldest-first order, as compute_mahadashas would naturally produce
    many = list(reversed(many))
    result = _select_diverse_antardashas(many, now, max_count=4)
    assert len(result) == 4
    # must include the most recent completed one
    assert result[-1] == many[-1]
    # selections should span a wide range, not four adjacent entries
    assert result[0] != many[-4]


def test_select_diverse_antardashas_returns_empty_when_nothing_qualifies():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _select_diverse_antardashas([], now, max_count=4) == []


def test_build_statement_mentions_lord_house_and_dates_en():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    statement = _build_statement("Sa", house=10, dignity="exalted", start=start, end=end, language="en")
    assert "Mar 2015" in statement
    assert "Jan 2017" in statement
    assert "Saturn" in statement
    assert "10th house" in statement
    assert "career" in statement


def test_build_statement_hindi_uses_devanagari_month_and_lord_names():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    statement = _build_statement("Sa", house=10, dignity="debilitated", start=start, end=end, language="hi")
    assert "मार्च 2015" in statement
    assert "जनवरी 2017" in statement
    assert "शनि" in statement


def test_build_statement_varies_by_dignity():
    start = datetime(2015, 3, 1, tzinfo=timezone.utc)
    end = datetime(2017, 1, 1, tzinfo=timezone.utc)
    strong = _build_statement("Ju", house=1, dignity="exalted", start=start, end=end, language="en")
    weak = _build_statement("Ju", house=1, dignity="debilitated", start=start, end=end, language="en")
    assert strong != weak
