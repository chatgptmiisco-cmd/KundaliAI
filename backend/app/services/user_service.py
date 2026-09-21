"""Birth profile CRUD (PII, encrypted at rest) and account deletion."""
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_pii_cipher
from app.db.models.audit import AuditLog
from app.db.models.birth_profile import BirthProfile
from app.db.models.life_state import LifeState
from app.db.models.user import User
from app.schemas.life_state import LifeStateIn, LifeStateOut
from app.schemas.user import BirthDataIn, BirthDataOut, UserProfileOut
from app.services.payments.subscription_service import get_or_create_subscription


async def get_birth_profile(db: AsyncSession, user_id: str) -> BirthProfile | None:
    result = await db.execute(select(BirthProfile).where(BirthProfile.user_id == user_id))
    return result.scalar_one_or_none()


def decrypt_birth_data(profile: BirthProfile) -> BirthDataOut:
    cipher = get_pii_cipher()
    return BirthDataOut(
        name=cipher.decrypt(profile.name_encrypted),
        date_of_birth=cipher.decrypt(profile.date_of_birth_encrypted),
        time_of_birth=cipher.decrypt(profile.time_of_birth_encrypted),
        time_uncertain=profile.time_uncertain,
        time_uncertainty_minutes=profile.time_uncertainty_minutes,
        place_of_birth=cipher.decrypt(profile.place_of_birth_encrypted),
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone_offset_hours=profile.timezone_offset_hours,
        version=profile.version,
    )


async def upsert_birth_profile(db: AsyncSession, user_id: str, data: BirthDataIn) -> BirthProfile:
    cipher = get_pii_cipher()
    existing = await get_birth_profile(db, user_id)

    if existing is None:
        profile = BirthProfile(
            user_id=user_id,
            name_encrypted=cipher.encrypt(data.name),
            date_of_birth_encrypted=cipher.encrypt(data.date_of_birth.isoformat()),
            time_of_birth_encrypted=cipher.encrypt(data.time_of_birth),
            time_uncertain=data.time_uncertain,
            time_uncertainty_minutes=data.time_uncertainty_minutes,
            place_of_birth_encrypted=cipher.encrypt(data.place_of_birth),
            latitude=data.latitude,
            longitude=data.longitude,
            timezone_offset_hours=data.timezone_offset_hours,
            version=1,
        )
        db.add(profile)
    else:
        profile = existing
        profile.name_encrypted = cipher.encrypt(data.name)
        profile.date_of_birth_encrypted = cipher.encrypt(data.date_of_birth.isoformat())
        profile.time_of_birth_encrypted = cipher.encrypt(data.time_of_birth)
        profile.time_uncertain = data.time_uncertain
        profile.time_uncertainty_minutes = data.time_uncertainty_minutes
        profile.place_of_birth_encrypted = cipher.encrypt(data.place_of_birth)
        profile.latitude = data.latitude
        profile.longitude = data.longitude
        profile.timezone_offset_hours = data.timezone_offset_hours
        # Bumping the version is what invalidates every cached chart/dasha/
        # horoscope/analysis row for this user — no cache row is ever deleted,
        # it just stops matching and is never selected again. A periodic
        # cleanup job pruning rows with stale versions would be a sensible
        # follow-up once this is under real load.
        profile.version += 1

    db.add(AuditLog(actor_user_id=user_id, subject_user_id=user_id, action="birth_profile.write"))
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_life_state(db: AsyncSession, user_id: str) -> LifeState | None:
    result = await db.execute(select(LifeState).where(LifeState.user_id == user_id))
    return result.scalar_one_or_none()


def decrypt_life_state(life_state: LifeState) -> LifeStateOut:
    cipher = get_pii_cipher()
    return LifeStateOut(
        marital_status=life_state.marital_status,
        marriage_date=cipher.decrypt(life_state.marriage_date_encrypted)
        if life_state.marriage_date_encrypted
        else None,
        children_count=life_state.children_count,
        pregnancy_status=life_state.pregnancy_status,
        expected_delivery=cipher.decrypt(life_state.expected_delivery_encrypted)
        if life_state.expected_delivery_encrypted
        else None,
        career_state=life_state.career_state,
        business_state=life_state.business_state,
        housing_status=life_state.housing_status,
        planning_property_purchase=life_state.planning_property_purchase,
        has_home_loan=life_state.has_home_loan,
        version=life_state.version,
    )


async def upsert_life_state(db: AsyncSession, user_id: str, data: LifeStateIn) -> LifeState:
    cipher = get_pii_cipher()
    existing = await get_life_state(db, user_id)

    marriage_date_encrypted = cipher.encrypt(data.marriage_date.isoformat()) if data.marriage_date else None
    expected_delivery_encrypted = (
        cipher.encrypt(data.expected_delivery.isoformat()) if data.expected_delivery else None
    )

    if existing is None:
        life_state = LifeState(
            user_id=user_id,
            marital_status=data.marital_status,
            marriage_date_encrypted=marriage_date_encrypted,
            children_count=data.children_count,
            pregnancy_status=data.pregnancy_status,
            expected_delivery_encrypted=expected_delivery_encrypted,
            career_state=data.career_state,
            business_state=data.business_state,
            housing_status=data.housing_status,
            planning_property_purchase=data.planning_property_purchase,
            has_home_loan=data.has_home_loan,
            version=1,
        )
        db.add(life_state)
    else:
        life_state = existing
        life_state.marital_status = data.marital_status
        life_state.marriage_date_encrypted = marriage_date_encrypted
        life_state.children_count = data.children_count
        life_state.pregnancy_status = data.pregnancy_status
        life_state.expected_delivery_encrypted = expected_delivery_encrypted
        life_state.career_state = data.career_state
        life_state.business_state = data.business_state
        life_state.housing_status = data.housing_status
        life_state.planning_property_purchase = data.planning_property_purchase
        life_state.has_home_loan = data.has_home_loan
        # Same staleness convention as BirthProfile.version — the Prediction
        # Engine stores this inside each cached row's JSON blob and treats a
        # mismatch as "recompute," so an edit here can't keep serving a
        # prediction framed for the user's OLD life state.
        life_state.version += 1

    db.add(AuditLog(actor_user_id=user_id, subject_user_id=user_id, action="life_state.write"))
    await db.commit()
    await db.refresh(life_state)
    return life_state


