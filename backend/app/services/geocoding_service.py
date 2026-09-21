"""Server-side proxy for Google Places API text search — powers the "Place
of birth" autocomplete (see app.api.v1.geocode). Proxied through this
backend rather than called directly from the app so the API key never ships
inside the mobile bundle, where it could be extracted from the JS bundle
and reused to run up billing on this project's Google account (unlike a
native SDK call, a plain fetch() from React Native can't be restricted by
app signature/bundle ID, so keeping the key server-side is the only real
protection).
"""
import httpx

from app.core.config import get_settings

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = "places.displayName,places.formattedAddress,places.location,places.addressComponents"
_MAX_RESULTS = 6

# Countries that sit on a single standard UTC offset year-round — mirrors
# the frontend's own former fallback table (src/data/geocoding.ts) for the
# same reason: large multi-timezone countries (US, Canada, Australia,
# Russia, Brazil, ...) deliberately aren't listed, since one flat offset
# would be wrong for much of them; those fall through to the longitude
# estimate below instead. Real historical DST rules aren't modeled either
# way — this is a best-effort estimate, not an authority.
_COUNTRY_OFFSET_HOURS: dict[str, float] = {
    "in": 5.5, "pk": 5, "bd": 6, "np": 5.75, "lk": 5.5, "mm": 6.5,
    "gb": 0, "ie": 0, "pt": 0,
    "fr": 1, "de": 1, "es": 1, "it": 1, "nl": 1, "be": 1, "ch": 1, "se": 1, "no": 1, "dk": 1, "pl": 1, "at": 1,
    "ae": 4, "sa": 3, "qa": 3, "kw": 3, "om": 4, "il": 2,
    "sg": 8, "my": 8, "hk": 8, "tw": 8, "ph": 8,
    "jp": 9, "kr": 9,
    "th": 7, "vn": 7, "id": 7,
    "nz": 12,
    "za": 2, "eg": 2, "ke": 3, "ng": 1,
}


def _estimate_timezone_offset_hours(country_code: str | None, longitude: float) -> float:
    known = _COUNTRY_OFFSET_HOURS.get(country_code.lower()) if country_code else None
    if known is not None:
        return known
    return round(longitude / 15)


async def search_places(query: str) -> list[dict]:
    """[{"display_name", "latitude", "longitude", "timezone_offset_hours"}, ...] —
    empty when GOOGLE_PLACES_API_KEY isn't configured, letting the frontend
    fall back to its own offline city table (see src/data/geocoding.ts's
    resolveBirthPlace)."""
    settings = get_settings()
    if not settings.google_places_api_key:
        return []

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.google_places_api_key,
                "X-Goog-FieldMask": _FIELD_MASK,
            },
            json={"textQuery": query},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for place in data.get("places", [])[:_MAX_RESULTS]:
        location = place.get("location")
        if not location or "latitude" not in location or "longitude" not in location:
            continue
        country_code = next(
            (c.get("shortText") for c in place.get("addressComponents", []) if "country" in c.get("types", [])),
            None,
        )
        longitude = location["longitude"]
        display_name = place.get("formattedAddress") or place.get("displayName", {}).get("text") or query
        results.append({
            "display_name": display_name,
            "latitude": location["latitude"],
            "longitude": longitude,
            "timezone_offset_hours": _estimate_timezone_offset_hours(country_code, longitude),
        })
    return results
