from datetime import datetime, timedelta, timezone

from app.astro.dasha import Antardasha, Mahadasha
from app.astro.event_window_scanner import WindowRule, scan_dasha_windows

FROM = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _mahadasha(lord, start, years, antardasha_lords) -> Mahadasha:
    end = start + timedelta(days=years * 365.2425)
    span = (end - start) / len(antardasha_lords)
    antardashas = []
    cursor = start
    for a_lord in antardasha_lords:
        a_end = cursor + span
        antardashas.append(Antardasha(lord=a_lord, start=cursor, end=a_end))
        cursor = a_end
    return Mahadasha(lord=lord, start=start, end=end, antardashas=antardashas)


def _timeline() -> list[Mahadasha]:
    m1 = _mahadasha("Ve", FROM, 5, ["Ve", "Su", "Mo", "Ma"])
    m2 = _mahadasha("Su", m1.end, 3, ["Su", "Mo", "Ma"])
    return [m1, m2]


def test_scan_only_returns_windows_a_rule_actually_matches():
    rules = [WindowRule("antardasha_lord", "Mo", 2.0, "moon_antardasha")]
    windows = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=10)
    assert len(windows) == 2  # one Mo antardasha in each mahadasha
    assert all(w.antardasha_lord == "Mo" for w in windows)
    assert all(w.score == 2.0 for w in windows)
    assert all(w.reason_keys == ["moon_antardasha"] for w in windows)


def test_scan_sums_score_when_multiple_rules_fire_on_the_same_window():
    rules = [
        WindowRule("antardasha_lord", "Ve", 3.0, "venus_antardasha"),
        WindowRule("mahadasha_lord", "Ve", 1.0, "venus_mahadasha"),
    ]
    windows = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=10)
    # The mahadasha-level rule matches every Antardasha inside the Ve
    # Mahadasha (4 of them); only the one whose OWN Antardasha lord is also
    # Ve additionally matches the antardasha-level rule, so it scores higher
    # than its 3 siblings, not exclusively.
    assert len(windows) == 4
    top = windows[0]
    assert top.antardasha_lord == "Ve" and top.mahadasha_lord == "Ve"
    assert top.score == 4.0
    assert set(top.reason_keys) == {"venus_antardasha", "venus_mahadasha"}
    assert all(w.score == 1.0 for w in windows[1:])


def test_scan_excludes_windows_outside_the_horizon():
    rules = [WindowRule("mahadasha_lord", "Su", 1.0, "sun_mahadasha")]
    # m2 (Su Mahadasha) starts ~5 years after FROM — a 1 year horizon must miss it.
    windows_short = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=1)
    windows_long = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=10)
    assert len(windows_short) == 0
    assert len(windows_long) > 0


def test_scan_excludes_windows_before_from_dt_and_clips_the_straddling_one():
    rules = [WindowRule("antardasha_lord", "Ve", 1.0, "venus_antardasha")]
    mid_window_start = FROM + timedelta(days=200)
    windows = scan_dasha_windows(_timeline(), rules, mid_window_start, horizon_years=10)
    assert len(windows) == 1
    assert windows[0].start == mid_window_start  # clipped, not the antardasha's real (earlier) start


def test_scan_clips_a_windows_end_to_the_horizon_too():
    # A window whose real Antardasha end falls AFTER horizon_end (e.g. an
    # ongoing period during a past-direction search, where horizon_end is
    # "now") must be reported as ending at horizon_end, not its real
    # (future-relative-to-the-search) end — otherwise a "what happened in
    # the past" search could return a window that hasn't finished yet with
    # an end date still out in the future.
    rules = [WindowRule("antardasha_lord", "Ve", 1.0, "venus_antardasha")]
    horizon_years = 200 / 365.2425  # ends mid-way through the first (Ve) antardasha
    horizon_end = FROM + timedelta(days=200)
    windows = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=horizon_years)
    assert len(windows) == 1
    assert windows[0].end == horizon_end


def test_scan_results_sorted_highest_score_first():
    rules = [
        WindowRule("antardasha_lord", "Mo", 1.0, "moon_antardasha"),
        WindowRule("antardasha_lord", "Ve", 5.0, "venus_antardasha"),
    ]
    windows = scan_dasha_windows(_timeline(), rules, FROM, horizon_years=10)
    scores = [w.score for w in windows]
    assert scores == sorted(scores, reverse=True)
