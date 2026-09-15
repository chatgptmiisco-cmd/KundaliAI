"""Generic transit-corroboration/obstruction check shared by
app.astro.marriage_timing and app.astro.life_event_timing: given a scored
dasha window and the house it's meant to activate, sample the relevant
planets' transiting positions across the window and report two independent
signals instead of one flat yes/no:

1. CORROBORATION: does one of the event's own classical "good transit"
   planets (Jupiter/Saturn for marriage; each event's karakas for life-event
   timing — see EVENT_KARAKAS in app.astro.life_event_timing) transit the
   target house during this window — and if so, how strong is THAT planet's
   own Ashtakavarga (Bhinnashtakavarga) bindu count at the sign it's
   transiting through (app.astro.ashtakavarga)? A transit through the
   classically right house with weak Ashtakavarga support is a real,
   different signal than one with strong support, not an unconditional
   "good transit" regardless of strength.

2. OBSTRUCTION: does a DIFFERENT natural malefic (any of
   app.astro.constants.NATURAL_MALEFICS not already playing the
   corroborating role for this event) actually OCCUPY the same house at the
   same time — a genuine classical caution, independent of whether the
   corroborating planets look good. Graded, not binary: reported as what
   FRACTION of the 3 sample points show some malefic occupying the house
   (0/3, 1/3, 2/3, or 3/3), not just whether it happened at least once. With
   3-4 malefic candidates and a window that can span several years, at
   least ONE of them occupying the house at at least ONE of 3 sample points
   turns out to be the common case in practice (observed ~70% of windows in
   a real multi-chart test), not the exception — a binary flag at that base
   rate stops differentiating anything. A fleeting 1/3 hit and a
   consistent 3/3 hit are real, different signals; only the latter should
   weigh heavily on the score (see prediction_service._TRANSIT_OBSTRUCTION_
   PENALTY, which now scales by this fraction).

OBSTRUCTION deliberately checks occupancy only, the SAME bar the positive
corroboration check above already uses — not the wider aspect (Parashari
drishti) net app.astro.natal_insights casts for NATAL strength. A malefic
casting its classical aspect from 2-3 houses away is a real but much softer
classical factor than one actually transiting through, and since a special-
aspect planet (Mars/Saturn) reaches 3-4 different houses from any one
position, an aspect-based check flags nearly every multi-year window purely
by chance — which stops being a meaningful signal that some windows have it
and others don't. Occupancy is rare and specific enough to actually
differentiate windows, the same reason the corroboration check above also
requires occupancy rather than merely an aspect.

OBSTRUCTION also deliberately excludes whatever planets are already the
corroborating planets for that event: this app already treats Saturn's
7th-house transit as a supportive marriage-timing signal, and Rahu's
12th-house transit as a supportive foreign-travel signal (both ARE natural
malefics, but that's a separate, already-established classical convention
for those specific events) — flagging the same transit as an obstruction
under a second rule would be double-counting one planet under contradictory
labels, not a real second opinion.
"""
from dataclasses import dataclass
from datetime import timedelta

from app.astro.ashtakavarga import ASHTAKAVARGA_PLANETS, ashtakavarga_strength_multiplier, compute_bav
from app.astro.constants import NATURAL_MALEFICS, PlanetKey
from app.astro.event_window_scanner import ScoredWindow
from app.astro.transits import TransitSnapshot, compute_transit_snapshot


@dataclass(frozen=True)
class TransitCheck:
    corroborated: bool
    # Ashtakavarga-derived strength of the corroborating planet's transit
    # (see app.astro.ashtakavarga.ashtakavarga_strength_multiplier) — 1.0
    # (no adjustment) when not corroborated, when natal data wasn't supplied,
    # or when the corroborating planet is Rahu/Ketu (no Ashtakavarga table).
    corroboration_strength: float
    corroborating_planet: PlanetKey | None
    obstructed: bool
    obstructing_planet: PlanetKey | None
    # Fraction (0.0-1.0) of the 3 sample points where SOME malefic occupied
    # the house — see the module docstring for why this is graded rather
    # than binary. `obstructed` is just `obstruction_fraction > 0`, kept as
    # a separate field for the reason-text trigger (mention it at all) while
    # `obstruction_fraction` drives how much it should actually weigh.
    obstruction_fraction: float


def _occupies(snapshot: TransitSnapshot, planet: PlanetKey, target_house: int) -> bool:
    return (
        snapshot.planet_house_from_lagna.get(planet) == target_house
        or snapshot.planet_house_from_moon.get(planet) == target_house
    )


def check_transits(
    window: ScoredWindow,
    target_house: int,
    corroborating_planets: tuple[PlanetKey, ...],
    lagna_sign_index: int,
    moon_sign_index: int,
    natal_planet_sign_index: dict[PlanetKey, int] | None = None,
) -> TransitCheck:
    """Samples the window's start, midpoint, and end (monthly-scale
    granularity is enough — every planet involved is a slow-to-moderate
    mover). Corroboration reports the FIRST matching planet found (one real
    hit is sufficient to call it corroborated at all — see
    `corroboration_strength` for how strong that specific hit is).
    Obstruction reports the fraction of all 3 points where some malefic
    occupied the house (see `TransitCheck.obstruction_fraction` and the
    module docstring for why this needs to be graded, not binary) — so,
    unlike corroboration, every sample point is checked even after the
    first obstruction hit. `natal_planet_sign_index` (all 7 classical
    planets' NATAL sign indices) is optional — without it,
    `corroboration_strength` stays at the neutral 1.0 rather than raising,
    since Ashtakavarga needs a full natal chart to compute and some callers
    (tests, or a future caller that doesn't have it handy) may not have
    one."""
    obstruction_candidates = tuple(NATURAL_MALEFICS - set(corroborating_planets))
    span = window.end - window.start
    sample_points = [window.start, window.start + span / 2, window.end - timedelta(seconds=1)]

    corroborating_planet: PlanetKey | None = None
    corroborating_sign: int | None = None
    obstructing_planet: PlanetKey | None = None
    obstructed_point_count = 0
    for at in sample_points:
        snapshot = compute_transit_snapshot(at, lagna_sign_index, moon_sign_index)
        if corroborating_planet is None:
            for planet in corroborating_planets:
                if (
                    snapshot.planet_house_from_lagna.get(planet) == target_house
                    or snapshot.planet_house_from_moon.get(planet) == target_house
                ):
                    corroborating_planet = planet
                    corroborating_sign = snapshot.planet_sign_index[planet]
                    break
        for planet in obstruction_candidates:
            if _occupies(snapshot, planet, target_house):
                if obstructing_planet is None:
                    obstructing_planet = planet
                obstructed_point_count += 1
                break

    corroboration_strength = 1.0
    has_full_natal_data = natal_planet_sign_index is not None and all(
        p in natal_planet_sign_index for p in ASHTAKAVARGA_PLANETS
    )
    if corroborating_planet in ASHTAKAVARGA_PLANETS and has_full_natal_data:
        bav = compute_bav(corroborating_planet, natal_planet_sign_index, lagna_sign_index)
        corroboration_strength = ashtakavarga_strength_multiplier(bav[corroborating_sign])

    return TransitCheck(
        corroborated=corroborating_planet is not None,
        corroboration_strength=corroboration_strength,
        corroborating_planet=corroborating_planet,
        obstructed=obstructed_point_count > 0,
        obstructing_planet=obstructing_planet,
        obstruction_fraction=obstructed_point_count / len(sample_points),
    )
