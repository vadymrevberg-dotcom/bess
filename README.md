# Energy Arbitrage MVP – Poland (2026)

## What it does
- Fetches Day-Ahead electricity prices from TGE (RDN)
- Fetches hourly weather data (wind + solar) from Open-Meteo
- Produces a unified CSV for modeling price arbitrage

## Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
