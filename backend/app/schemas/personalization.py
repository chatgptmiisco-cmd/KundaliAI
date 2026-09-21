from typing import Literal

from pydantic import BaseModel


class PersonalizationScoreOut(BaseModel):
    """See app.services.personalization_score_service for how each field
    is computed and weighted."""

    score: int
    domains_covered: int
    domains_total: int
    life_state_fields_set: int
    life_state_fields_total: int
    has_life_event: bool
    has_important_date: bool
    has_tracked_decision: bool


class NextOnboardingTopicOut(BaseModel):
    """See app.services.onboarding_followup_service.get_next_onboarding_
    topic for how this is chosen — both null when there's nothing worth
    asking about right now."""

    topic: str | None
    reason: Literal["life_event", "time_based"] | None
