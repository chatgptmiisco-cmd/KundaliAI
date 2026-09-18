from pydantic import BaseModel

_TOPICS = (
    "career", "business", "relationships", "marriage", "money", "family", "personal_direction", "other",
)


class LifeContextFactOut(BaseModel):
    id: int
    domain: str
    key: str
    value: str
    confidence: str
    source: str
    last_confirmed_at: str | None


class LifeDecisionOut(BaseModel):
    id: int
    decision_type: str
    context: str | None
    status: str
    final_choice: str | None
    outcome: str | None
    created_at: str


class MyLifeTwinResponse(BaseModel):
    """The whole "My Life Twin" screen's data in one call (product spec
    §14) — facts grouped by domain (not the raw flat list) since that's how
    they're meant to be shown, plus every decision (open and resolved) so
    the screen can show "Upcoming"/"Current Decision" sections too."""
    facts: dict[str, list[LifeContextFactOut]]
    decisions: list[LifeDecisionOut]


class CorrectFactIn(BaseModel):
    value: str


class LifeTimelineEntry(BaseModel):
    id: int
    event_type: str
    description: str
    year: int
    month: int | None


class OnboardingQA(BaseModel):
    question: str
    answer: str


class OnboardingContextIn(BaseModel):
    """Product spec §1-2 — the short post-signup topic pick + 2-4 follow-up
    questions, submitted together once the user finishes answering (the
    frontend asks them one at a time, but there's nothing to extract until
    the small set is complete)."""
    topic: str  # one of _TOPICS, enforced at the service layer rather than a strict Literal so an unrecognized value degrades to "other" instead of a 422
    qa_pairs: list[OnboardingQA]
    language: str = "en"
