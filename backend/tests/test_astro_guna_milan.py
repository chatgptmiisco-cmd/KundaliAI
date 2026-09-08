from app.astro.guna_milan import compute_guna_milan


def test_koota_max_scores_sum_to_36():
    result = compute_guna_milan(
        moon_sign_a=0, moon_nakshatra_a=0, is_manglik_a=False,
        moon_sign_b=0, moon_nakshatra_b=0, is_manglik_b=False,
    )
    assert sum(k.max_score for k in result.kootas) == 36.0
    assert result.max_total == 36.0


def test_identical_charts_score_zero_on_tara_and_nadi_but_max_elsewhere():
    # Matching someone with your exact Moon nakshatra classically triggers
    # Tara Dosha (Janma tara) and Nadi Dosha — a real, well-known quirk of
    # the system, not a bug: everything ELSE maxes out, but those two don't.
    result = compute_guna_milan(
        moon_sign_a=3, moon_nakshatra_a=5, is_manglik_a=False,
        moon_sign_b=3, moon_nakshatra_b=5, is_manglik_b=False,
    )
    by_key = {k.key: k.score for k in result.kootas}
    assert by_key["tara"] == 0.0
    assert by_key["nadi"] == 0.0
    assert by_key["yoni"] == 4.0
    assert by_key["graha_maitri"] == 5.0
    assert by_key["gana"] == 6.0
    assert by_key["bhakoot"] == 7.0
    assert result.total_score == 1.0 + 2.0 + 0.0 + 4.0 + 5.0 + 6.0 + 7.0 + 0.0


def test_varna_is_role_direction_dependent_by_classical_design():
    # Aries (Kshatriya, rank 1) vs Gemini (Shudra, rank 3): A's rank >= B's
    # rank only in one direction.
    forward = compute_guna_milan(0, 0, False, 2, 2, False)
    reverse = compute_guna_milan(2, 2, False, 0, 0, False)
    forward_varna = next(k.score for k in forward.kootas if k.key == "varna")
    reverse_varna = next(k.score for k in reverse.kootas if k.key == "varna")
    assert forward_varna == 1.0
    assert reverse_varna == 0.0


def test_bhakoot_dosha_for_6_8_and_2_12_relationships():
    # Aries (0) and Virgo (5): diff = 5 -> 6-8 relationship -> dosha (0 points)
    result = compute_guna_milan(0, 0, False, 5, 12, False)
    bhakoot = next(k.score for k in result.kootas if k.key == "bhakoot")
    assert bhakoot == 0.0

    # Aries (0) and Leo (4): diff = 4 -> no dosha -> full points
    result2 = compute_guna_milan(0, 0, False, 4, 10, False)
    bhakoot2 = next(k.score for k in result2.kootas if k.key == "bhakoot")
    assert bhakoot2 == 7.0


def test_mangal_dosha_mismatch_flag():
    same = compute_guna_milan(0, 0, True, 1, 3, True)
    different = compute_guna_milan(0, 0, True, 1, 3, False)
    assert same.mangal_dosha_mismatch is False
    assert different.mangal_dosha_mismatch is True


def test_graha_maitri_same_lord_is_full_marks():
    # Cancer (3, lord Moon) and Cancer again -> same lord -> 5
    result = compute_guna_milan(3, 5, False, 3, 5, False)
    graha_maitri = next(k.score for k in result.kootas if k.key == "graha_maitri")
    assert graha_maitri == 5.0


def test_scores_vary_meaningfully_across_different_chart_pairs():
    # Sanity check that this isn't collapsing to one static number regardless
    # of input — the entire point of this engine.
    totals = set()
    pairs = [
        (0, 0, 1, 3), (2, 5, 7, 19), (4, 10, 9, 22), (6, 15, 11, 25), (8, 20, 1, 2),
    ]
    for sign_a, nak_a, sign_b, nak_b in pairs:
        result = compute_guna_milan(sign_a, nak_a, False, sign_b, nak_b, False)
        totals.add(result.total_score)
    assert len(totals) == len(pairs)
