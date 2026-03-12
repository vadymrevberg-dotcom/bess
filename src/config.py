# src/config.py
"""
Central configuration for the Energy Arbitrage MVP (Poland).

All external services, constants and runtime parameters
are defined here to keep the rest of the code clean and testable.
"""

from datetime import date
from zoneinfo import ZoneInfo

# ======================================================
# General
# ======================================================

# Timezone for Poland (important for DST handling)
TIMEZONE = ZoneInfo("Europe/Warsaw")

# Default date for pipeline run (ISO format: YYYY-MM-DD)
TODAY = date.today().isoformat()

# Network settings
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3       # for external APIs
RETRY_BACKOFF = 2.0   # seconds

# ======================================================
# ENTSO-E (Day-Ahead Prices)
# ======================================================

# IMPORTANT:
# Replace with your real ENTSO-E Web API token
ENTSOE_API_KEY = "74d08b9d-ea3f-490c-ad7d-d671ce671828"

ENTSOE_BASE_URL = "https://web-api.tp.entsoe.eu/api"

# ENTSO-E bidding zone for Poland
# (official ENTSO-E identifier)
PL_BIDDING_ZONE = "10YPL-AREA-----S"

# ENTSO-E document type for Day-Ahead prices
ENTSOE_DAY_AHEAD_DOCUMENT = "A44"

# ======================================================
# Weather (Open-Meteo)
# ======================================================

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Cities used for weather → price analysis
CITIES = {
    "Warsaw": {
        "lat": 52.2297,
        "lon": 21.0122,
    },
    "Poznan": {
        "lat": 52.4064,
        "lon": 16.9252,
    },
}

# Weather variables we explicitly depend on
WEATHER_VARIABLES = [
    "windspeed_10m",
    "shortwave_radiation",
]

# ======================================================
# FX (for MVP)
# ======================================================

# Fixed FX rate for MVP.
# Later this can be replaced by ECB or NBP API.
EUR_TO_PLN = 4.4
