# src/entsoe_client.py
"""
ENTSO-E Day-Ahead price client.

Responsible for:
- fetching Day-Ahead prices (A44) for Poland
- handling retries and transient failures
- parsing XML into a clean hourly structure with automatic 
  resolution handling (PT15M -> 60M aggregation).
"""

import time
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta
from typing import List, Dict

from config import (
    ENTSOE_API_KEY,
    ENTSOE_BASE_URL,
    PL_BIDDING_ZONE,
    ENTSOE_DAY_AHEAD_DOCUMENT,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF,
)

class ENTSOEClient:
    def __init__(self):
        self.session = requests.Session()

    def fetch_day_ahead_prices(self, date_iso: str) -> List[Dict]:
        start_dt = datetime.fromisoformat(date_iso)
        end_dt = start_dt + timedelta(days=1)

        params = {
            "securityToken": ENTSOE_API_KEY,
            "documentType": ENTSOE_DAY_AHEAD_DOCUMENT,
            "in_Domain": PL_BIDDING_ZONE,
            "out_Domain": PL_BIDDING_ZONE,
            "periodStart": start_dt.strftime("%Y%m%d0000"),
            "periodEnd": end_dt.strftime("%Y%m%d0000"),
        }

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    ENTSOE_BASE_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return self._parse_prices(response.text, date_iso)

            except (requests.RequestException, ET.ParseError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
                else:
                    break

        raise RuntimeError(
            f"ENTSO-E request failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def _parse_prices(self, xml_text: str, date_iso: str) -> List[Dict]:
        root = ET.fromstring(xml_text)

        # 1. Анализ разрешения данных (PT15M, PT30M, PT60M)
        resolution = "PT60M"  # По умолчанию 1 час
        for elem in root.iter():
            if elem.tag.endswith("resolution"):
                resolution = elem.text
                break
                
        points_per_hour = 1
        if resolution == "PT15M":
            points_per_hour = 4
        elif resolution == "PT30M":
            points_per_hour = 2

        # 2. Сбор сырых интервалов
        raw_points = []
        for elem in root.iter():
            if not elem.tag.endswith("Point"):
                continue

            pos = None
            price = None

            for child in elem:
                if child.tag.endswith("position"):
                    try:
                        pos = int(child.text)
                    except (TypeError, ValueError):
                        pass
                elif child.tag.endswith("price.amount"):
                    try:
                        price = float(child.text)
                    except (TypeError, ValueError):
                        pass

            if pos is not None and price is not None:
                raw_points.append({"position": pos, "price": price})

        if not raw_points:
            raise ValueError("No valid Day-Ahead prices found in ENTSO-E response")

        raw_points.sort(key=lambda r: r["position"])

        # 3. Агрегация интервалов в полноценные часы (L2-патч)
        records: List[Dict] = []
        for i in range(0, len(raw_points), points_per_hour):
            chunk = raw_points[i : i + points_per_hour]
            avg_price = sum(p["price"] for p in chunk) / len(chunk)
            hour_index = (i // points_per_hour) + 1
            
            records.append(
                {
                    "date": date_iso,
                    "hour": hour_index,
                    "price_eur_mwh": round(avg_price, 2),
                }
            )

        return records
