import pytest

from app.astro.life_stage_plausibility import (
    age_plausibility_multiplier,
    is_hard_implausible_age,
    is_implausible_age,
)


@pytest.mark.parametrize("event_type", ["marriage", "career", "wealth", "children", "foreign_travel"])
def test_age_plausibility_multiplier_is_full_weight_in_the_middle_of_life(event_type):
    assert age_plausibility_multiplier(event_type, 30.0) == 1.0


def test_age_plausibility_multiplier_is_heavily_discounted_at_birth():
    # This is exactly the real bug this module fixes: a chart's very first
    # Antardasha (age ~0) used to be able to win "career"/"children" purely
    # on dasha math, with zero real-world sanity check.
    for event_type in ("marriage", "career", "wealth", "children"):
        assert age_plausibility_multiplier(event_type, 0.1) == pytest.approx(0.15)


def test_age_plausibility_multiplier_is_heavily_discounted_deep_into_old_age():
    assert age_plausibility_multiplier("marriage", 70.0) == pytest.approx(0.15)
    assert age_plausibility_multiplier("children", 65.0) == pytest.approx(0.15)


def test_age_plausibility_multiplier_ramps_smoothly_rather_than_a_hard_cutoff():
    # Just below the soft floor should score higher than right at the hard
    # floor, and lower than comfortably inside the band — a ramp, not a cliff.
    at_hard_floor = age_plausibility_multiplier("marriage", 15.0)
    midway = age_plausibility_multiplier("marriage", 17.0)
    at_soft_floor = age_plausibility_multiplier("marriage", 19.0)
    assert at_hard_floor < midway < at_soft_floor == 1.0


def test_age_plausibility_multiplier_foreign_travel_has_a_much_wider_band():
    # Foreign travel/relocation is plausible even for a child (family
    # relocation) or an older adult (work/retirement travel) — a much
    # gentler band than marriage/career/wealth/children.
    assert age_plausibility_multiplier("foreign_travel", 8.0) == 1.0
    assert age_plausibility_multiplier("foreign_travel", 70.0) == 1.0
    assert age_plausibility_multiplier("marriage", 8.0) < 1.0


def test_is_implausible_age_flags_early_and_late_but_not_the_typical_range():
    assert is_implausible_age("marriage", 5.0) == "early"
    assert is_implausible_age("marriage", 30.0) is None
    assert is_implausible_age("marriage", 55.0) == "late"


def test_is_hard_implausible_age_is_false_inside_the_hard_band():
    # 30 is comfortably inside every category's hard band, and even the
    # softer "late"/"early" edge (19, 45) for marriage is still inside the
    # HARD band (15-60) — is_hard_implausible_age is deliberately a much
    # stricter bar than is_implausible_age.
    for event_type in ("marriage", "career", "wealth", "children", "foreign_travel"):
        assert is_hard_implausible_age(event_type, 30.0) is False
    assert is_hard_implausible_age("marriage", 19.0) is False
    assert is_hard_implausible_age("marriage", 45.0) is False


def test_is_hard_implausible_age_is_true_at_and_beyond_the_hard_floor_and_ceiling():
    assert is_hard_implausible_age("wealth", 16.0) is True  # at the hard floor itself
    assert is_hard_implausible_age("wealth", 17.0) is False  # just past it
    assert is_hard_implausible_age("children", 63.0) is True  # hard_ceiling=55, so 63 is well beyond it
    assert is_hard_implausible_age("marriage", 60.0) is True  # at the hard ceiling itself
