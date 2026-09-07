#!/usr/bin/env python3

"""
GSI Historical Landslide Inventory Ingestion

GeoJSON
  ↓
validate Point geometry
  ↓
extract GSI properties
  ↓
find nearest road segment (≤ 500m)
  ↓
HistoricalIncident

Usage:
    uv run python scripts/ingest_gsi_inventory.py

    uv run python scripts/ingest_gsi_inventory.py \
        data/gsi_landslide_inventory.geojson
"""

import sys
import os
import json
import math

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

DEFAULT_GEOJSON = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "gsi_landslide_inventory.geojson",
    )
)

MAX_ROAD_DISTANCE_M = 500

BATCH_SIZE = 500


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def clean_value(value):
    """
    Convert GSI values into JSON-safe values.

    Handles:
    - None
    - NaN
    - infinity
    - numpy-like numeric values
    """

    if value is None:
        return None

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

    return value


def clean_properties(properties):
    """
    Clean all GSI properties so they can safely be stored
    inside PostgreSQL JSONB.
    """

    return {
        str(key): clean_value(value)
        for key, value in properties.items()
    }


def parse_number(value, default=None):
    """Safely convert a value to float."""

    if value is None:
        return default

    if isinstance(value, str):
        value = value.strip()

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
        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return default

        return number

    except (ValueError, TypeError):
        return default


def parse_int(value, default=None):
    """Safely convert a value to integer."""

    number = parse_number(value)

    if number is None:
        return default

    return int(number)


def calculate_severity(properties):
    """
    Simple prototype severity score.

    Uses:
      - PERSONS_DEATH
      - PEOPLE_AFFECTED
      - INFRASTRUCTURE_AFFECTED
      - LANDUSE_AFFECTED

    This is a heuristic for the prototype, not a
    scientifically validated severity model.
    """

    deaths = parse_number(
        properties.get("PERSONS_DEATH"),
        0,
    )

    people_affected = parse_number(
        properties.get("PEOPLE_AFFECTED"),
        0,
    )

    score = 0.5

    # Fatalities have the strongest effect.
    if deaths and deaths > 0:
        score += min(deaths * 0.1, 0.3)

    # Affected people provide a smaller contribution.
    if people_affected and people_affected > 0:
        score += min(
            people_affected * 0.01,
            0.15,
        )

    return round(
        min(score, 1.0),
        2,
    )


# ---------------------------------------------------------
# Spatial matching
# ---------------------------------------------------------

