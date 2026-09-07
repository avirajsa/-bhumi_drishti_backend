import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import WeatherObservation


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set in .env"
    )

if not OPENWEATHER_API_KEY:
    raise RuntimeError(
        "OPENWEATHER_API_KEY is not set in .env"
    )


# Free Current Weather API
OPENWEATHER_URL = (
    "https://api.openweathermap.org/data/2.5/weather"
)

REQUEST_TIMEOUT = 30


# ============================================================
# WEATHER COLLECTION POINTS
# ============================================================
#
# These are coordinates where we ask OpenWeather for the
# current weather.
#
# They are NOT being treated as actual weather stations.
#
# Later we can replace these with:
# - a proper weather grid
# - actual station locations
# - or another spatial sampling strategy
#
# ============================================================

WEATHER_POINTS = [
    ("guwahati", 26.1445, 91.7362),
    ("dibrugarh", 27.4728, 94.9120),
    ("silchar", 24.8333, 92.7789),

    ("itanagar", 27.0844, 93.6053),
    ("tawang", 27.5860, 91.8590),

    ("shillong", 25.5788, 91.8933),
    ("cherrapunji", 25.2840, 91.7210),

    ("kohima", 25.6751, 94.1086),
    ("dimapur", 25.8629, 93.7536),

    ("imphal", 24.8170, 93.9368),

    ("aizawl", 23.7271, 92.7176),

    ("agartala", 23.8315, 91.2868),

    ("gangtok", 27.3389, 88.6065),

    ("siliguri", 26.7271, 88.3953),
]


# ============================================================
# DATABASE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ============================================================
# FETCH
# ============================================================

def fetch_weather(latitude, longitude):
    """
    Fetch current weather from OpenWeather.

    Raises RuntimeError on:
    - network failure
    - HTTP failure
    - invalid JSON
    - unexpected response structure
    """

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
    }

    try:
        response = requests.get(
            OPENWEATHER_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Network error while requesting "
            f"{latitude}, {longitude}: {exc}"
        ) from exc

    if not response.ok:

        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text

        raise RuntimeError(
            f"OpenWeather returned HTTP "
            f"{response.status_code}: "
            f"{error_data}"
        )

    try:
        data = response.json()

    except ValueError as exc:
        raise RuntimeError(
            "OpenWeather returned invalid JSON"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Unexpected OpenWeather response type: "
            f"{type(data).__name__}"
        )

    return data


# ============================================================
# PARSE
# ============================================================

def parse_weather(data):
    """
    Parse ONLY values actually returned by OpenWeather.

    No synthetic/default weather values are generated.
    """

    required_fields = [
        "dt",
        "main",
        "wind",
    ]

    missing = [
        field
        for field in required_fields
        if field not in data
    ]

    if missing:
        raise RuntimeError(
            "OpenWeather response is missing required "
            f"fields: {missing}"
        )

    main = data["main"]
    wind = data["wind"]

    if "temp" not in main:
        raise RuntimeError(
            "OpenWeather response is missing "
            "main.temp"
        )

    if "humidity" not in main:
        raise RuntimeError(
            "OpenWeather response is missing "
            "main.humidity"
        )

    if "speed" not in wind:
        raise RuntimeError(
            "OpenWeather response is missing "
            "wind.speed"
        )

    observed_at = datetime.fromtimestamp(
        data["dt"],
        tz=timezone.utc,
    )

    temperature_c = float(
        main["temp"]
    )

    humidity = float(
        main["humidity"]
    )

    # OpenWeather returns wind speed in m/s.
    # Convert to km/h for our database.
    wind_speed_kmph = (
        float(wind["speed"]) * 3.6
    )

    # --------------------------------------------------------
    # Rainfall
    # --------------------------------------------------------
    #
    # OpenWeather only includes "rain" when rain data exists.
    #
    # We DO NOT convert missing rain into 0.
    #
    # Missing = NULL.
    #
    # This prevents us from pretending that the API measured
    # zero rainfall when it simply did not provide the field.
    # --------------------------------------------------------

    rainfall_mm = None

    rain = data.get("rain")

    if rain is not None:

        if not isinstance(rain, dict):
            raise RuntimeError(
                "Unexpected format for OpenWeather "
                "'rain' field"
            )

        if "1h" in rain:
            rainfall_mm = float(
                rain["1h"]
            )

    # --------------------------------------------------------
    # Weather condition
    # --------------------------------------------------------

    weather_code = None

    weather = data.get("weather")

    if weather is not None:

        if not isinstance(weather, list):
            raise RuntimeError(
                "Unexpected OpenWeather "
                "'weather' field"
            )

        if len(weather) > 0:

            weather_code = weather[0].get(
                "id"
            )

            if weather_code is not None:
                weather_code = int(
                    weather_code
                )

    return {
        "observed_at": observed_at,
        "rainfall_mm": rainfall_mm,
        "temperature_c": temperature_c,
        "humidity": humidity,
        "wind_speed": wind_speed_kmph,
        "weather_code": weather_code,
    }


