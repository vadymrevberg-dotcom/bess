"""
Update market data (Day-Ahead electricity prices) from ENTSO-E
and store them in data/output.csv.
"""

from datetime import date, timedelta

from entsoe_client import ENTSOEClient
from pipeline import merge_price_and_weather
from config import EUR_TO_PLN  # Добавлен импорт актуального курса

OUTPUT_PATH = "data/output.csv"

def main():
    client = ENTSOEClient()
    target_date = (date.today() - timedelta(days=1)).isoformat()

    print(f"▶ Fetching ENTSO-E Day-Ahead prices for {target_date}...")

    prices_eur = client.fetch_day_ahead_prices(target_date)

    if not prices_eur:
        raise RuntimeError("No price data received from ENTSO-E")

    # ПАТЧ: Конвертация EUR -> PLN с округлением до 2 знаков для финансовой точности
    prices_pln = [
        {
            "date": p["date"],
            "hour": p["hour"],  
            "price_pln_mwh": round(p["price_eur_mwh"] * EUR_TO_PLN, 2),
        }
        for p in prices_eur
    ]

    merge_price_and_weather(
        prices=prices_pln,
        weather={},          
        output_path=OUTPUT_PATH,
    )

    print(f"✅ Market data updated successfully: {OUTPUT_PATH}")
    print(f"   Records: {len(prices_pln)} hours")


if __name__ == "__main__":
    main()