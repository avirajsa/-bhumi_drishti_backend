"""
Bhumi Drishti - Terrain Feature Ingestion

Reads:
    data/terrain/COP30_NER/COP30_NER.vrt

For every road segment:
    1. Sample multiple points along the road.
    2. Read elevation from the Copernicus DEM.
    3. Calculate mean elevation.
    4. Estimate slope.
    5. Calculate terrain roughness.
    6. Store the derived features in segment_features.

The DEM itself is NOT stored in PostgreSQL.
Only the derived terrain features are stored.

This is intentionally simple for the prototype.
"""

from pathlib import Path

import numpy as np
import rasterio
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import RoadSegment, SegmentFeature


# ============================================================
# CONFIGURATION
# ============================================================

DEM_PATH = Path(
    "data/terrain/COP30_NER/COP30_NER.vrt"
)

# Number of DEM samples taken along each road segment.
SAMPLES_PER_SEGMENT = 10

# Ignore obviously invalid DEM values.
MIN_ELEVATION = -500
MAX_ELEVATION = 9000

# Commit after every N processed segments.
BATCH_SIZE = 100


# ============================================================
# GEOMETRY
# ============================================================

def get_sample_points(
    geom,
    count: int = SAMPLES_PER_SEGMENT,
):
    """
    Generate evenly distributed points along a road.

    Samples are taken from 5% to 95% of the segment length
    instead of exactly at the endpoints.
    """

    if geom is None:
        return []

    if geom.length == 0:
        return []

    points = []

    fractions = np.linspace(
        0.05,
        0.95,
        count,
    )

    for fraction in fractions:
        point = geom.interpolate(
            fraction,
            normalized=True,
        )

        points.append(point)

    return points


# ============================================================
# DEM SAMPLING
# ============================================================

def sample_elevations(
    dataset,
    points,
):
    """
    Read elevation values from the DEM at the supplied points.

    Invalid, NaN, and out-of-range values are ignored.
    """

    if not points:
        return []

    coordinates = [
        (point.x, point.y)
        for point in points
    ]

    elevations = []

    for sample in dataset.sample(coordinates):

        value = float(sample[0])

        if np.isnan(value):
            continue

        if value < MIN_ELEVATION:
            continue

        if value > MAX_ELEVATION:
            continue

        elevations.append(value)

    return elevations


# ============================================================
# TERRAIN CALCULATIONS
# ============================================================

def calculate_roughness(elevations):
    """
    Calculate terrain roughness as the standard deviation
    of sampled elevations.

    Higher value = greater elevation variation along
    the road segment.
    """

    if len(elevations) < 2:
        return 0.0

    return float(
        np.std(elevations)
    )


def calculate_slope(
    elevations,
    segment_length_m,
):
    """
    Estimate road slope from elevation change.

    slope = atan(elevation_change / horizontal_distance)

    This is a simple prototype approximation. A future
    version can derive slope from a proper DEM slope raster.
    """

    if len(elevations) < 2:
        return 0.0

    if segment_length_m <= 0:
        return 0.0

    elevation_change = abs(
        elevations[-1] - elevations[0]
    )

    slope_ratio = (
        elevation_change / segment_length_m
    )

    slope_deg = np.degrees(
        np.arctan(slope_ratio)
    )

    return float(slope_deg)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_or_create_features(
    db: Session,
    segment_id: int,
):
    """
    Return the SegmentFeature row for a road segment.

    If it does not exist, create it.
    """

    feature = (
        db.query(SegmentFeature)
        .filter(
            SegmentFeature.segment_id == segment_id
        )
        .first()
    )

    if feature is None:

        feature = SegmentFeature(
            segment_id=segment_id
        )

        db.add(feature)

    return feature


# ============================================================
# PROCESS ROAD SEGMENTS
# ============================================================

def process_segments(
    db: Session,
    dataset,
):
    """
    Process every road segment and populate terrain features.

    Road segments are loaded with .all() rather than yield_per()
    because we commit periodically. PostgreSQL server-side
    cursors used by yield_per() can become invalid after commit.
    """

    segments = (
        db.query(RoadSegment)
        .order_by(RoadSegment.segment_id)
        .all()
    )

    print(
        f"Road segments found: {len(segments)}"
    )
    print()

    processed = 0
    skipped = 0

    for segment in segments:

        # ----------------------------------------------------
        # Convert PostGIS geometry to Shapely
        # ----------------------------------------------------

        try:

            geom = to_shape(
                segment.geom
            )

        except Exception as exc:

            print(
                f"[SKIP] segment={segment.segment_id} "
                f"invalid geometry: {exc}"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Generate sample points
        # ----------------------------------------------------

        points = get_sample_points(
            geom,
            SAMPLES_PER_SEGMENT,
        )

        if not points:

            print(
                f"[SKIP] segment={segment.segment_id} "
                f"no valid sample points"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Sample DEM
        # ----------------------------------------------------

        try:

            elevations = sample_elevations(
                dataset,
                points,
            )

        except Exception as exc:

            print(
                f"[SKIP] segment={segment.segment_id} "
                f"DEM sampling failed: {exc}"
            )

            skipped += 1
            continue

        if not elevations:

            print(
                f"[SKIP] segment={segment.segment_id} "
                f"no valid DEM samples"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Calculate terrain features
        # ----------------------------------------------------

        elevation_m = float(
            np.mean(elevations)
        )

        terrain_roughness = calculate_roughness(
            elevations
        )

        slope_deg = calculate_slope(
            elevations,
            segment.length_m,
        )

        # ----------------------------------------------------
        # Create/update segment_features
        # ----------------------------------------------------

        feature = get_or_create_features(
            db,
            segment.segment_id,
        )

        feature.elevation_m = elevation_m

        feature.slope_deg = slope_deg

        feature.terrain_roughness = (
            terrain_roughness
        )

        processed += 1

        # ----------------------------------------------------
        # Periodic commit
        # ----------------------------------------------------

        if processed % BATCH_SIZE == 0:

            db.commit()

            print(
                f"[PROGRESS] "
                f"processed={processed} "
                f"skipped={skipped}"
            )

    # --------------------------------------------------------
    # Final commit
    # --------------------------------------------------------

    db.commit()

    print()
    print("=" * 60)
    print("Terrain ingestion complete")
    print("=" * 60)
    print(
        f"Processed: {processed}"
    )
    print(
        f"Skipped:   {skipped}"
    )
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("Bhumi Drishti - Terrain Feature Ingestion")
    print("=" * 60)

    # --------------------------------------------------------
    # Verify DEM
    # --------------------------------------------------------

    if not DEM_PATH.exists():

        raise FileNotFoundError(
            f"""
DEM VRT not found:

    {DEM_PATH}

Build it first with:

    gdalbuildvrt \\
        data/terrain/COP30_NER/COP30_NER.vrt \\
        data/terrain/COP30_NER/*.tif
"""
        )

    print(
        f"DEM: {DEM_PATH}"
    )

    print()

    # --------------------------------------------------------
    # Open DEM
    # --------------------------------------------------------

    print("Opening DEM...")

    with rasterio.open(DEM_PATH) as dataset:

        print(
            f"CRS:        {dataset.crs}"
        )

        print(
            f"Resolution: {dataset.res}"
        )

        print(
            f"Bounds:     {dataset.bounds}"
        )

        print(
            f"Size:       "
            f"{dataset.width} x {dataset.height}"
        )

        print()

        # ----------------------------------------------------
        # Database connection
        # ----------------------------------------------------

        db = SessionLocal()

        try:

            process_segments(
                db,
                dataset,
            )

        except Exception:

            db.rollback()
            raise

        finally:

            db.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
