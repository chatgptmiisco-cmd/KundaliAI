"""Birth profile CRUD (PII, encrypted at rest) and account deletion."""
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
        # Same staleness convention as BirthProfile.version — the Prediction
        # Engine stores this inside each cached row's JSON blob and treats a
        # mismatch as "recompute," so an edit here can't keep serving a
        # prediction framed for the user's OLD life state.
        life_state.version += 1

    db.add(AuditLog(actor_user_id=user_id, subject_user_id=user_id, action="life_state.write"))
    await db.commit()
    await db.refresh(life_state)
    return life_state


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
