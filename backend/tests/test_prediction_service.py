from datetime import datetime, timedelta, timezone

import pytest

from app.astro.constants import DAYS_PER_YEAR
from app.astro.dasha import Antardasha, Mahadasha
from app.astro.event_window_scanner import ScoredWindow
from app.astro.transit_corroboration import TransitCheck
from app.services.prediction_service import (
    _CANDIDATE_POOL_SIZE,
    _FUTURE_HORIZON_YEARS,
    _LONG_TERM_PEAK_MARGIN,
    _PAST_RECENCY_YEARS,
    _current_period_score,
    _delivery_anchor_window,
    _dusthana_lords,
    _evidence_level,
    _find_long_term_peak,
    _history_nudge,
    _is_currently_dusthana_afflicted,
    _peak_window_for,
    _resolve_past_windows,
    _rerank_with_transit_bonus,
    _search_bounds,
    _select_candidate_pool,
)


def _mahadasha(lord, start, years, antardasha_lords) -> Mahadasha:
    end = start + timedelta(days=years * DAYS_PER_YEAR)
    span = (end - start) / len(antardasha_lords)
    antardashas = []
    cursor = start
    for a_lord in antardasha_lords:
        a_end = cursor + span
        antardashas.append(Antardasha(lord=a_lord, start=cursor, end=a_end))
        cursor = a_end
    return Mahadasha(lord=lord, start=start, end=end, antardashas=antardashas)


def test_search_bounds_past_defaults_to_recency_window():
    # v18: "what happened in my past" defaults to recent life, not the
    # entire birth-to-now span — see _PAST_RECENCY_YEARS.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    from_dt, horizon_years = _search_bounds("past", birth_dt, now)
    assert horizon_years == pytest.approx(_PAST_RECENCY_YEARS)
    assert from_dt == now - timedelta(days=_PAST_RECENCY_YEARS * DAYS_PER_YEAR)


def test_search_bounds_past_recency_window_never_predates_birth():
    # A user younger than _PAST_RECENCY_YEARS: the recency window clamps to
    # their actual age instead of reaching before they were born.
    birth_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)  # age 6
    from_dt, horizon_years = _search_bounds("past", birth_dt, now)
    assert from_dt == birth_dt
    assert horizon_years == pytest.approx((now - birth_dt).days / DAYS_PER_YEAR)


def test_search_bounds_past_full_lifetime_still_available_explicitly():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    from_dt, horizon_years = _search_bounds("past", birth_dt, now, past_full_lifetime=True)
    assert from_dt == birth_dt
    assert horizon_years == pytest.approx((now - birth_dt).days / DAYS_PER_YEAR)


def test_search_bounds_future_starts_from_now_without_mahadashas():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    from_dt, horizon_years = _search_bounds("future", birth_dt, now)
    assert from_dt == now
    assert horizon_years == pytest.approx(_FUTURE_HORIZON_YEARS)


def test_search_bounds_future_starts_from_now_when_no_antardasha_is_currently_active():
    # `now` falls entirely outside the given timeline -> no current
    # Antardasha to anchor on, so this must fall back to "now" exactly like
    # the no-mahadashas case above.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 5, ["Ju"])  # ends 1995ish, long before "now"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    from_dt, horizon_years = _search_bounds("future", birth_dt, now, [maha])
    assert from_dt == now
    assert horizon_years == pytest.approx(_FUTURE_HORIZON_YEARS)


def test_search_bounds_future_starts_from_the_currently_running_antardashas_true_start():
    # Regression guard for the "straddling now" gap: a genuinely strong
    # window already running right now used to get clipped to only its
    # remaining tail in the future direction (and only its already-elapsed
    # portion in the past direction) — neither fragment reflecting its true
    # score. The future search must now start from where that Antardasha
    # ACTUALLY began, even though that's in the past relative to "now".
    birth_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 16, ["Ju", "Sa", "Me"])
    currently_running = maha.antardashas[1]
    now = currently_running.start + timedelta(days=100)  # partway through it
    assert currently_running.start < now < currently_running.end  # sanity-check the fixture

    from_dt, horizon_years = _search_bounds("future", birth_dt, now, [maha])
    assert from_dt == currently_running.start


