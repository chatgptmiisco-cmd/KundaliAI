from app.astro.constants import aspected_houses_from, planet_relation


def test_planet_relation_matches_classical_naisargika_maitri():
    assert planet_relation("Su", "Mo") == "friend"
    assert planet_relation("Su", "Sa") == "enemy"
    assert planet_relation("Su", "Me") == "neutral"  # Mercury is neutral toward the Sun


def test_planet_relation_is_not_always_symmetric():
    # The Moon has no classical enemies, but Saturn considers the Moon an
    # enemy — a real, well-documented asymmetry (Naisargika Maitri is
    # directional), not a bug to "fix" into a symmetric table.
    assert planet_relation("Sa", "Mo") == "enemy"
    assert planet_relation("Mo", "Sa") == "neutral"


def test_planet_relation_defaults_to_neutral_for_rahu_and_ketu():
    # Rahu/Ketu are deliberately absent from PLANET_FRIENDS/PLANET_ENEMIES —
    # same convention as EXALTATION_SIGN etc. — so they fall back to neutral
    # in both directions rather than raising a KeyError.
    assert planet_relation("Ra", "Su") == "neutral"
    assert planet_relation("Su", "Ke") == "neutral"
    assert planet_relation("Ra", "Ke") == "neutral"


def test_aspected_houses_from_gives_every_planet_the_universal_seventh_aspect():
    for planet in ("Su", "Mo", "Me", "Ve"):  # no special aspects for these
        assert aspected_houses_from(planet, house=1) == {7}
        assert aspected_houses_from(planet, house=10) == {4}  # 7th from house 10 wraps to house 4


def test_aspected_houses_from_gives_mars_its_classical_special_aspects():
    # Mars aspects the 4th, 7th, and 8th houses from itself.
    assert aspected_houses_from("Ma", house=1) == {4, 7, 8}


def test_aspected_houses_from_gives_jupiter_its_classical_special_aspects():
    # Jupiter aspects the 5th, 7th, and 9th houses from itself.
    assert aspected_houses_from("Ju", house=1) == {5, 7, 9}


def test_aspected_houses_from_gives_saturn_its_classical_special_aspects():
    # Saturn aspects the 3rd, 7th, and 10th houses from itself.
    assert aspected_houses_from("Sa", house=1) == {3, 7, 10}


def test_aspected_houses_from_gives_rahu_and_ketu_only_the_universal_aspect():
    # Deliberate simplification (see the module comment on
    # SPECIAL_ASPECT_HOUSES) — no special aspects claimed for the shadow
    # planets here, same convention as excluding them from EXALTATION_SIGN.
    assert aspected_houses_from("Ra", house=1) == {7}
    assert aspected_houses_from("Ke", house=1) == {7}


def test_aspected_houses_from_never_includes_the_planets_own_house():
    for planet in ("Su", "Ma", "Ju", "Sa"):
        for house in range(1, 13):
            assert house not in aspected_houses_from(planet, house)
