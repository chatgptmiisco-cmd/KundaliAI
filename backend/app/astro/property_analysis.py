"""Phase 8 — the natal "property_promise" assessment for house-purchase
questions: a genuinely different concern from TIMING (see prediction_
service.get_property_analysis for the window-scanning half) — this is
purely "does the D1 chart classically support property/home acquisition
at all," independent of when.

Every rule returned here is explicitly tagged classical or derived — see
PropertyRuleEvidence. Primary classical grounding used:
  - FOURTH_HOUSE_DOMAIN: the 4th house (Bandhu Bhava) is the classical
    house of home, land, and residence.
  - PHALADEEPIKA_20_5 / PHALADEEPIKA_20_16: favorable/difficult results
    tied to the 4th lord's own strength.
The "supported/mixed/weak" synthesis itself (combining dignity + affliction
into one status) is OUR OWN derived judgment call, built ON those classical
dignity concepts but not itself a verse — tagged PROPERTY_PROMISE_SCORING,
never presented as scripture. Never "guaranteed": astrology cannot
establish a guaranteed real-world transaction, only how classically
supported the underlying promise is (see PropertyPromiseStatus — no
"guaranteed" status exists by design).

Planets occupying the 4th house and Mars's own dignity (the traditional
land/property karaka) are deliberately NOT folded into this status — there
is no cited classical weighting for exactly how much an occupant should
shift the reading, and inventing one would violate the "document your
scoring, never invent it" rule. They're surfaced as separate, informational
`property_factors` by the caller instead (see prediction_service), so a
consumer can see them without this function silently mixing them into one
opaque number.
"""
from dataclasses import dataclass
from typing import Literal

from app.astro.constants import PlanetKey
from app.astro.natal_insights import Dignity

PropertyPromiseStatus = Literal["supported", "mixed", "weak"]


@dataclass(frozen=True)
class PropertyRuleEvidence:
    rule_id: str
    type: Literal["classical", "derived"]
    description: str
    source: str | None = None
    chapter: int | None = None
    verses: str | None = None


