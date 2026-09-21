from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.models.user import User
from app.schemas.geocode import GeocodeResult
from app.services.geocoding_service import search_places

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("/search", response_model=list[GeocodeResult])
@limiter.limit("30/minute")
async def geocode_search(
    request: Request, q: str = Query(min_length=3), _user: User = Depends(get_current_user)
):
    """"Place of birth" search-as-you-type (see app.services.geocoding_
    service) — real Google-geocoded results, proxied server-side so the API
    key never reaches the mobile app bundle. Returns [] rather than an error
    when Google isn't configured, so the frontend's own offline city table
    fallback (src/data/geocoding.ts) still works either way."""
    results = await search_places(q)
    return [GeocodeResult(**r) for r in results]