def test_search_bounds_future_horizon_still_reaches_full_horizon_past_now():
    # Pulling from_dt backward to the current Antardasha's start must not
    # shrink the effective search horizon — it should still reach
    # +_FUTURE_HORIZON_YEARS from "now", just starting from an earlier point.
    birth_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 16, ["Ju", "Sa", "Me"])
    currently_running = maha.antardashas[1]
    now = currently_running.start + timedelta(days=100)

    from_dt, horizon_years = _search_bounds("future", birth_dt, now, [maha])
    horizon_end = from_dt + timedelta(days=horizon_years * DAYS_PER_YEAR)
    expected_end = now + timedelta(days=_FUTURE_HORIZON_YEARS * DAYS_PER_YEAR)
    assert abs((horizon_end - expected_end).total_seconds()) < 1.0


def _window_at_age(
    birth_dt: datetime, age_years: float, score: float, lord: str = "Ju", reason_keys: list[str] | None = None
) -> ScoredWindow:
    start = birth_dt + timedelta(days=age_years * DAYS_PER_YEAR)
    return ScoredWindow(
        start=start, end=start + timedelta(days=365), mahadasha_lord=lord, antardasha_lord=lord,
        score=score, reason_keys=reason_keys if reason_keys is not None else [],
    )


_NO_TRANSIT = TransitCheck(
    corroborated=False, corroboration_strength=1.0, corroborating_planet=None,
    obstructed=False, obstructing_planet=None, obstruction_fraction=0.0,
)


def test_resolve_past_windows_falls_back_to_full_lifetime_when_recent_pool_is_weak():
    # v18: recency-default search only covers the last _PAST_RECENCY_YEARS
    # by default (see _search_bounds) — but if that recent-only pool's best
    # candidate is still backdrop-only evidence, a genuinely strong window
    # further back must not be silently hidden, same lesson as v16's
    # future-horizon fix.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = birth_dt + timedelta(days=30 * DAYS_PER_YEAR)  # age 30
    weak_recent = _window_at_age(birth_dt, 25.0, score=1.0)  # no "_antardasha" key -> backdrop_only
    strong_old = _window_at_age(birth_dt, 10.0, score=5.0, reason_keys=["seventh_lord_antardasha"])

    calls = []

    def scan_and_select(from_dt, horizon_years):
        calls.append(horizon_years)
        if horizon_years == pytest.approx(_PAST_RECENCY_YEARS):
            return [weak_recent]
        return [strong_old]

    result = _resolve_past_windows("past", birth_dt, now, None, "marriage", scan_and_select)
    assert result == [strong_old]
    assert len(calls) == 2  # recency attempt, then the full-lifetime fallback


def test_resolve_past_windows_does_not_fall_back_when_recent_pool_is_already_good():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = birth_dt + timedelta(days=30 * DAYS_PER_YEAR)
    strong_recent = _window_at_age(birth_dt, 25.0, score=5.0, reason_keys=["seventh_lord_antardasha"])

    calls = []

    def scan_and_select(from_dt, horizon_years):
        calls.append(horizon_years)
        return [strong_recent]

    result = _resolve_past_windows("past", birth_dt, now, None, "marriage", scan_and_select)
    assert result == [strong_recent]
    assert len(calls) == 1  # no fallback call needed


def test_resolve_past_windows_future_direction_delegates_straight_through():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    now = birth_dt + timedelta(days=30 * DAYS_PER_YEAR)
    some_window = _window_at_age(birth_dt, 35.0, score=1.0)
    calls = []

    def scan_and_select(from_dt, horizon_years):
        calls.append(horizon_years)
        return [some_window]

    result = _resolve_past_windows("future", birth_dt, now, None, "marriage", scan_and_select)
    assert result == [some_window]
    assert len(calls) == 1


def test_select_candidate_pool_prefers_plausible_age_over_higher_raw_score():
    # Regression guard for the exact real-world gap this fix addresses: a
    # chart's own adolescence (age 5, "wealth" hard_floor=13) scoring higher
    # on raw dasha math than a comfortably plausible-age window (30) must
    # not crowd the plausible one out of the candidate pool before transit
    # corroboration or age weighting ever gets to consider it.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    implausible = _window_at_age(birth_dt, 5.0, score=10.0)
    plausible = _window_at_age(birth_dt, 30.0, score=1.0)
    pool = _select_candidate_pool([implausible, plausible], birth_dt, "wealth")
    assert pool == [plausible, implausible]


