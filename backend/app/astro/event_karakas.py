"""Registry of which classical karaka (significator) each Prediction Engine
event category uses, and how "exclusive" each karaka is to its own
category — used to discount a merely-SHARED karaka's pull on a category
relative to that category's own house lord (always category-specific by
construction) or a karaka used nowhere else.

Jupiter alone is a classical karaka for wealth, children, AND foreign
travel (plus a co-karaka for marriage) — genuinely correct classically
(Guru signifies broad auspiciousness), and Venus is a karaka for both
marriage and wealth. That's real astrology, not a bug, but it means a
single strong Jupiter (or Venus) Antardasha can score highly across MOST
of this app's five event categories at once, since every category draws
from the exact same real dasha timeline. Verified empirically, not just
suspected: across a 20-chart test, 78% of user/direction combinations
(marriage + 4 life events, future + past) had at least one duplicate #1
window across categories — too high to be only the expected classical
overlap. This registry lets each category's own rule set (see
app.astro.marriage_timing.marriage_rules and
app.astro.life_event_timing.event_rules) scale down a SHARED karaka's
pull specifically, while leaving the category's OWN house lord and any
EXCLUSIVE karaka (Saturn/Sun for career, Rahu for foreign travel — each
used by exactly one category here) untouched, so a broadly-auspicious
planet's classical reach doesn't drown out what's actually distinctive
about a given category's own window.
"""
from app.astro.constants import PlanetKey

CATEGORY_KARAKAS: dict[str, tuple[PlanetKey, ...]] = {
    "marriage": ("Ve", "Ju"),
    "career": ("Sa", "Su"),
    "wealth": ("Ju", "Ve"),
    "children": ("Ju",),
    "foreign_travel": ("Ra", "Ju"),
}

_KARAKA_CATEGORY_COUNT: dict[PlanetKey, int] = {}
for _karakas in CATEGORY_KARAKAS.values():
    for _planet in _karakas:
        _KARAKA_CATEGORY_COUNT[_planet] = _KARAKA_CATEGORY_COUNT.get(_planet, 0) + 1

# A karaka used by only ONE category (Sa/Su for career, Ra for
# foreign_travel) is already fully category-discriminating — no discount.
# A karaka shared across 2+ categories (Ve, Ju) is a real classical signal
# but a generic one; discounting it shifts ranking weight toward whichever
# category a given real dasha window is more SPECIFICALLY tied to (via its
# own house lord, or an exclusive karaka) rather than letting the shared
# planet's broad strength win every category it touches identically.
_SHARED_KARAKA_MULTIPLIER = 0.6


def karaka_specificity_multiplier(planet: PlanetKey) -> float:
    return _SHARED_KARAKA_MULTIPLIER if _KARAKA_CATEGORY_COUNT.get(planet, 0) > 1 else 1.0
