# src/main.py
"""
Main entry point for Energy Arbitrage MVP.
"""

from client_manual import CLIENT_HOME, CLIENT_BUSINESS
from load_profile import load_consumption_profile
from report import generate_pdf_report
from analytics import (
    simulate_without_battery_30d,
    simulate_with_battery_30d,
    compute_waiting_cost,
)
import pandas as pd

DATA_CSV = "data/output.csv"
EFFICIENCY = 0.9

PV_PROFILE = pd.Series(
    [0, 0, 0, 0, 0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.32, 0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.02, 0, 0, 0, 0],
    index=range(24)
)
PV_KWH_PER_KWP_DAY = 3.0

def main():
    clients = [("home", CLIENT_HOME), ("business", CLIENT_BUSINESS)]
    df = pd.read_csv(DATA_CSV)
    df["hour"] = df["hour"] - 1
    df = df[df["hour"].between(0, 23)]
    target_date = sorted(df["date"].unique())[-1]
    
    day_prices = df[df["date"] == target_date].set_index("hour").sort_index()
    if len(day_prices) != 24:
        raise ValueError(f"Incomplete day: {target_date}")

    print(f"▶ Using market date: {target_date}\n")

    for label, client in clients:
        print("▶ Client:", client)
        
        annual_kwh = client["annual_kwh"]
        battery_kwh = client["battery_kwh"]
        profile = client["profile"]
        pv_kwp = client.get("pv_kwp", 0)

        consumption = load_consumption_profile(profile_name=profile, annual_kwh=annual_kwh).loc[day_prices.index]
        pv_generation = PV_PROFILE * pv_kwp * PV_KWH_PER_KWP_DAY
        pv_generation = pv_generation.loc[day_prices.index]

        self_consumed = consumption.clip(upper=pv_generation)
        remaining_consumption = consumption - self_consumed
        pv_excess = pv_generation - self_consumed

        battery_charge_from_pv = min(pv_excess.sum(), battery_kwh)

        if remaining_consumption.sum() > 0 and battery_charge_from_pv > 0:
            battery_used = (remaining_consumption / remaining_consumption.sum()) * battery_charge_from_pv
            grid_consumption = remaining_consumption - battery_used
        else:
            grid_consumption = remaining_consumption

        available_dates = df["date"].unique()
        last_30_dates = sorted(available_dates)[-30:]
        df_30d = df[df["date"].isin(last_30_dates)]
        num_days = len(last_30_dates)

        cost_no_battery_period = simulate_without_battery_30d(df_30d, remaining_consumption)
        cost_pv_battery_period = simulate_without_battery_30d(df_30d, grid_consumption)
        
        available_for_arbitrage = max(0, battery_kwh - battery_charge_from_pv)
        arbitrage_profit_period = simulate_with_battery_30d(df_30d, grid_consumption, available_for_arbitrage, EFFICIENCY)

        cost_with_battery_period = cost_pv_battery_period - arbitrage_profit_period
        profit_battery_period = cost_no_battery_period - cost_with_battery_period

        cost_no_battery_daily = cost_no_battery_period / num_days
        cost_with_battery_daily = cost_with_battery_period / num_days
        profit_battery_daily = profit_battery_period / num_days
        waiting_cost = compute_waiting_cost(profit_battery_daily, 6)

        # NOWOŚĆ: Pakujemy dane z ostatniego dnia do wizualizacji dla klienta
        chart_data = {
            "hours": list(range(24)),
            "pv_kw": pv_generation.tolist(),
            "cons_kw": consumption.tolist(),
            "prices": day_prices["price_pln_mwh"].tolist(),
            "cheap_hours": day_prices["price_pln_mwh"].nsmallest(3).index.tolist(),
            "expensive_hours": day_prices["price_pln_mwh"].nlargest(3).index.tolist()
        }

        output_path = f"data/report_{label}.pdf"
        generate_pdf_report(
            output_path=output_path,
            client=client,
            date=last_30_dates[-1], 
            cost_no_battery=cost_no_battery_daily,
            cost_with_battery=cost_with_battery_daily,
            profit_daily=profit_battery_daily,
            waiting_cost=waiting_cost,
            chart_data=chart_data
        )

        print(f"📄 PDF generated: {output_path}")
        print(f"Daily PROFIT: {profit_battery_daily:.2f} PLN")


if __name__ == "__main__":
    main()