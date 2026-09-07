#!/usr/bin/env python3

"""
CSV Historical Landslide Ingestion

CSV
  ↓
validate coordinates
  ↓
parse date/year
  ↓
nearest road segment (≤ 500m)
  ↓
HistoricalIncident

Usage:
    uv run python scripts/ingest_csv_incidents.py
    uv run python scripts/ingest_csv_incidents.py path/to/file.csv
"""

import sys
import os
import csv
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

# ---------------------------------------------------------
# Project root
# ---------------------------------------------------------

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)

from app.db.database import engine, SessionLocal, Base
from app.db.models import (
    RoadSegment,
    HistoricalIncident,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

DEFAULT_CSV = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "historical_landslides.csv",
    )
)

MAX_ROAD_DISTANCE_M = 500


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def parse_float(value, default=None):
    """Safely parse a value as float."""

    if value is None:
        return default

    value = str(value).strip()

    if value in (
        "",
        "-",
        "--",
        "NA",
        "N/A",
        "null",
        "None",
    ):
        return default

    try:
        return float(value)

    except (ValueError, TypeError):
        return default


def parse_int(value, default=None):
    """Safely parse a value as integer."""

    number = parse_float(value)

    if number is None:
        return default

    return int(number)


def parse_date(value):
    """Try several common date formats."""

    if not value:
        return None

    value = str(value).strip()

    if value in ("", "-", "--"):
        return None

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)

        except ValueError:
            continue

    return None


def extract_year(date_value, report_year):
    """
    Get event year from the exact date when available.
    Otherwise use report_year.
    """

    if date_value:
        return date_value.year

    year = parse_int(report_year)

    if year and 1900 <= year <= 2100:
        return year

    return None


def calculate_severity(casualty):
    """
    Simple prototype severity score.

    Unknown/zero casualties → 0.65
    Increasing casualties → increasing severity
    Maximum → 1.0
    """

    if casualty is None or casualty <= 0:
        return 0.65

    return round(
        min(0.6 + casualty * 0.1, 1.0),
        2,
    )


# ---------------------------------------------------------
# Spatial matching
# ---------------------------------------------------------

def find_nearest_segment(db, lon, lat):
    """
    Find the nearest road segment within MAX_ROAD_DISTANCE_M.
    """

    query = text(
        """
        SELECT
            segment_id,

            ST_Distance(
                geom::geography,
                ST_SetSRID(
                    ST_MakePoint(:lon, :lat),
                    4326
                )::geography
            ) AS distance_m

        FROM road_segments

        WHERE ST_DWithin(
            geom::geography,
            ST_SetSRID(
                ST_MakePoint(:lon, :lat),
                4326
            )::geography,
            :max_distance
        )

        ORDER BY geom <-> ST_SetSRID(
            ST_MakePoint(:lon, :lat),
            4326
        )

        LIMIT 1
        """
    )

    return db.execute(
        query,
        {
            "lon": lon,
            "lat": lat,
            "max_distance": MAX_ROAD_DISTANCE_M,
        },
    ).fetchone()


# ---------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------

def ingest(csv_path):

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"CSV not found: {csv_path}"
        )

    print(f"Loading CSV: {csv_path}")

    # Create tables if they don't exist.
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()

    inserted = 0
    invalid_coordinates = 0
    invalid_dates = 0
    no_nearby_road = 0

    try:

        # -------------------------------------------------
        # Verify road network exists
        # -------------------------------------------------

        road_count = db.query(RoadSegment).count()

        if road_count == 0:
            print(
                "ERROR: road_segments is empty. "
                "Import OSM roads first."
            )
            return

        print(f"Road segments available: {road_count}")

        # -------------------------------------------------
        # Read CSV
        # -------------------------------------------------

        with open(
            csv_path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            for row_number, row in enumerate(
                reader,
                start=2,
            ):

                # -----------------------------------------
                # Coordinates
                # -----------------------------------------

                lat = parse_float(
                    row.get("latitude")
                )

                lon = parse_float(
                    row.get("longitude")
                )

                if lat is None or lon is None:
                    invalid_coordinates += 1
                    continue

                # Rough NER bounding box.
                if not (
                    20 <= lat <= 30
                    and 87 <= lon <= 98
                ):
                    invalid_coordinates += 1
                    continue

                # -----------------------------------------
                # Date
                # -----------------------------------------

                occurred_at = parse_date(
                    row.get("date_of_event")
                )

                event_year = extract_year(
                    occurred_at,
                    row.get("report_year"),
                )

                if occurred_at is None:
                    invalid_dates += 1

                # -----------------------------------------
                # Find nearest road
                # -----------------------------------------

                segment = find_nearest_segment(
                    db,
                    lon,
                    lat,
                )

                if segment is None:
                    no_nearby_road += 1
                    continue

                # -----------------------------------------
                # Preserve original CSV data
                # -----------------------------------------

                source_metadata = {
                    "source_dataset": "csv",
                    "original_row": row_number,
                    "original": dict(row),
                }

                # -----------------------------------------
                # Severity
                # -----------------------------------------

                casualty = parse_float(
                    row.get("casualty")
                )

                severity = calculate_severity(
                    casualty
                )

                # -----------------------------------------
                # Description
                # -----------------------------------------

                description_parts = []

                for field in [
                    "name",
                    "location",
                    "district",
                    "state",
                ]:

                    value = row.get(field)

                    if value and value.strip():
                        description_parts.append(
                            value.strip()
                        )

                description = ", ".join(
                    description_parts
                )

                # -----------------------------------------
                # Geometry
                # -----------------------------------------

                point = Point(
                    lon,
                    lat,
                )

                geometry = from_shape(
                    point,
                    srid=4326,
                )

                # -----------------------------------------
                # Create HistoricalIncident
                # -----------------------------------------

                incident = HistoricalIncident(
                    segment_id=segment.segment_id,

                    incident_type="landslide",

                    severity=severity,

                    description=description,

                    occurred_at=occurred_at,

                    event_year=event_year,

                    geom=geometry,

                    source_metadata=source_metadata,
                )

                db.add(incident)

                inserted += 1

                # -----------------------------------------
                # Periodic commit
                # -----------------------------------------

                if inserted % 100 == 0:

                    db.commit()

                    print(
                        f"Inserted {inserted} incidents..."
                    )

        # -------------------------------------------------
        # Final commit
        # -------------------------------------------------

        db.commit()

        print(
            "\n========== CSV INGESTION =========="
        )

        print(
            f"Inserted:             {inserted}"
        )

        print(
            f"Invalid coordinates:  {invalid_coordinates}"
        )

        print(
            f"Invalid/missing date: {invalid_dates}"
        )

        print(
            f"No road within 500m:  {no_nearby_road}"
        )

        print(
            "===================================\n"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------

if __name__ == "__main__":

    csv_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else DEFAULT_CSV
    )

    ingest(csv_path)

