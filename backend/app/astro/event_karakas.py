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
    # business_partnership is a genuinely new domain (Mercury, the
    # classical trade/commerce karaka — distinct from marriage's Venus/
    # Jupiter even though both share the 7th house; see
    # prediction_service.get_life_event_timing's business_partnership
    # life-state gate for why these two don't read identically), so it's
    # counted for specificity like any other category below.
    "business_partnership": ("Me",),
}

_KARAKA_CATEGORY_COUNT: dict[PlanetKey, int] = {}
for _karakas in CATEGORY_KARAKAS.values():
    for _planet in _karakas:
        _KARAKA_CATEGORY_COUNT[_planet] = _KARAKA_CATEGORY_COUNT.get(_planet, 0) + 1

# career_promotion/business_expansion deliberately reuse their PARENT
# domain's own karaka set (a promotion IS a career event, not a second,
# unrelated category a planet could win independently) — added to
# CATEGORY_KARAKAS AFTER _KARAKA_CATEGORY_COUNT is computed, so they don't
# inflate Sa/Su's or Ju/Ve's cross-category count and silently start
# discounting the ALREADY-shipped career/wealth categories' own karaka
# rules purely because a sub-intent was added. They still get the correct
# multiplier at lookup time (karaka_specificity_multiplier reads the
# planet's real count from the parent domain either way).
CATEGORY_KARAKAS["career_promotion"] = CATEGORY_KARAKAS["career"]
CATEGORY_KARAKAS["business_expansion"] = CATEGORY_KARAKAS["wealth"]

# "property" (Phase 5, house_purchase_decision) — the standard convention:
# Mars (land) as the primary karaka, Saturn (stability/fixed assets) as a
# secondary one, paralleling marriage's Ve/Ju and career's Sa/Su. Added
# AFTER _KARAKA_CATEGORY_COUNT is computed for the SAME reason career_
# promotion/business_expansion are above: Saturn already has its own
# exclusive (count=1) role in career's already-shipped, already-tested
# scoring, and property being a brand-new category is the one that should
# absorb any cross-category-discount imprecision here, never career.
CATEGORY_KARAKAS["property"] = ("Ma", "Sa")

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
