from datetime import datetime, timedelta, timezone

from app.astro.dasha import Antardasha, Mahadasha
from app.astro.marriage_timing import corroborate_with_transits, find_marriage_windows, marriage_rules
from app.astro.event_window_scanner import ScoredWindow

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


def test_marriage_rules_score_seventh_lord_antardasha_highest():
    seventh_lord = "Sa"
    rules = marriage_rules(seventh_lord)
    antar_rule = next(r for r in rules if r.applies_to == "antardasha_lord" and r.target == seventh_lord)
    other_weights = [r.weight for r in rules if r.reason_key != antar_rule.reason_key]
    assert all(antar_rule.weight >= w for w in other_weights)


def test_marriage_rules_double_count_when_seventh_lord_is_a_karaka():
    # A chart whose 7th lord happens to be Venus fires BOTH the 7th-lord rule
    # and the Venus rule on the same Antardasha window — a genuinely stronger
    # signal, not a bug to suppress.
    rules_venus_seventh = marriage_rules("Ve")
    matching = [r for r in rules_venus_seventh if r.applies_to == "antardasha_lord" and r.target == "Ve"]
    assert len(matching) == 2  # the seventh_lord_antardasha rule AND venus_antardasha rule both target Ve
    assert {r.reason_key for r in matching} == {"seventh_lord_antardasha", "venus_antardasha"}


def test_find_marriage_windows_ranks_seventh_lord_window_above_unrelated_one():
    maha1 = _mahadasha("Sa", FROM, 19, ["Sa", "Me", "Ke"])  # Sa antardasha = 7th lord hit
    maha2 = _mahadasha("Me", maha1.end, 17, ["Me", "Ve", "Su"])
    timeline = [maha1, maha2]
    windows = find_marriage_windows(timeline, seventh_lord="Sa", from_dt=FROM, horizon_years=40, top_n=10)
    assert len(windows) > 0
    assert windows[0].antardasha_lord in ("Sa", "Ve")  # 7th lord or Venus antardasha ranks at the top
    # Every returned window has a positive score (irrelevant windows filtered out).
    assert all(w.score > 0 for w in windows)


def test_find_marriage_windows_respects_top_n():
    timeline = [_mahadasha("Ve", FROM, 20, ["Ve", "Su", "Mo", "Ma", "Ra", "Ju", "Sa", "Me", "Ke"])]
    windows = find_marriage_windows(timeline, seventh_lord="Ve", from_dt=FROM, horizon_years=25, top_n=2)
    assert len(windows) <= 2


def test_find_marriage_windows_searches_the_past_when_given_earlier_bounds():
    # No separate "past" function — get_marriage_timing's `direction="past"`
    # just calls this exact function with from_dt=birth_dt and
    # horizon_years=age instead of from_dt=now and horizon_years=20. This
    # confirms that choice of bounds genuinely searches (and bounds) the past.
    birth_dt = FROM
    now = FROM + timedelta(days=15 * 365.2425)  # "today" is 15 years after birth
    maha1 = _mahadasha("Sa", birth_dt, 19, ["Sa", "Me", "Ke"])
    age_years = (now - birth_dt).days / 365.2425

    windows = find_marriage_windows(
        [maha1], seventh_lord="Sa", from_dt=birth_dt, horizon_years=age_years, top_n=10
    )
    assert len(windows) > 0
    assert all(w.start >= birth_dt for w in windows)
    assert all(w.end <= now + timedelta(days=1) for w in windows)  # nothing beyond "now" returned


def test_corroborate_with_transits_returns_a_bool():
    window = ScoredWindow(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        mahadasha_lord="Ve",
        antardasha_lord="Ve",
        score=2.0,
        reason_keys=["venus_antardasha"],
    )
    result = corroborate_with_transits(window, lagna_sign_index=0, moon_sign_index=3)
    assert isinstance(result, bool)
