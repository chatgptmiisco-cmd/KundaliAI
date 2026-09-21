from typing import Literal

from pydantic import BaseModel

from app.schemas.prediction import LifeEventWindow, LongTermPeak

# Forward-documented intent vocabulary (spec §10) — 4 have real logic behind
# them (see prediction_service.get_property_analysis): "property_purchase"
# (Phase 8) plus "property_sale"/"property_inheritance"/"property_relocation"
# (Phase 9 — the SAME BPHS 48.2-4 signal, reinterpreted by context, per the
# explicit approval to do so without a new citation). The remaining 4
# (construction/renovation/dispute/investment) have no cited classical rule
# yet — any of those gets a clear "not yet supported" response, never a
# guess routed through the purchase logic.
PropertyIntent = Literal[
    "property_purchase", "property_sale", "property_construction", "property_renovation",
    "property_inheritance", "property_dispute", "property_relocation", "property_investment",
]
IMPLEMENTED_PROPERTY_INTENTS: tuple[PropertyIntent, ...] = (
    "property_purchase", "property_sale", "property_inheritance", "property_relocation",
)


class PropertyRuleEvidence(BaseModel):
    """See app.astro.property_analysis for the full citation list and the
    classical/derived discipline this is built to."""

    rule_id: str
    type: Literal["classical", "derived"]
    description: str
    source: str | None = None
    chapter: int | None = None
    verses: str | None = None


class PropertyPromise(BaseModel):
    """Natal-only assessment — never "guaranteed" (see PropertyPromiseStatus
    in app.astro.property_analysis): astrology cannot establish a
    guaranteed real-world transaction, only how classically supported the
    underlying promise is."""

    status: Literal["supported", "mixed", "weak"]
    evidence: list[PropertyRuleEvidence]


class PropertyD4Factors(BaseModel):
    """Phase 9 — the D4 (Chaturthamsha) refinement layer (see app.astro.
    vargas.chaturthamsa_sign_index and app.astro.property_analysis's
    D4_CONFIRMATION rule). `confirmed` only ever REINFORCES a non-weak D1
    property_promise — see compute_property_promise's docstring for why it
    can never override a weak one."""

    fourth_lord_d4_sign_index: int
    fourth_lord_d4_dignity: Literal["exalted", "debilitated", "own_sign", "neutral"]
    confirmed: bool


class PropertyFactors(BaseModel):
    """Raw technical facts behind the promise — supporting factors the
    product spec asks to expose separately rather than silently folded
    into one opaque score (see app.astro.property_analysis's own
    docstring on why Mars/occupancy aren't mixed into `property_promise`
    itself)."""

    fourth_lord: str
    fourth_lord_name: str
    fourth_lord_dignity: Literal["exalted", "debilitated", "own_sign", "neutral"]
    fourth_lord_combust: bool
    planets_in_fourth_house: list[str]
    mars_dignity: Literal["exalted", "debilitated", "own_sign", "neutral"]
    # None when the D1 chart's degree-in-sign isn't available (old cached
    # rows — see PlanetPlacement.degree_in_sign's own docstring) — honestly
    # omitted rather than fabricated, never a fake "not_implemented" label
    # now that D4 IS implemented (Phase 9).
    d4: PropertyD4Factors | None = None


class PropertyAnalysis(BaseModel):
    """Phase 8 (property_purchase) + Phase 9 (sale/inheritance/relocation —
    see PropertyIntent's own docstring). Named intent-neutrally since one
    structure now serves all 4 implemented intents, differing only in
    `intent` and the narrative framing inside `evidence`/reasoning text."""

    intent: PropertyIntent
    language: str
    property_promise: PropertyPromise | None = None
    property_factors: PropertyFactors | None = None
    current_period: LifeEventWindow | None = None
    next_relevant_window: LifeEventWindow | None = None
    medium_term_window: LifeEventWindow | None = None
    long_term_peak: LongTermPeak | None = None
    # The primary window's own already-computed score/confidence, relabeled
    # per spec §16 — never a new number invented alongside the real one.
    astro_strength: float | None = None
    event_confidence: Literal["strong", "moderate", "low"] | None = None
    evidence: list[PropertyRuleEvidence] = []
    # Populated only for a past-tense query (see message_mentions_past_tense)
    # — real historical windows, never a claim about which one "happened."
    historical_windows: list[LifeEventWindow] = []
    # Set (with everything else minimal/None) when a life-state gate fires
    # (e.g. already owns property and the message doesn't clarify another/
    # investment property for property_purchase, spec §9; or "sell" asked
    # with no indication of owning anything for property_sale) or when a
    # non-implemented intent was requested (spec §10) — never silently
    # answered as if it were a different question than what was asked.
    note: str | None = None
