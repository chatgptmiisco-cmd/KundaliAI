"""Coverage for Phase 4's recurring-dasha-pattern detection (product spec's
"richer correlations") — see app.services.life_pattern_service. Every test
monkeypatches dasha_service.get_mahadashas_raw with a small fixed fixture
(mirroring how earlier phases monkeypatched other engine calls for
deterministic control) since the whole point is checking the CORRELATION
logic, not real ephemeris output.
"""
from datetime import datetime, timezone

from app.astro.dasha import Antardasha, Mahadasha
from app.db.base import AsyncSessionLocal
from app.services import dasha_service, life_context_service, life_pattern_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return profile.json()["id"]


def _fake_mahadashas():
    saturn = Mahadasha(
        lord="Sa", start=datetime(2010, 1, 1, tzinfo=timezone.utc), end=datetime(2029, 1, 1, tzinfo=timezone.utc),
        antardashas=[
            Antardasha(lord="Ve", start=datetime(2010, 1, 1, tzinfo=timezone.utc), end=datetime(2013, 1, 1, tzinfo=timezone.utc)),
            Antardasha(lord="Su", start=datetime(2013, 1, 1, tzinfo=timezone.utc), end=datetime(2014, 1, 1, tzinfo=timezone.utc)),
        ],
    )
    jupiter = Mahadasha(
        lord="Ju", start=datetime(2029, 1, 1, tzinfo=timezone.utc), end=datetime(2045, 1, 1, tzinfo=timezone.utc),
        antardashas=[
            Antardasha(lord="Me", start=datetime(2029, 1, 1, tzinfo=timezone.utc), end=datetime(2032, 1, 1, tzinfo=timezone.utc)),
        ],
    )
    return [saturn, jupiter]


async def test_returns_none_with_fewer_than_two_matching_events(client, monkeypatch):
    async def _fake(*a, **k):
        return _fake_mahadashas()
    monkeypatch.setattr(dasha_service, "get_mahadashas_raw", _fake)
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2011)
        result = await life_pattern_service.get_recurring_dasha_pattern(db, None, None, user_id, "career")
        assert result is None


async def test_returns_none_when_events_land_under_different_lords(client, monkeypatch):
    # Both years must stay in the real past (add_event clamps anything past
    # the current year to it — see life_context_service.add_event), so this
    # uses its own two-Mahadasha fixture rather than the shared future-
    # reaching one above.
    def _fixture():
        return [
            Mahadasha(
                lord="Ve", start=datetime(2005, 1, 1, tzinfo=timezone.utc), end=datetime(2011, 1, 1, tzinfo=timezone.utc),
                antardashas=[],
            ),
            Mahadasha(
                lord="Sa", start=datetime(2011, 1, 1, tzinfo=timezone.utc), end=datetime(2030, 1, 1, tzinfo=timezone.utc),
                antardashas=[],
            ),
        ]
    async def _fake(*a, **k):
        return _fixture()
    monkeypatch.setattr(dasha_service, "get_mahadashas_raw", _fake)
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        # 2008 -> Venus Mahadasha, 2015 -> Saturn Mahadasha: no shared lord.
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2008)
        await life_context_service.add_event(db, user_id, "promotion", "promoted", 2015)
        result = await life_pattern_service.get_recurring_dasha_pattern(db, None, None, user_id, "career")
        assert result is None


async def test_returns_a_hit_when_two_events_share_a_mahadasha_lord(client, monkeypatch):
    async def _fake(*a, **k):
        return _fake_mahadashas()
    monkeypatch.setattr(dasha_service, "get_mahadashas_raw", _fake)
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        # Both land in the Saturn Mahadasha (2010-2029), but different
        # Antardashas (2011 -> Venus, 2013 -> Sun) — so only the mahadasha
        # lord should be reported as shared, not the antardasha lord.
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2011)
        await life_context_service.add_event(db, user_id, "promotion", "promoted", 2013)
        result = await life_pattern_service.get_recurring_dasha_pattern(db, None, None, user_id, "career")
        assert result is not None
        assert result["shared_mahadasha_lord"] == "Sa"
        assert result["shared_mahadasha_count"] == 2
        assert result["shared_antardasha_lord"] is None
        assert result["occurrences"] == 2


async def test_returns_none_for_a_domain_with_no_matching_event_types(client, monkeypatch):
    async def _fake(*a, **k):
        return _fake_mahadashas()
    monkeypatch.setattr(dasha_service, "get_mahadashas_raw", _fake)
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2011)
        await life_context_service.add_event(db, user_id, "promotion", "promoted", 2013)
        # These are career events, not relationships ones.
        result = await life_pattern_service.get_recurring_dasha_pattern(db, None, None, user_id, "relationships")
        assert result is None