_VALID_MARITAL_STATUS = {"single", "dating", "engaged", "married", "divorced", "widowed"}
_VALID_PREGNANCY_STATUS = {"none", "expecting"}
_VALID_CAREER_STATE = {"employed", "unemployed", "student"}
_VALID_BUSINESS_STATE = {"none", "running", "considering"}
_VALID_HOUSING_STATUS = {"renting", "owns_property", "living_with_parents", "other"}


def _sanitize_life_state_fields(fields: dict) -> dict:
    """Drops (never coerces to a wrong default — a life-state fact wrongly
    set could misfire prediction_service's marriage/children/business
    redirect) any field the LLM populated with something outside the small
    fixed vocabulary, or a date string that doesn't actually parse — same
    "sanitize at the service boundary, don't let a bad LLM field crash the
    request" convention as life_context_service.upsert_fact's domain/
    confidence/source coercion."""
    clean: dict = {}
    if (v := fields.get("marital_status")) in _VALID_MARITAL_STATUS:
        clean["marital_status"] = v
    if (v := fields.get("pregnancy_status")) in _VALID_PREGNANCY_STATUS:
        clean["pregnancy_status"] = v
    if (v := fields.get("career_state")) in _VALID_CAREER_STATE:
        clean["career_state"] = v
    if (v := fields.get("business_state")) in _VALID_BUSINESS_STATE:
        clean["business_state"] = v
    if (v := fields.get("housing_status")) in _VALID_HOUSING_STATUS:
        clean["housing_status"] = v
    if isinstance(v := fields.get("planning_property_purchase"), bool):
        clean["planning_property_purchase"] = v
    if isinstance(v := fields.get("has_home_loan"), bool):
        clean["has_home_loan"] = v
    if isinstance(v := fields.get("children_count"), int) and v >= 0:
        clean["children_count"] = v
    for date_field in ("marriage_date", "expected_delivery"):
        if isinstance(v := fields.get(date_field), str):
            try:
                clean[date_field] = date.fromisoformat(v)
            except ValueError:
                pass
    return clean


async def apply_life_state_updates(db: AsyncSession, user_id: str, **fields) -> LifeState | None:
    """Partial-update path for LifeState, used by the chat pipeline (see
    chat_understanding.LifeStateUpdate) when the user states a life fact in
    conversation rather than filling in a settings form. `upsert_life_state`
    above is a deliberate full-replace (the settings-form contract: every
    field is resupplied every save, so an unset field really does mean
    "clear this"), which would silently wipe out unrelated fields — e.g. a
    known `career_state` — if reused directly for a chat update that only
    ever mentions ONE fact at a time. This reads the existing row (if any),
    overlays only the sanitized fields actually passed in `fields`, and
    routes the merged result through the existing `upsert_life_state` —
    additive, not a new write path around it."""
    clean_fields = _sanitize_life_state_fields(fields)
    if not clean_fields:
        return await get_life_state(db, user_id)
    existing = await get_life_state(db, user_id)
    current = decrypt_life_state(existing) if existing is not None else LifeStateOut(version=0)
    merged = current.model_copy(update=clean_fields)
    await upsert_life_state(db, user_id, LifeStateIn(**merged.model_dump(exclude={"version"})))
    return await get_life_state(db, user_id)


async def get_user_profile(db: AsyncSession, user: User) -> UserProfileOut:
    profile = await get_birth_profile(db, user.id)
    life_state = await get_life_state(db, user.id)
    subscription = await get_or_create_subscription(db, user.id)
    db.add(AuditLog(actor_user_id=user.id, subject_user_id=user.id, action="birth_profile.read"))
    await db.commit()

    return UserProfileOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        preferred_language=user.preferred_language,
        subscription_tier=subscription.tier,
        birth_data=decrypt_birth_data(profile) if profile else None,
        preferences=user.preferences,
        life_state=decrypt_life_state(life_state) if life_state else None,
    )


async def set_preferences(db: AsyncSession, user: User, preferences: list[str]) -> None:
    user.preferences = preferences
    await db.commit()


async def delete_account(db: AsyncSession, user_id: str) -> None:
    """Hard-deletes the user and every row that references them (birth
    profile, subscription, caches, chat history — all `ondelete=CASCADE`).
    The audit trail survives deletion (subject_user_id is a plain string, not
    a foreign key) so "who deleted what, when" remains provable."""
    db.add(AuditLog(actor_user_id=None, subject_user_id=user_id, action="account.delete"))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
