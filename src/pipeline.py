# src/pipeline.py
"""
Data pipeline for merging Day-Ahead prices and weather data
into a unified hourly CSV dataset.
"""

import csv
from typing import List, Dict


def merge_price_and_weather(
    prices: List[Dict],
    weather: Dict[str, Dict[int, Dict[str, float]]],
    output_path: str,
) -> None:
    """
    Merge price and weather data and save to CSV.

    Args:
        prices: list of price records:
            [
                {
                    "date": "YYYY-MM-DD",
                    "hour": 1..N,
                    "price_pln_mwh": float
                }
            ]

        weather:
            {
                "Warsaw": {hour -> {weather_var: value}},
                "Poznan": {hour -> {weather_var: value}}
            }

        output_path: path to output CSV
    """

    if not prices:
        raise ValueError("No price data provided to pipeline")

    date = prices[0]["date"]

    # Determine full set of hours present in price data
    hours = sorted({row["hour"] for row in prices})

    rows = []

    for hour in hours:
        price_row = next(
            (p for p in prices if p["hour"] == hour),
            None,
        )

        if price_row is None:
            continue

        row = {
            "date": date,
            "hour": hour,
            "price_pln_mwh": price_row["price_pln_mwh"],
        }

        # Merge weather per city
        for city, city_weather in weather.items():
            weather_at_hour = city_weather.get(hour, {})

            for var, value in weather_at_hour.items():
                column = f"{city.lower()}_{var}"
                row[column] = value

        rows.append(row)

    if not rows:
        raise ValueError("No rows produced by pipeline")

    _write_csv(rows, output_path)


def _write_csv(rows: List[Dict], output_path: str) -> None:
    """
    Write rows to CSV with stable column order.
    """

    # Stable column order
    fieldnames = list(rows[0].keys())

    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