FOURTH_HOUSE_DOMAIN = PropertyRuleEvidence(
    rule_id="FOURTH_HOUSE_DOMAIN", type="classical",
    source="Classical principle (4th house / Bandhu Bhava)",
    description="The 4th house governs home, land, residence, and domestic happiness.",
)
PHALADEEPIKA_FAVORABLE = PropertyRuleEvidence(
    rule_id="PHALADEEPIKA_20_5", type="classical", source="Phaladeepika", chapter=20, verses="5",
    description=(
        "Favorable results are associated with the 4th lord's own Dasha/Antardasha "
        "when the 4th lord is strong."
    ),
)
PHALADEEPIKA_DIFFICULT = PropertyRuleEvidence(
    rule_id="PHALADEEPIKA_20_16", type="classical", source="Phaladeepika", chapter=20, verses="16",
    description=(
        "Difficult results are associated with the 4th lord's own Dasha/Antardasha "
        "when the 4th lord is weak or afflicted."
    ),
)
PROPERTY_PROMISE_SCORING = PropertyRuleEvidence(
    rule_id="PROPERTY_PROMISE_SCORING", type="derived",
    description=(
        "This engine's own synthesis of 4th-lord dignity/affliction into a supported/"
        "mixed/weak reading — built on classical dignity concepts, not itself a classical verse."
    ),
)
BPHS_48_2_4 = PropertyRuleEvidence(
    rule_id="BPHS_48_2_4", type="classical", source="Brihat Parashara Hora Shastra", chapter=48, verses="2-4",
    description="The Dasha of the lord of the 4th house (Bandhu Bhava) is associated with acquisition of house and land.",
)
PROPERTY_KARAKA_MARS_SATURN = PropertyRuleEvidence(
    rule_id="PROPERTY_KARAKA_MARS_SATURN", type="derived",
    description=(
        "Mars (land) and Saturn (stability/fixed assets) read here as SUPPORTING, not "
        "primary, significators — a widely-used convention, not a specific cited verse; "
        "the 4th house and 4th lord remain the primary classical framework."
    ),
)
PROPERTY_TIMING_WINDOWS = PropertyRuleEvidence(
    rule_id="PROPERTY_TIMING_WINDOWS", type="derived",
    description=(
        "This engine's window-ranking/confidence scoring is built on top of BPHS_48_2_4 "
        "but the score itself is engineering, not scripture."
    ),
)
D4_CONFIRMATION = PropertyRuleEvidence(
    rule_id="D4_CONFIRMATION", type="derived",
    description=(
        "The 4th lord's dignity in the Chaturthamsha (D4) chart — the classical property/"
        "fixed-assets divisional chart — corroborates the D1 promise. Used only to "
        "reinforce a non-weak D1 reading, never to override a weak one."
    ),
)
# Phase 9 — property_sale/property_inheritance/property_relocation reuse the
# SAME BPHS_48_2_4 4th-house-lord-dasha signal, reinterpreted by context
# rather than computed differently (per explicit approval — no new citation
# for these 3). BPHS_48_2_4's own description only ever names "acquisition"
# (what the classical verse actually says) — these entries disclose
# transparently that the SAME signal is being read for a different
# property-related question, rather than silently relabeling the citation
# itself to claim something the verse didn't say.
PROPERTY_INTENT_REFRAME_SALE = PropertyRuleEvidence(
    rule_id="PROPERTY_INTENT_REFRAME_SALE", type="derived",
    description=(
        "This reading reuses the same 4th-house-lord dasha activation BPHS_48_2_4 grounds "
        "for property acquisition, reinterpreted here for a sale question — the classical "
        "verse itself only names acquisition; reusing the same activation signal for a "
        "related but different property event is this engine's own extension."
    ),
)
PROPERTY_INTENT_REFRAME_INHERITANCE = PropertyRuleEvidence(
    rule_id="PROPERTY_INTENT_REFRAME_INHERITANCE", type="derived",
    description=(
        "This reading reuses the same 4th-house-lord dasha activation BPHS_48_2_4 grounds "
        "for property acquisition, reinterpreted here for an inheritance question — some "
        "traditions read inheritance via a different house; this engine deliberately does "
        "not assert that separate rule without its own citation, and only reframes the "
        "existing 4th-house signal."
    ),
)
PROPERTY_INTENT_REFRAME_RELOCATION = PropertyRuleEvidence(
    rule_id="PROPERTY_INTENT_REFRAME_RELOCATION", type="derived",
    description=(
        "This reading reuses the same 4th-house-lord dasha activation BPHS_48_2_4 grounds "
        "for property acquisition, reinterpreted here as a change of residence — a 4th-house "
        "(home) matter distinct from Phase 3's relocation_decision, which reads the 12th "
        "house for moving countries, not homes."
    ),
)


@dataclass(frozen=True)
class PropertyPromise:
    status: PropertyPromiseStatus
    evidence: list[PropertyRuleEvidence]


def compute_property_promise(
    fourth_lord_dignity: Dignity,
    fourth_lord_combust: bool,
    fourth_lord_d4_dignity: Dignity | None = None,
) -> PropertyPromise:
    """`fourth_lord_d4_dignity` (Phase 9): the 4th lord's dignity in the
    Chaturthamsha (D4) chart, when computable (see app.astro.vargas.
    chaturthamsa_sign_index) — None when the D1 chart's degree-in-sign
    isn't available (old cached rows), in which case D4 is honestly
    skipped, never guessed. Per explicit instruction, D4 confirmation
    (exalted/own-sign) may only ever REINFORCE a non-weak reading — it can
    upgrade "mixed" to "supported", and adds corroborating evidence to an
    already-"supported" one, but it NEVER touches a "weak" D1 promise."""
    evidence: list[PropertyRuleEvidence] = [FOURTH_HOUSE_DOMAIN]

    if fourth_lord_dignity == "debilitated" or fourth_lord_combust:
        status: PropertyPromiseStatus = "weak"
        evidence.append(PHALADEEPIKA_DIFFICULT)
    elif fourth_lord_dignity in ("exalted", "own_sign"):
        status = "supported"
        evidence.append(PHALADEEPIKA_FAVORABLE)
    else:
        status = "mixed"

    d4_confirmed = fourth_lord_d4_dignity in ("exalted", "own_sign")
    if status != "weak" and d4_confirmed:
        status = "supported"
        evidence.append(D4_CONFIRMATION)

    evidence.append(PROPERTY_PROMISE_SCORING)
    return PropertyPromise(status=status, evidence=evidence)
