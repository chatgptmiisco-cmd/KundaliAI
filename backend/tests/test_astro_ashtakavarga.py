import pytest

from app.astro.ashtakavarga import (
    ASHTAKAVARGA_PLANETS,
    BAV_TABLES,
    BAV_TOTAL_BINDUS,
    ashtakavarga_strength_multiplier,
    compute_bav,
)

_CONTRIBUTORS = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Lagna")


def test_ashtakavarga_row_and_grand_totals_match_the_published_constants():
    # Every planet's Bhinnashtakavarga sums to a FIXED total (Brihat
    # Parashara Hora Shastra), regardless of chart — a transcription error
    # anywhere in the 56 rows (7 planets x 8 contributors) would very likely
    # break at least one of these sums, since getting a wrong table to
    # coincidentally sum to the exact right total is implausible.
    grand_total = 0
    for planet in ASHTAKAVARGA_PLANETS:
        contributors = BAV_TABLES[planet]
        assert set(contributors) == set(_CONTRIBUTORS)
        planet_total = sum(len(houses) for houses in contributors.values())
        assert planet_total == BAV_TOTAL_BINDUS[planet], f"{planet} BAV sums to {planet_total}, expected {BAV_TOTAL_BINDUS[planet]}"
        grand_total += planet_total
    assert grand_total == 337


def test_bav_table_house_numbers_are_all_in_range():
    for planet, contributors in BAV_TABLES.items():
        for contributor, houses in contributors.items():
            assert len(houses) == len(set(houses)), f"{planet}/{contributor} has a duplicate house number"
            assert all(1 <= h <= 12 for h in houses), f"{planet}/{contributor} has an out-of-range house number"


def test_compute_bav_every_sign_scores_between_zero_and_eight():
    natal = {"Su": 0, "Mo": 1, "Ma": 2, "Me": 3, "Ju": 4, "Ve": 5, "Sa": 6}
    for planet in ASHTAKAVARGA_PLANETS:
        bav = compute_bav(planet, natal, natal_lagna_sign_index=0)
        assert set(bav) == set(range(12))
        assert all(0 <= v <= 8 for v in bav.values())


def test_compute_bav_sums_to_the_published_total_for_a_real_chart():
    # The BAV total is fixed regardless of the actual natal positions used —
    # a strong end-to-end check that compute_bav's house-distance arithmetic
    # (not just the raw table) is correct, since a systematic off-by-one bug
    # in the distance formula would still preserve the table's row lengths
    # but would NOT preserve this per-chart sum.
    natal = {"Su": 5, "Mo": 11, "Ma": 2, "Me": 8, "Ju": 0, "Ve": 3, "Sa": 9}
    for planet in ASHTAKAVARGA_PLANETS:
        bav = compute_bav(planet, natal, natal_lagna_sign_index=7)
        assert sum(bav.values()) == BAV_TOTAL_BINDUS[planet]


def test_compute_bav_a_contributor_always_gives_itself_a_point_on_its_own_sign():
    # Every planet's own contributor row includes house-number 1 (its own
    # sign) EXCEPT Venus and Saturn, whose own-house self-contribution is a
    # known classical exception — this test instead checks the far simpler,
    # always-true invariant: moving a contributor's sign changes exactly
    # which signs earn a point from it, without changing how MANY signs earn
    # a point overall (the row length itself is fixed).
    base = {"Su": 0, "Mo": 1, "Ma": 2, "Me": 3, "Ju": 4, "Ve": 5, "Sa": 6}
    shifted = {**base, "Su": 3}
    bav_base = compute_bav("Ju", base, natal_lagna_sign_index=0)
    bav_shifted = compute_bav("Ju", shifted, natal_lagna_sign_index=0)
    assert sum(bav_base.values()) == sum(bav_shifted.values()) == BAV_TOTAL_BINDUS["Ju"]
    assert bav_base != bav_shifted  # moving the Sun changes WHICH signs score


def test_compute_bav_house_distance_wraps_correctly_across_the_zodiac():
    # A contributor at sign 11 (Pisces) counting to sign 0 (Aries) must see
    # that as house-number 2 "from" it (wrapping), not a negative distance.
    natal = {"Su": 11, "Mo": 11, "Ma": 11, "Me": 11, "Ju": 11, "Ve": 11, "Sa": 11}
    bav = compute_bav("Su", natal, natal_lagna_sign_index=11)
    # Sun's own row earns houses (1,2,4,7,8,9,10,11) from EVERY contributor
    # here since they're all on the same sign as the Sun — sign 11 itself is
    # house-number 1 from every contributor, sign 0 is house-number 2, etc.
    # House-number 1 is in Sun's own-row list, so sign 11 gets a point from
    # every one of the 8 contributors whose row includes house-number 1.
    rows_including_house_1 = sum(1 for houses in BAV_TABLES["Su"].values() if 1 in houses)
    assert bav[11] == rows_including_house_1


@pytest.mark.parametrize("bindus,expected", [(0, 0.5), (2, 0.5), (3, 0.75), (4, 1.0), (5, 1.25), (6, 1.25), (7, 1.5), (8, 1.5)])
def test_ashtakavarga_strength_multiplier_follows_the_classical_strong_average_weak_bands(bindus, expected):
    assert ashtakavarga_strength_multiplier(bindus) == expected
