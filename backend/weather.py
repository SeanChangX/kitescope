"""Fetch current weather for a location (Open-Meteo, no API key).
Location can be a place name (geocoded) or GPS "lat,lon". Returns kite-relevant data: temp, wind 10m/80m, condition.
We use Open-Meteo only; labels like 'cloudy' are our short names for WMO weather codes (e.g. 1-3 = partly cloudy), not a different API."""
import re
import httpx

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Optional "lat,lon" or "lat, lon" (decimal numbers)
COORDS_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

CURRENT_VARS = "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m,wind_speed_80m,wind_direction_80m"

# Compass directions (16 points); 0 = N, 90 = E, 180 = S, 270 = W
_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def _deg_to_compass(deg: int | float) -> str:
    if deg is None:
        return ""
    i = int((deg + 11.25) / 22.5) % 16
    return _COMPASS[i]


def _weather_code_to_short(code: int) -> str:
    """WMO weather code to short description (e.g. clear, cloudy, rain)."""
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    return "fair"


async def get_weather_for_location(location: str) -> str:
    """Return a short weather string for notifications, e.g. '22C, NE 12 km/h, cloudy'. Backward compatible."""
    d = await get_weather_detail(location)
    return d.get("text", "") if d else ""


async def get_weather_detail(location: str) -> dict | None:
    """Return full kite-relevant weather: temp_c, wind 10m/80m (speed + direction), weather_desc, and summary text."""
    location = (location or "").strip()
    if not location or len(location) > 200:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            lat, lon = None, None
            m = COORDS_PATTERN.match(location)
            if m:
                lat = float(m.group(1))
                lon = float(m.group(2))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    return None
            else:
                r = await client.get(GEO_URL, params={"name": location, "count": 1})
                if r.status_code != 200:
                    return None
                data = r.json()
                results = data.get("results") or []
                if not results:
                    return None
                lat = results[0].get("latitude")
                lon = results[0].get("longitude")
                if lat is None or lon is None:
                    return None
            r2 = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": CURRENT_VARS,
                    "timezone": "auto",
                },
            )
            if r2.status_code != 200:
                return None
            cur = (r2.json() or {}).get("current") or {}
            temp = cur.get("temperature_2m")
            if temp is None:
                return None
            code = cur.get("weather_code", 0)
            desc = _weather_code_to_short(code)
            ws10 = cur.get("wind_speed_10m")
            wd10 = cur.get("wind_direction_10m")
            ws80 = cur.get("wind_speed_80m")
            wd80 = cur.get("wind_direction_80m")
            dir10 = _deg_to_compass(wd10) if wd10 is not None else ""
            dir80 = _deg_to_compass(wd80) if wd80 is not None else ""
            temp_c = int(round(temp))
            parts = [f"{temp_c}C"]
            if ws10 is not None and dir10:
                parts.append(f"{dir10} {int(round(ws10))} km/h (10m)")
            elif ws10 is not None:
                parts.append(f"{int(round(ws10))} km/h (10m)")
            if ws80 is not None and dir80 and (ws10 is None or (ws80, wd80) != (ws10, wd10)):
                parts.append(f"{dir80} {int(round(ws80))} km/h (80m)")
            elif ws80 is not None and ws10 is None:
                parts.append(f"{int(round(ws80))} km/h (80m)")
            parts.append(desc)
            text = ", ".join(parts)
            return {
                "text": text,
                "temp_c": temp_c,
                "weather_desc": desc,
                "wind_speed_10m_kmh": round(ws10, 1) if ws10 is not None else None,
                "wind_direction_10m": dir10 or None,
                "wind_speed_80m_kmh": round(ws80, 1) if ws80 is not None else None,
                "wind_direction_80m": dir80 or None,
            }
    except Exception:
        return None
