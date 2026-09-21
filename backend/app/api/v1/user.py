from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models.user import User
from app.schemas.life_context import (
    CorrectFactIn,
    LifeContextFactOut,
    LifeDecisionOut,
    LifeTimelineEntry,
    MyLifeTwinResponse,
    OnboardingContextIn,
)
from app.schemas.life_state import LifeStateIn
from app.schemas.personalization import NextOnboardingTopicOut, PersonalizationScoreOut
from app.schemas.user import BirthDataIn, PreferencesIn, UserProfileOut
from app.services import (
    life_context_service, onboarding_followup_service, personalization_score_service, user_service,
)
from app.services.chat_understanding import extract_onboarding_context

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile", response_model=UserProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await user_service.get_user_profile(db, user)


@router.put("/profile/birth-data", response_model=UserProfileOut)
async def update_birth_data(
    body: BirthDataIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await user_service.upsert_birth_profile(db, user.id, body)
    return await user_service.get_user_profile(db, user)


@router.put("/profile/life-state", response_model=UserProfileOut)
async def update_life_state(
    body: LifeStateIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await user_service.upsert_life_state(db, user.id, body)
    return await user_service.get_user_profile(db, user)


@router.put("/profile/preferences", response_model=UserProfileOut)
async def update_preferences(
    body: PreferencesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await user_service.set_preferences(db, user, body.preferences)
    return await user_service.get_user_profile(db, user)


@router.delete("/account", status_code=204)
async def delete_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await user_service.delete_account(db, user.id)


# --- "My Life Twin" (product spec §14-15) — see/correct/delete what the app
# remembers, since "the Life Twin belongs to the user," not a hidden database. ---


@router.get("/life-context", response_model=MyLifeTwinResponse)
async def get_my_life_twin(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    facts = await life_context_service.get_active_facts(db, user.id)
    grouped: dict[str, list[LifeContextFactOut]] = {}
    for f in facts:
        grouped.setdefault(f.domain, []).append(
            LifeContextFactOut(
                id=f.id, domain=f.domain, key=f.key, value=f.value,
                # Product spec §13 — Context Decay: the screen shows how much
                # the app currently trusts this fact, not the confidence it
                # was originally captured at, so a stale "employer" from 8
                # months ago visibly reads as lower-confidence than one
                # confirmed yesterday.
                confidence=life_context_service.effective_confidence(f.confidence, f.last_confirmed_at),
                source=f.source,
                last_confirmed_at=f.last_confirmed_at.isoformat() if f.last_confirmed_at else None,
            )
        )
    decisions = await life_context_service.get_all_decisions(db, user.id)
    return MyLifeTwinResponse(
        facts=grouped,
        decisions=[
            LifeDecisionOut(
                id=d.id, decision_type=d.decision_type, context=d.context, status=d.status,
                final_choice=d.final_choice, outcome=d.outcome, created_at=d.created_at.isoformat(),
            )
            for d in decisions
        ],
    )


@router.patch("/life-context/{item_id}", response_model=LifeContextFactOut)
async def correct_life_context_fact(
    item_id: int, body: CorrectFactIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    item = await life_context_service.correct_fact(db, user.id, item_id, body.value)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such remembered fact.")
    return LifeContextFactOut(
        id=item.id, domain=item.domain, key=item.key, value=item.value, confidence=item.confidence,
        source=item.source, last_confirmed_at=item.last_confirmed_at.isoformat() if item.last_confirmed_at else None,
    )


@router.delete("/life-context/{item_id}", status_code=204)
async def delete_life_context_fact(
    item_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    deleted = await life_context_service.delete_fact(db, user.id, item_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such remembered fact.")


@router.get("/life-timeline", response_model=list[LifeTimelineEntry])
async def get_life_timeline(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timeline = await life_context_service.get_timeline(db, user.id)
    return [LifeTimelineEntry(**e) for e in timeline]


@router.get("/personalization-score", response_model=PersonalizationScoreOut)
async def get_personalization_score(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await personalization_score_service.get_personalization_score(db, user.id)


@router.get("/next-onboarding-topic", response_model=NextOnboardingTopicOut)
async def get_next_onboarding_topic(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await onboarding_followup_service.get_next_onboarding_topic(db, user.id, user.created_at)
    return result or {"topic": None, "reason": None}


@router.post("/onboarding-context", status_code=status.HTTP_204_NO_CONTENT)
async def submit_onboarding_context(
    body: OnboardingContextIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Product spec §1-2 — the short post-signup topic pick + 2-4 follow-up
    answers, submitted together once the user finishes. Always records the
    topic itself as the user's main concern (goals.main_concern) even when
    AI extraction is off/unavailable, since that alone is a real, useful
    fact regardless of whether the richer per-answer extraction ran."""
    await life_context_service.upsert_fact(db, user.id, "goals", "main_concern", body.topic, "high", "user_stated")
    updates = await extract_onboarding_context(body.topic, [(qa.question, qa.answer) for qa in body.qa_pairs])
    for u in updates:
        await life_context_service.upsert_fact(db, user.id, u.domain, u.key, u.value, u.confidence, u.source)