def test_select_candidate_pool_preserves_raw_score_order_within_each_bucket():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    plausible_strong = _window_at_age(birth_dt, 30.0, score=5.0)
    plausible_weak = _window_at_age(birth_dt, 40.0, score=1.0)
    implausible = _window_at_age(birth_dt, 5.0, score=10.0)
    pool = _select_candidate_pool([implausible, plausible_strong, plausible_weak], birth_dt, "wealth")
    assert pool == [plausible_strong, plausible_weak, implausible]


def test_select_candidate_pool_is_capped_at_the_candidate_pool_size():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    windows = [_window_at_age(birth_dt, 30.0 + i, score=1.0) for i in range(_CANDIDATE_POOL_SIZE + 5)]
    pool = _select_candidate_pool(windows, birth_dt, "wealth")
    assert len(pool) == _CANDIDATE_POOL_SIZE


def test_rerank_with_transit_bonus_never_lets_an_implausible_age_window_outrank_a_plausible_one():
    # Even a much higher effective score (bonus applied) at a hard-
    # implausible age must sort AFTER a plausible-age window with a lower
    # score — the age gate is a hard ordering constraint, not just a
    # multiplier that can still be outweighed by a strong enough score.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    implausible = _window_at_age(birth_dt, 63.0, score=10.0)  # children hard_ceiling=55
    plausible = _window_at_age(birth_dt, 25.0, score=0.5)
    pairs = [(implausible, _NO_TRANSIT), (plausible, _NO_TRANSIT)]
    ranked = _rerank_with_transit_bonus(pairs, birth_dt, "children")
    assert [w for w, _ in ranked][0] is plausible


def test_rerank_with_transit_bonus_still_returns_an_implausible_window_when_its_the_only_option():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    only_option = _window_at_age(birth_dt, 63.0, score=1.0)
    ranked = _rerank_with_transit_bonus([(only_option, _NO_TRANSIT)], birth_dt, "children")
    assert [w for w, _ in ranked] == [only_option]


def test_evidence_level_is_house_lord_antardasha_for_marriages_own_naming():
    # Marriage doesn't use the generic "{event}_house_lord_antardasha"
    # naming (see life_event_timing.py) — its house-lord key is
    # "seventh_lord_antardasha" (see marriage_rules).
    window = _window_at_age(
        datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 1.0, reason_keys=["seventh_lord_antardasha"]
    )
    assert _evidence_level(window) == "house_lord_antardasha"


def test_evidence_level_is_house_lord_antardasha_for_life_events_generic_naming():
    window = _window_at_age(
        datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 1.0, reason_keys=["wealth_house_lord_antardasha"]
    )
    assert _evidence_level(window) == "house_lord_antardasha"


def test_evidence_level_is_karaka_antardasha_for_a_karakas_own_antardasha():
    # Regression guard for the real gap this level distinguishes: a
    # karaka's own Antardasha (Venus for marriage) used to read identically
    # ("direct evidence") to the actual house lord's own Antardasha,
    # losing the classical distinction between "this IS the house of the
    # event" and "this planet ALSO happens to signify the event."
    marriage_karaka = _window_at_age(
        datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 1.0, reason_keys=["venus_antardasha"]
    )
    assert _evidence_level(marriage_karaka) == "karaka_antardasha"
    # Life-event's antardasha-level karaka key has the karaka code appended
    # (e.g. "wealth_karaka_antardasha_Ju") — a substring check, not endswith.
    life_event_karaka = _window_at_age(
        datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 1.0, reason_keys=["wealth_karaka_antardasha_Ju"]
    )
    assert _evidence_level(life_event_karaka) == "karaka_antardasha"


def test_evidence_level_is_backdrop_only_for_mahadasha_only_or_relationship_only_keys():
    # Regression guard for the exact real-world gap this fix addresses: a
    # window whose ONLY tie to the event is its broader Mahadasha (plus a
    # dasha-relationship note) is backdrop-only, not real evidence this
    # specific narrower window is about the event.
    backdrop_only = _window_at_age(
        datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 0.28,
        reason_keys=["wealth_karaka_mahadasha_Ju", "dasha_relationship_friend"],
    )
    assert _evidence_level(backdrop_only) == "backdrop_only"
    assert _evidence_level(_window_at_age(datetime(1990, 1, 1, tzinfo=timezone.utc), 30.0, 1.0)) == "backdrop_only"


