"""Reverse geocode lat,lon to a display address (e.g. for dashboard). Uses Nominatim (OSM), cached."""
import asyncio
import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "KiteScope/1.0 (kite stream dashboard)"
# Nominatim usage policy: max 1 request per second
_reverse_cache: dict[tuple[float, float], str] = {}
_cache_lock = asyncio.Lock()


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 3), round(lon, 3))


async def reverse_geocode(lat: float, lon: float) -> str:
    """Return a short display address for lat,lon (e.g. 'Nanliao Fishing Port, Hsinchu'). Empty on failure. Cached."""
    key = _cache_key(lat, lon)
    async with _cache_lock:
        if key in _reverse_cache:
            return _reverse_cache[key]
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(
                NOMINATIM_URL,
                params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            )
            if r.status_code != 200:
                return ""
            data = r.json() or {}
            display = (data.get("display_name") or "").strip()
            async with _cache_lock:
                _reverse_cache[key] = display
            await asyncio.sleep(1)
            return display
    except Exception:
        return ""
