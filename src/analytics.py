# src/analytics.py
"""
Analytics module for Energy Arbitrage MVP.

Responsible for:
- computing daily price spreads
- estimating battery arbitrage profit
- analyzing wind → price effect
"""

import pandas as pd
from typing import Dict




def compute_daily_spread(
    csv_path: str,
    target_date: str,
    top_n: int = 3,
) -> Dict[str, float]:
    """
    Compute Daily Spread for a given date.
    """

    df = pd.read_csv(csv_path)
    day_df = df[df["date"] == target_date]

    if len(day_df) < top_n * 2:
        raise ValueError("Not enough hourly data to compute spread")

    sorted_df = day_df.sort_values("price_pln_mwh")

    cheap_avg = sorted_df.head(top_n)["price_pln_mwh"].mean()
    expensive_avg = sorted_df.tail(top_n)["price_pln_mwh"].mean()

    return {
        "date": target_date,
        "cheap_avg": round(cheap_avg, 2),
        "expensive_avg": round(expensive_avg, 2),
        "daily_spread_pln_mwh": round(expensive_avg - cheap_avg, 2),
    }


def compute_theoretical_battery_profit(
    csv_path: str,
    battery_kwh: float = 10.0,
    efficiency: float = 0.9,
    top_n: int = 3,
) -> dict:
    """
    Compute theoretical battery arbitrage profit over entire dataset.
    """

    df = pd.read_csv(csv_path)

    total_profit = 0.0
    days = 0

    for date, day_df in df.groupby("date"):
        if len(day_df) < top_n * 2:
            continue

        sorted_df = day_df.sort_values("price_pln_mwh")

        cheap_avg = sorted_df.head(top_n)["price_pln_mwh"].mean()
        expensive_avg = sorted_df.tail(top_n)["price_pln_mwh"].mean()

        daily_spread = expensive_avg - cheap_avg
        if daily_spread <= 0:
            continue

        daily_profit = (
            daily_spread
            * (battery_kwh / 1000)  # kWh → MWh
            * efficiency
        )

        total_profit += daily_profit
        days += 1

    return {
        "days": days,
        "battery_kwh": battery_kwh,
        "efficiency": efficiency,
        "total_profit_pln": round(total_profit, 2),
        "avg_daily_profit_pln": round(total_profit / days, 2) if days else 0.0,
    }

def simulate_with_battery(
    prices_df: pd.DataFrame,
    consumption_series: pd.Series,
    battery_kwh: float,
    efficiency: float = 0.9,
    distribution_cost_kwh: float = 0.60,
) -> float:
    df = prices_df.copy()
    profit = 0.0

    cheap_hours = df["price_pln_mwh"].nsmallest(3).index
    expensive_hours = df["price_pln_mwh"].nlargest(3).index

    energy_per_hour = battery_kwh / 3

    # 🔋 CHARGE: we pay for energy from grid
    for h in cheap_hours:
        price = df.loc[h, "price_pln_mwh"] / 1000 + distribution_cost_kwh
        profit -= energy_per_hour * price

    # 🔌 DISCHARGE: we avoid buying energy from grid
    for h in expensive_hours:
        price = df.loc[h, "price_pln_mwh"] / 1000 + distribution_cost_kwh
        profit += energy_per_hour * price * efficiency

    return profit

    
def simulate_without_battery(prices_df, consumption_series, distribution_cost_kwh: float = 0.45):
    """
    Baseline scenario: no battery, all energy bought from grid.
    Returns daily cost in PLN (float).
    """
    df = prices_df.copy()
    # consumption_series: kWh per hour; price_pln_mwh → cost = MWh * price
    price_kwh = df["price_pln_mwh"] / 1000 + distribution_cost_kwh
    df["cost_pln"] = price_kwh * consumption_series

    total_cost = df["cost_pln"].sum()
    return round(total_cost, 2)

def compute_wind_price_effect(
    csv_path: str,
    wind_threshold: float = 8.0,
) -> dict:
    """
    Compute price difference when wind speed is above threshold.
    """

    df = pd.read_csv(csv_path)

    df["max_wind"] = df[
        ["warsaw_windspeed_10m", "poznan_windspeed_10m"]
    ].max(axis=1)

    high_wind = df[df["max_wind"] > wind_threshold]
    low_wind = df[df["max_wind"] <= wind_threshold]

    if high_wind.empty or low_wind.empty:
        raise ValueError("Not enough data for wind correlation analysis")

    avg_high = high_wind["price_pln_mwh"].mean()
    avg_low = low_wind["price_pln_mwh"].mean()

    delta = avg_high - avg_low
    delta_pct = (delta / avg_low) * 100

    return {
        "wind_threshold_m_s": wind_threshold,
        "avg_price_high_wind": round(avg_high, 2),
        "avg_price_low_wind": round(avg_low, 2),
        "price_delta_pln": round(delta, 2),
        "price_delta_pct": round(delta_pct, 2),
    }


def compute_waiting_cost(daily_profit_pln: float, months_delay: int) -> float:
    waiting_cost = daily_profit_pln * 30 * months_delay
    return round(waiting_cost, 2)


def simulate_without_battery_30d(prices_df, consumption_profile, distribution_cost_kwh: float = 0.45):
    total_cost_pln = 0.0
    for date in prices_df["date"].unique():
        day_df = prices_df[prices_df["date"] == date]
        cons = consumption_profile.reindex(day_df["hour"]).fillna(0)
        price_kwh = day_df["price_pln_mwh"].values / 1000 + distribution_cost_kwh
        cost_day = (cons.values * price_kwh).sum()

        total_cost_pln += cost_day
    return round(total_cost_pln, 2)


def simulate_with_battery_30d(prices_df, consumption_profile, battery_kwh, efficiency, distribution_cost_kwh: float = 0.45):
    total_profit_pln = 0.0
    for date in prices_df["date"].unique():
        day_df = prices_df[prices_df["date"] == date]
        day_prices = day_df.set_index("hour")[["price_pln_mwh"]]
        cons = consumption_profile.reindex(day_prices.index).fillna(0)
        total_profit_pln += simulate_with_battery(
            day_prices, cons, battery_kwh=battery_kwh, efficiency=efficiency, distribution_cost_kwh=distribution_cost_kwh
        )
    return round(total_profit_pln, 2)