def test_select_candidate_pool_prefers_direct_evidence_over_higher_raw_score():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    weak_but_high_score = _window_at_age(
        birth_dt, 30.0, score=10.0, reason_keys=["wealth_karaka_mahadasha_Ju"]
    )
    real_evidence = _window_at_age(
        birth_dt, 30.0, score=1.0, reason_keys=["wealth_house_lord_antardasha"]
    )
    pool = _select_candidate_pool([weak_but_high_score, real_evidence], birth_dt, "wealth")
    assert pool == [real_evidence, weak_but_high_score]


def test_select_candidate_pool_prefers_house_lord_evidence_over_karaka_evidence():
    # The new distinction this level adds: a karaka's own Antardasha (real
    # evidence, but a more generic signal) should still rank behind the
    # actual house lord's own Antardasha, even at a much higher raw score.
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    karaka_high_score = _window_at_age(
        birth_dt, 30.0, score=10.0, reason_keys=["wealth_karaka_antardasha_Ve"]
    )
    house_lord_low_score = _window_at_age(
        birth_dt, 30.0, score=1.0, reason_keys=["wealth_house_lord_antardasha"]
    )
    pool = _select_candidate_pool([karaka_high_score, house_lord_low_score], birth_dt, "wealth")
    assert pool == [house_lord_low_score, karaka_high_score]


def test_select_candidate_pool_prefers_plausible_karaka_window_over_implausible_house_lord_window():
    # The exact real case this fix addresses (see the module's v14 changelog
    # entry and _pool_priority's docstring): a hard-implausible-age window
    # that IS the house lord's own Antardasha must not beat a plausible-age
    # window that's only a karaka's own Antardasha — real ages/scores from
    # a live chart (marriage, hard_floor=15).
    birth_dt = datetime(2006, 10, 23, tzinfo=timezone.utc)
    implausible_house_lord = _window_at_age(
        birth_dt, 2.57, score=2.164, lord="Sa", reason_keys=["seventh_lord_antardasha"]
    )
    plausible_karaka = _window_at_age(
        birth_dt, 16.96, score=1.287, lord="Ve", reason_keys=["venus_antardasha"]
    )
    pool = _select_candidate_pool([implausible_house_lord, plausible_karaka], birth_dt, "marriage")
    assert pool == [plausible_karaka, implausible_house_lord]


def test_select_candidate_pool_prioritizes_age_plausibility_ahead_of_evidence():
    # Regression guard for a real bug found by comparing this engine's own
    # output against independent chart reads: evidence used to outrank age,
    # so a hard-implausible-age window with strong (house-lord) evidence
    # could beat a plausible-age window with merely real (karaka/backdrop)
    # evidence — one chart's "strongest past marriage period" was the 7th
    # lord's own Antardasha at age ~2.6 (reinterpreted as non-literal)
    # while a plausible-age Venus Antardasha sat unchosen in the same pool.
    # Age-plausibility must decide first; evidence only breaks ties within
    # the same age-plausibility bucket (see _pool_priority's docstring).
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    implausible_but_real = _window_at_age(
        birth_dt, 63.0, score=1.0, reason_keys=["children_house_lord_antardasha"]
    )
    plausible_but_backdrop_only = _window_at_age(
        birth_dt, 30.0, score=1.0, reason_keys=["children_karaka_mahadasha_Ju"]
    )
    pool = _select_candidate_pool(
        [implausible_but_real, plausible_but_backdrop_only], birth_dt, "children"
    )
    assert pool == [plausible_but_backdrop_only, implausible_but_real]


def test_rerank_with_transit_bonus_never_lets_a_backdrop_only_window_outrank_direct_evidence():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    backdrop_only_high_score = _window_at_age(
        birth_dt, 30.0, score=10.0, reason_keys=["wealth_karaka_mahadasha_Ju"]
    )
    real_evidence_low_score = _window_at_age(
        birth_dt, 30.0, score=0.5, reason_keys=["wealth_house_lord_antardasha"]
    )
    pairs = [(backdrop_only_high_score, _NO_TRANSIT), (real_evidence_low_score, _NO_TRANSIT)]
    ranked = _rerank_with_transit_bonus(pairs, birth_dt, "wealth")
    assert [w for w, _ in ranked][0] is real_evidence_low_score


def test_find_long_term_peak_surfaces_a_meaningfully_stronger_later_window():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    near = _window_at_age(birth_dt, 30.0, score=1.0, reason_keys=["career_house_lord_antardasha"])
    far_peak = _window_at_age(
        birth_dt, 45.0, score=1.0 * (_LONG_TERM_PEAK_MARGIN + 1), reason_keys=["career_house_lord_antardasha"]
    )
    pairs = [(near, _NO_TRANSIT), (far_peak, _NO_TRANSIT)]
    result = _find_long_term_peak(pairs, birth_dt, "career", top_window=near)
    assert result is not None
    assert result[0] is far_peak


