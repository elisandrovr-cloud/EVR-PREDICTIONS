"""OpenWeather — game-time conditions per ballpark, with physical impact model."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.infrastructure.providers.base import BaseProvider

# Ballpark coordinates + altitude(m) + center-field bearing (degrees from north).
BALLPARKS: dict[str, dict[str, float]] = {
    "Angel Stadium": {"lat": 33.8003, "lon": -117.8827, "alt": 48, "cf_bearing": 65},
    "Minute Maid Park": {"lat": 29.7572, "lon": -95.3552, "alt": 15, "cf_bearing": 345},
    "Daikin Park": {"lat": 29.7572, "lon": -95.3552, "alt": 15, "cf_bearing": 345},
    "Oakland Coliseum": {"lat": 37.7516, "lon": -122.2005, "alt": 13, "cf_bearing": 55},
    "Sutter Health Park": {"lat": 38.5802, "lon": -121.5133, "alt": 6, "cf_bearing": 80},
    "Tropicana Field": {"lat": 27.7683, "lon": -82.6534, "alt": 13, "cf_bearing": 45},
    "George M. Steinbrenner Field": {"lat": 27.9803, "lon": -82.5067, "alt": 12, "cf_bearing": 70},
    "Yankee Stadium": {"lat": 40.8296, "lon": -73.9262, "alt": 16, "cf_bearing": 75},
    "Fenway Park": {"lat": 42.3467, "lon": -71.0972, "alt": 6, "cf_bearing": 55},
    "Rogers Centre": {"lat": 43.6414, "lon": -79.3894, "alt": 76, "cf_bearing": 15},
    "Oriole Park at Camden Yards": {"lat": 39.2839, "lon": -76.6217, "alt": 10, "cf_bearing": 30},
    "Guaranteed Rate Field": {"lat": 41.83, "lon": -87.6339, "alt": 180, "cf_bearing": 120},
    "Rate Field": {"lat": 41.83, "lon": -87.6339, "alt": 180, "cf_bearing": 120},
    "Progressive Field": {"lat": 41.4962, "lon": -81.6852, "alt": 200, "cf_bearing": 0},
    "Comerica Park": {"lat": 42.339, "lon": -83.0485, "alt": 183, "cf_bearing": 150},
    "Kauffman Stadium": {"lat": 39.0517, "lon": -94.4803, "alt": 229, "cf_bearing": 45},
    "Target Field": {"lat": 44.9817, "lon": -93.2776, "alt": 250, "cf_bearing": 90},
    "Truist Park": {"lat": 33.8908, "lon": -84.4678, "alt": 320, "cf_bearing": 145},
    "loanDepot park": {"lat": 25.7781, "lon": -80.2196, "alt": 3, "cf_bearing": 120},
    "Citi Field": {"lat": 40.7571, "lon": -73.8458, "alt": 6, "cf_bearing": 25},
    "Citizens Bank Park": {"lat": 39.9061, "lon": -75.1665, "alt": 6, "cf_bearing": 10},
    "Nationals Park": {"lat": 38.873, "lon": -77.0074, "alt": 8, "cf_bearing": 30},
    "Wrigley Field": {"lat": 41.9484, "lon": -87.6553, "alt": 182, "cf_bearing": 40},
    "Great American Ball Park": {"lat": 39.0974, "lon": -84.5065, "alt": 168, "cf_bearing": 120},
    "American Family Field": {"lat": 43.028, "lon": -87.9712, "alt": 180, "cf_bearing": 130},
    "PNC Park": {"lat": 40.4469, "lon": -80.0057, "alt": 226, "cf_bearing": 115},
    "Busch Stadium": {"lat": 38.6226, "lon": -90.1928, "alt": 141, "cf_bearing": 60},
    "Chase Field": {"lat": 33.4453, "lon": -112.0667, "alt": 331, "cf_bearing": 0},
    "Coors Field": {"lat": 39.7559, "lon": -104.9942, "alt": 1580, "cf_bearing": 15},
    "Dodger Stadium": {"lat": 34.0739, "lon": -118.24, "alt": 156, "cf_bearing": 25},
    "Petco Park": {"lat": 32.7073, "lon": -117.1566, "alt": 4, "cf_bearing": 25},
    "Oracle Park": {"lat": 37.7786, "lon": -122.3893, "alt": 3, "cf_bearing": 85},
    "T-Mobile Park": {"lat": 47.5914, "lon": -122.3325, "alt": 4, "cf_bearing": 45},
    "Globe Life Field": {"lat": 32.7473, "lon": -97.0847, "alt": 165, "cf_bearing": 65},
}

# Roofed parks where weather barely matters.
ROOFED = {"Minute Maid Park", "Daikin Park", "Tropicana Field", "Rogers Centre",
          "loanDepot park", "American Family Field", "Chase Field", "Globe Life Field", "T-Mobile Park"}


class WeatherProvider(BaseProvider):
    source_name = "openweather"
    base_url = settings.OPENWEATHER_API_BASE

    @property
    def enabled(self) -> bool:
        return bool(settings.OPENWEATHER_API_KEY)

    def conditions_for_venue(self, venue_name: str) -> dict[str, Any]:
        park = BALLPARKS.get(venue_name)
        if park is None:
            return {}
        base: dict[str, Any] = {"venue": venue_name, "altitude_m": park["alt"], "roofed": venue_name in ROOFED}
        if not self.enabled:
            return base
        raw = self._get(
            "/weather",
            params={"lat": park["lat"], "lon": park["lon"], "appid": settings.OPENWEATHER_API_KEY, "units": "metric"},
        )
        wind = raw.get("wind", {})
        main = raw.get("main", {})
        base.update(
            {
                "temperature_c": main.get("temp"),
                "humidity": main.get("humidity"),
                "pressure_hpa": main.get("pressure"),
                "wind_speed_ms": wind.get("speed"),
                "wind_deg": wind.get("deg"),
                "rain_probability": min(1.0, raw.get("rain", {}).get("1h", 0.0) / 5.0),
                "description": (raw.get("weather") or [{}])[0].get("description"),
            }
        )
        base["impact"] = self.impact_score(base, park["cf_bearing"])
        return base

    @staticmethod
    def impact_score(conditions: dict[str, Any], cf_bearing: float) -> dict[str, float]:
        """Expected run/HR impact multipliers from physics-informed heuristics."""
        if conditions.get("roofed"):
            return {"runs_multiplier": 1.0, "hr_multiplier": 1.0}
        runs = 1.0
        hr = 1.0
        temp = conditions.get("temperature_c")
        if temp is not None:
            # ~+0.8% carry per °C above 21C
            hr *= 1 + (temp - 21) * 0.008
            runs *= 1 + (temp - 21) * 0.004
        alt = conditions.get("altitude_m", 0) or 0
        hr *= 1 + alt / 1600 * 0.15
        runs *= 1 + alt / 1600 * 0.10
        speed = conditions.get("wind_speed_ms")
        deg = conditions.get("wind_deg")
        if speed is not None and deg is not None:
            import math

            # Positive component = wind blowing OUT toward center field.
            blowing_to = (deg + 180) % 360
            component = math.cos(math.radians(blowing_to - cf_bearing)) * speed
            hr *= 1 + component * 0.012
            runs *= 1 + component * 0.006
        return {"runs_multiplier": round(max(0.7, min(1.35, runs)), 3),
                "hr_multiplier": round(max(0.6, min(1.5, hr)), 3)}
