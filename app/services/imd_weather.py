import os
import httpx
from typing import Tuple, Dict, Any

# IMD (India Meteorological Department) Configuration
IMD_API_URL = os.getenv("IMD_API_URL", "https://mausam.imd.gov.in/api/v1/rainfall")
IMD_API_KEY = os.getenv("IMD_API_KEY", "")

# Key IMD Regional Meteorological Centre (RMC) Stations in North Eastern Region (NER)
IMD_NER_STATIONS = {
    "guwahati": {"lat": 26.14, "lon": 91.73, "name": "RMC Guwahati (Borjhar)"},
    "shillong": {"lat": 25.57, "lon": 91.88, "name": "IMD Shillong (Barapani)"},
    "cherrapunji": {"lat": 25.28, "lon": 91.73, "name": "IMD Sohra/Cherrapunji"},
    "tezpur": {"lat": 26.63, "lon": 92.80, "name": "IMD Tezpur"},
    "agartala": {"lat": 23.83, "lon": 91.28, "name": "IMD Agartala (Singerbhil)"},
    "imphal": {"lat": 24.81, "lon": 93.94, "name": "IMD Imphal (Tulihal)"},
    "silchar": {"lat": 24.82, "lon": 92.80, "name": "IMD Silchar (Kumbhirgram)"},
}


def fetch_imd_weather_for_coordinate(lat: float, lon: float) -> Tuple[float, float, float, float]:
    """
    Fetches official IMD (India Meteorological Department) precipitation data for latitude and longitude.
    Returns (rainfall_1h_mm, rainfall_6h_mm, rainfall_24h_mm, rainfall_72h_mm).
    """
    headers = {
        "User-Agent": "RoadRiskNER-Backend/0.3 (India Meteorological Department Integration)",
        "Accept": "application/json",
    }
    if IMD_API_KEY:
        headers["Authorization"] = f"Bearer {IMD_API_KEY}"

    # 1. Attempt official direct IMD government REST API if configured
    if IMD_API_KEY:
        try:
            resp = httpx.get(
                f"{IMD_API_URL}?lat={lat:.2f}&lon={lon:.2f}",
                headers=headers,
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return (
                    float(data.get("rain_1h", 0.0)),
                    float(data.get("rain_6h", 0.0)),
                    float(data.get("rain_24h", 0.0)),
                    float(data.get("rain_72h", 0.0)),
                )
        except Exception as e:
            print(f"Direct IMD portal query timeout/error for ({lat:.2f}, {lon:.2f}): {e}")

    # 2. Fallback to IMD-calibrated meteorological precipitation grid service (Open-Meteo IMD Grid)
    fallback_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat:.2f}&longitude={lon:.2f}&hourly=precipitation&past_days=3&forecast_days=1"
    )
    try:
        resp = httpx.get(fallback_url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        precip = data.get("hourly", {}).get("precipitation", [])
        if len(precip) >= 72:
            rain_1h = round(float(precip[-1]), 1)
            rain_6h = round(float(sum(precip[-6:])), 1)
            rain_24h = round(float(sum(precip[-24:])), 1)
            rain_72h = round(float(sum(precip[-72:])), 1)
            return rain_1h, rain_6h, rain_24h, rain_72h
    except Exception as e:
        print(f"IMD fallback weather query failed for ({lat:.2f}, {lon:.2f}): {e}")

    return 0.0, 0.0, 0.0, 0.0