def test_find_long_term_peak_returns_none_when_not_meaningfully_stronger():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    near = _window_at_age(birth_dt, 30.0, score=1.0, reason_keys=["career_house_lord_antardasha"])
    slightly_higher = _window_at_age(
        birth_dt, 45.0, score=1.05, reason_keys=["career_house_lord_antardasha"]
    )
    pairs = [(near, _NO_TRANSIT), (slightly_higher, _NO_TRANSIT)]
    assert _find_long_term_peak(pairs, birth_dt, "career", top_window=near) is None


def test_find_long_term_peak_ignores_a_weaker_evidence_tier_candidate():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    near = _window_at_age(birth_dt, 30.0, score=1.0, reason_keys=["career_house_lord_antardasha"])
    # Much higher raw score, but backdrop_only -> different bucket, must not
    # count as a "long-term peak" for the house-lord-level primary answer.
    far_but_weaker_tier = _window_at_age(birth_dt, 45.0, score=100.0, reason_keys=["career_karaka_mahadasha_Ju"])
    pairs = [(near, _NO_TRANSIT), (far_but_weaker_tier, _NO_TRANSIT)]
    assert _find_long_term_peak(pairs, birth_dt, "career", top_window=near) is None


def _antardasha_mahadasha(lord, start, years, antardasha_lords):
    return _mahadasha(lord, start, years, antardasha_lords)


def test_peak_window_for_narrows_to_matching_pratyantardashas():
    from app.astro.constants import VIMSHOTTARI_SEQUENCE

    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    # A Saturn Mahadasha whose FIRST Antardasha is Saturn's own (the actual
    # Vimshottari self-first order) — its Pratyantardashas then also start
    # from Saturn, so the first (shortest) PD sub-period is Sa's own.
    sequence_from_sa = VIMSHOTTARI_SEQUENCE[VIMSHOTTARI_SEQUENCE.index("Sa"):] + VIMSHOTTARI_SEQUENCE[
        : VIMSHOTTARI_SEQUENCE.index("Sa")
    ]
    maha = _antardasha_mahadasha("Sa", birth_dt, 19, sequence_from_sa)
    sa_antardasha = maha.antardashas[0]
    window = ScoredWindow(
        start=sa_antardasha.start, end=sa_antardasha.end, mahadasha_lord="Sa", antardasha_lord="Sa",
        score=1.0, reason_keys=["career_house_lord_antardasha"],
    )
    peak = _peak_window_for([maha], window, "career", house_lord_planet="Sa")
    assert peak is not None
    peak_start, peak_end = peak
    assert peak_start == window.start
    assert peak_end < window.end  # a real narrowing, not the whole window


def test_peak_window_for_returns_none_when_source_antardasha_not_found():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _antardasha_mahadasha("Sa", birth_dt, 19, ["Sa", "Me", "Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju"])
    mismatched_window = _window_at_age(birth_dt, 5.0, score=1.0, lord="Ve")  # doesn't match maha's own lord
    assert _peak_window_for([maha], mismatched_window, "career", house_lord_planet="Sa") is None


def test_delivery_anchor_window_finds_the_antardasha_covering_the_target_date():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 16, ["Ju", "Sa", "Me", "Ke", "Ve", "Su", "Mo", "Ma", "Ra"])
    target = maha.antardashas[2].start + timedelta(days=10)  # inside the 3rd Antardasha
    anchor = _delivery_anchor_window([maha], target)
    assert anchor is not None
    assert anchor.antardasha_lord == maha.antardashas[2].lord
    assert anchor.start == maha.antardashas[2].start
    assert anchor.end == maha.antardashas[2].end


def test_delivery_anchor_window_returns_none_outside_every_mahadasha():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 5, ["Ju"])  # ends ~1995
    far_future_target = birth_dt + timedelta(days=50 * DAYS_PER_YEAR)
    assert _delivery_anchor_window([maha], far_future_target) is None


# --- Phase 3: decision support -----------------------------------------

def test_history_nudge_fires_only_on_neutral_with_two_agreeing_priors():
    assert _history_nudge("neutral", ["favorable", "favorable"]) == "favorable"
    assert _history_nudge("neutral", ["unfavorable", "unfavorable"]) == "unfavorable"