# ============================================================
# INGEST LOCATION
# ============================================================

def ingest_location(
    db,
    location_name,
    latitude,
    longitude,
):
    print(
        f"[INFO] Fetching OpenWeather data for "
        f"{location_name} "
        f"({latitude}, {longitude})"
    )

    data = fetch_weather(
        latitude,
        longitude,
    )

    weather = parse_weather(data)

    observed_at = weather["observed_at"]

    # This is OUR collection-point identifier.
    station_id = f"OW_{location_name}"

    # --------------------------------------------------------
    # Duplicate check
    # --------------------------------------------------------

    existing = (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.station_id
            == station_id,

            WeatherObservation.observed_at
            == observed_at,
        )
        .first()
    )

    if existing:

        print(
            f"[INFO] Observation already exists for "
            f"{location_name} at "
            f"{observed_at.isoformat()}"
        )

        return False

    # --------------------------------------------------------
    # Create database row
    # --------------------------------------------------------

    observation = WeatherObservation(
        station_id=station_id,

        observed_at=observed_at,

        latitude=latitude,
        longitude=longitude,

        rainfall_mm=weather["rainfall_mm"],

        temperature_c=weather["temperature_c"],

        humidity=weather["humidity"],

        wind_speed=weather["wind_speed"],

        source="OpenWeather",

        geom=from_shape(
            Point(
                longitude,
                latitude,
            ),
            srid=4326,
        ),
    )

    db.add(observation)

    print(
        f"[SUCCESS] {location_name}"
    )

    print(
        f"          observed_at = "
        f"{observed_at.isoformat()}"
    )

    print(
        f"          rainfall    = "
        f"{weather['rainfall_mm']}"
    )

    print(
        f"          temperature = "
        f"{weather['temperature_c']} °C"
    )

    print(
        f"          humidity    = "
        f"{weather['humidity']} %"
    )

    print(
        f"          wind        = "
        f"{weather['wind_speed']:.2f} km/h"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    db = SessionLocal()

    inserted = 0
    skipped = 0
    failed = 0

    try:

        for (
            location_name,
            latitude,
            longitude,
        ) in WEATHER_POINTS:

            try:

                was_inserted = ingest_location(
                    db=db,
                    location_name=location_name,
                    latitude=latitude,
                    longitude=longitude,
                )

                if was_inserted:

                    db.commit()

                    inserted += 1

                else:

                    skipped += 1

            except Exception as exc:

                db.rollback()

                failed += 1

                print(
                    f"[ERROR] {location_name} failed:"
                )

                print(
                    f"        {exc}"
                )

    finally:

        db.close()

    print()
    print("=" * 60)
    print("WEATHER INGESTION COMPLETE")
    print("=" * 60)

    print(f"Inserted : {inserted}")
    print(f"Skipped  : {skipped}")
    print(f"Failed   : {failed}")
    print(f"Points   : {len(WEATHER_POINTS)}")

    # Make the process fail if any location failed.
    #
    # Useful later with cron/systemd monitoring.
    if failed > 0:

        raise RuntimeError(
            f"Weather ingestion completed with "
            f"{failed} failed locations."
        )


if __name__ == "__main__":
    main()

