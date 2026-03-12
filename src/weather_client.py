# src/weather_client.py
"""
Weather client based on Open-Meteo API.

Responsible for:
- fetching hourly weather data for selected cities
- returning a normalized hourly structure
- being robust to DST / missing hours
"""

import time
import requests
from typing import Dict

from config import (
    OPEN_METEO_BASE_URL,
    CITIES,
    WEATHER_VARIABLES,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF,
)


class WeatherClient:
    def __init__(self):
        self.session = requests.Session()

    def fetch_weather(self, date_iso: str) -> Dict:
        """
        Fetch hourly weather data for all configured cities.

        Args:
            date_iso: YYYY-MM-DD

        Returns:
            {
                "Warsaw": {
                    1: {"windspeed_10m": float, "shortwave_radiation": float},
                    2: {...},
                    ...
                },
                "Poznan": {
                    ...
                }
            }
        """
        results: Dict[str, Dict[int, Dict[str, float]]] = {}

        for city, coords in CITIES.items():
            results[city] = self._fetch_city_weather(
                city=city,
                lat=coords["lat"],
                lon=coords["lon"],
                date_iso=date_iso,
            )

        return results

    def _fetch_city_weather(
        self,
        city: str,
        lat: float,
        lon: float,
        date_iso: str,
    ) -> Dict[int, Dict[str, float]]:
        """
        Fetch weather for a single city and normalize by hour index.
        """

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(WEATHER_VARIABLES),
            "start_date": date_iso,
            "end_date": date_iso,
            "timezone": "Europe/Warsaw",
        }

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    OPEN_METEO_BASE_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
                return self._parse_hourly(payload)

            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
                else:
                    break

        raise RuntimeError(
            f"Open-Meteo request failed for {city} after "
            f"{MAX_RETRIES} attempts: {last_error}"
        )

    def _parse_hourly(self, payload: Dict) -> Dict[int, Dict[str, float]]:
        """
        Convert Open-Meteo hourly arrays into hour-indexed dict.

        Hour index:
        1 = 00:00–01:00
        24 = 23:00–00:00
        """

        hourly = payload.get("hourly")
        if not hourly:
            raise ValueError("No hourly data in Open-Meteo response")

        result: Dict[int, Dict[str, float]] = {}

        # Number of hourly points (can be 23/24/25 on DST days)
        hours_count = len(hourly.get("windspeed_10m", []))

        for idx in range(hours_count):
            hour = idx + 1

            record = {}
            for var in WEATHER_VARIABLES:
                values = hourly.get(var)
                record[var] = values[idx] if values and idx < len(values) else None

            result[hour] = record

        return result