def test_history_nudge_never_touches_a_clear_verdict():
    # A real, non-neutral verdict is NEVER overridden by history, no matter
    # how consistent the prior answers were — this is the core guardrail
    # the whole feature was scoped around.
    assert _history_nudge("favorable", ["unfavorable", "unfavorable"]) is None
    assert _history_nudge("unfavorable", ["favorable", "favorable"]) is None
    assert _history_nudge("wait_for_better_window", ["favorable", "favorable"]) is None


def test_history_nudge_requires_exactly_two_agreeing_priors():
    assert _history_nudge("neutral", []) is None
    assert _history_nudge("neutral", ["favorable"]) is None  # only one data point
    assert _history_nudge("neutral", ["favorable", "unfavorable"]) is None  # disagree
    assert _history_nudge("neutral", [None, None]) is None  # e.g. both were blocked/no-verdict calls


def test_dusthana_lords_returns_the_sixth_eighth_twelfth_house_lords():
    # Aries lagna (sign_index 0): 6th=Virgo(Me), 8th=Scorpio(Ma), 12th=Pisces(Ju).
    assert _dusthana_lords(0) == {"Me", "Ma", "Ju"}


def test_is_currently_dusthana_afflicted_true_when_running_antardasha_lord_is_dusthana():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 16, ["Sa", "Me", "Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju"])
    now = maha.antardashas[0].start + timedelta(days=10)  # inside the Sa antardasha
    assert _is_currently_dusthana_afflicted([maha], now, {"Sa"}) is True
    assert _is_currently_dusthana_afflicted([maha], now, {"Me", "Ma"}) is False


def test_is_currently_dusthana_afflicted_false_outside_every_mahadasha():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Ju", birth_dt, 5, ["Ju"])
    far_future = birth_dt + timedelta(days=50 * DAYS_PER_YEAR)
    assert _is_currently_dusthana_afflicted([maha], far_future, {"Ju"}) is False


def test_decision_reason_text_hides_dusthana_mechanics_by_default():
    """Regression guard for a real, explicit feedback item: naming the
    Antardasha lord and "dusthana (6th/8th/12th, the classical difficulty
    houses)" is HOW the chart arrives at the risk signal, not WHAT it means
    for the person — this should only surface when the user actually asks
    "why"/"which planet"/"what is my dasha", matching the same
    wants_technical_detail() convention already used elsewhere in this app.
    The real signal itself must still show up when asked; only the
    mechanical narration is gated."""
    from app.services.interpretation.prediction_templates import decision_reason_text

    hidden = decision_reason_text(
        "job_change", "unfavorable", "en", current_period_lord="Sa", dusthana_afflicted=True,
        better_window_start=None, history_nudge=None, history_dates=[],
    )
    assert "dusthana" not in hidden.lower()
    assert "antardasha" not in hidden.lower()

    shown = decision_reason_text(
        "job_change", "unfavorable", "en", current_period_lord="Sa", dusthana_afflicted=True,
        better_window_start=None, history_nudge=None, history_dates=[], include_mechanics=True,
    )
    assert "dusthana" in shown.lower()
    assert "saturn" in shown.lower()


def test_current_period_score_scores_the_antardasha_covering_now():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    maha = _mahadasha("Sa", birth_dt, 19, ["Sa", "Me", "Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju"])
    now = maha.antardashas[0].start + timedelta(days=10)  # Sa/Sa: house lord's own antardasha, same-lord bonus
    window = _current_period_score([maha], now, "career_promotion", house_lord_planet="Sa", strength={})
    assert window is not None
    assert window.mahadasha_lord == "Sa"
    assert window.antardasha_lord == "Sa"
    assert window.start == maha.antardashas[0].start
    assert window.end == maha.antardashas[0].end
    assert window.score > 0


def test_current_period_score_returns_none_when_no_rule_matches():
    birth_dt = datetime(1990, 1, 1, tzinfo=timezone.utc)
    # Mercury Mahadasha/Antardasha: not career_promotion's house lord (Sa),
    # not a career karaka (Sa/Su), and no secondary house lord either.
    maha = _mahadasha("Me", birth_dt, 17, ["Me"])
    now = maha.antardashas[0].start + timedelta(days=10)
    window = _current_period_score([maha], now, "career_promotion", house_lord_planet="Sa", strength={})
    assert window is None