def find_nearest_segment(db, lon, lat):
    """
    Find the nearest road segment within 500 meters.
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
# Description
# ---------------------------------------------------------

def build_description(properties):
    """
    Build a human-readable description from useful
    GSI attributes.
    """

    parts = []

    fields = [
        ("SLIDE_NAME", "Slide"),
        ("DISTRICT", "District"),
        ("STATE", "State"),
        ("TRIGGERING", "Trigger"),
        ("MATERIAL_TYPE", "Material"),
        ("MOVEMENT_TYPE", "Movement"),
        ("MOVEMENT_RATE", "Movement rate"),
        ("NH_SH_LOCATION", "Location"),
    ]

    for field, label in fields:

        value = properties.get(field)

        if value is None:
            continue

        value = str(value).strip()

        if value in (
            "",
            "-",
            "--",
            " ",
        ):
            continue

        parts.append(
            f"{label}: {value}"
        )

    return "; ".join(parts)


# ---------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------

def ingest(geojson_path):

    if not os.path.exists(geojson_path):
        raise FileNotFoundError(
            f"GeoJSON not found: {geojson_path}"
        )

    print(
        f"Loading GSI GeoJSON: {geojson_path}"
    )

    # Create missing tables if necessary.
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()

    inserted = 0
    invalid_geometry = 0
    invalid_coordinates = 0
    no_nearby_road = 0
    unsupported_geometry = 0

    try:

        # -------------------------------------------------
        # Verify road network exists
        # -------------------------------------------------

        road_count = db.query(
            RoadSegment
        ).count()

        if road_count == 0:
            print(
                "ERROR: road_segments is empty. "
                "Import OSM roads first."
            )
            return

        print(
            f"Road segments available: {road_count}"
        )

        # -------------------------------------------------
        # Load GeoJSON
        # -------------------------------------------------

        with open(
            geojson_path,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if data.get("type") != "FeatureCollection":

            raise ValueError(
                "GeoJSON must be a FeatureCollection."
            )

        features = data.get("features", [])

        print(
            f"GSI features found: {len(features)}"
        )

        # -------------------------------------------------
        # Process features
        # -------------------------------------------------

        for feature_number, feature in enumerate(
            features,
            start=1,
        ):

            geometry = feature.get("geometry")
            properties = feature.get(
                "properties"
            ) or {}

            # ---------------------------------------------
            # Geometry validation
            # ---------------------------------------------

            if not geometry:

                invalid_geometry += 1
                continue

            geometry_type = geometry.get("type")

            if geometry_type != "Point":

                unsupported_geometry += 1
                continue

            coordinates = geometry.get(
                "coordinates"
            )

            if (
                not coordinates
                or len(coordinates) < 2
            ):

                invalid_geometry += 1
                continue

            lon = parse_number(
                coordinates[0]
            )

            lat = parse_number(
                coordinates[1]
            )

            if lon is None or lat is None:

                invalid_coordinates += 1
                continue

            # Rough NER bounding box.
            if not (
                20 <= lat <= 30
                and 87 <= lon <= 98
            ):

                invalid_coordinates += 1
                continue

            # ---------------------------------------------
            # Find nearest road
            # ---------------------------------------------

            segment = find_nearest_segment(
                db,
                lon,
                lat,
            )

            if segment is None:

                no_nearby_road += 1
                continue

            # ---------------------------------------------
            # Event year
            # ---------------------------------------------
            #
            # GSI provides a year through SLIDE_NO values
            # such as:
            #
            # AP/SY/83I01/2021/14
            #
            # We intentionally do not invent an exact
            # occurred_at date.
            # ---------------------------------------------

            event_year = None

            slide_no = properties.get(
                "SLIDE_NO"
            )

            if slide_no:

                slide_no = str(slide_no)

                # Search slash-separated components.
                for part in slide_no.split("/"):

                    year = parse_int(part)

                    if (
                        year is not None
                        and 1900 <= year <= 2100
                    ):

                        event_year = year
                        break

            # ---------------------------------------------
            # Severity
            # ---------------------------------------------

            severity = calculate_severity(
                properties
            )

            # ---------------------------------------------
            # Description
            # ---------------------------------------------

            description = build_description(
                properties
            )

            # ---------------------------------------------
            # Preserve ALL original GSI data
            # ---------------------------------------------

            source_metadata = {
                "source_dataset": "gsi_landslide_inventory",
                "original_feature": feature_number,
                "original": clean_properties(
                    properties
                ),
            }

            # ---------------------------------------------
            # Geometry
            # ---------------------------------------------

            point = Point(
                lon,
                lat,
            )

            point_geometry = from_shape(
                point,
                srid=4326,
            )

            # ---------------------------------------------
            # HistoricalIncident
            # ---------------------------------------------

            incident = HistoricalIncident(
                segment_id=segment.segment_id,

                incident_type="landslide",

                severity=severity,

                description=description,

                occurred_at=None,

                event_year=event_year,

                geom=point_geometry,

                source_metadata=source_metadata,
            )

            db.add(incident)

            inserted += 1

            # ---------------------------------------------
            # Batch commit
            # ---------------------------------------------

            if inserted % BATCH_SIZE == 0:

                db.commit()

                print(
                    f"Inserted {inserted} GSI incidents..."
                )

        # -------------------------------------------------
        # Final commit
        # -------------------------------------------------

        db.commit()

        print(
            "\n========== GSI INGESTION =========="
        )

        print(
            f"Features processed:   {len(features)}"
        )

        print(
            f"Inserted:             {inserted}"
        )

        print(
            f"Invalid geometry:     {invalid_geometry}"
        )

        print(
            f"Invalid coordinates:  {invalid_coordinates}"
        )

        print(
            f"Unsupported geometry: {unsupported_geometry}"
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

    geojson_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else DEFAULT_GEOJSON
    )

    ingest(geojson_path)

