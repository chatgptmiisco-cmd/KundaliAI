"""Import every model module so Base.metadata is fully populated for
`create_all_tables()` (dev) and Alembic autogenerate (everywhere else)."""
from app.db.models.audit import AuditLog
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import (
    ChartCache,
    CompleteKundaliCache,
    DashaCache,
    HoroscopeCache,
    ManglikCache,
    PeriodAnalysisCache,
    UsageCounter,
)
from app.db.models.chat import ChatMessage
from app.db.models.life_state import LifeState
from app.db.models.prediction_query_log import PredictionQueryLog
from app.db.models.subscription import Subscription
from app.db.models.user import OtpRequest, User
from app.db.models.user_memory import UserMemoryNote

__all__ = [
    "AuditLog",
    "BirthProfile",
    "ChartCache",
    "CompleteKundaliCache",
    "DashaCache",
    "HoroscopeCache",
    "ManglikCache",
    "PeriodAnalysisCache",
    "UsageCounter",
    "ChatMessage",
    "LifeState",
    "PredictionQueryLog",
    "Subscription",
    "OtpRequest",
    "User",
    "UserMemoryNote",
]
