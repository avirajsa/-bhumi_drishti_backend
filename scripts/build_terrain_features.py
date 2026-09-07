from pathlib import Path

import numpy as np
import rasterio
from dotenv import load_dotenv
from geoalchemy2.shape import to_shape

from app.db.database import SessionLocal
from app.db.models import RoadSegment, SegmentFeature


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DEM_PATH = (
    PROJECT_ROOT
    / "data"
    / "terrain"
    / "COP30_NER"
    / "COP30_NER.vrt"
)

SAMPLES_PER_SEGMENT = 10
BATCH_SIZE = 500


# ---------------------------------------------------------
# TERRAIN CALCULATION
# ---------------------------------------------------------

def sample_elevations(dem, segment):
    """
    Sample DEM elevation at evenly spaced points along
    a road segment.
    """

    if segment.geom is None:
        return []

    # GeoAlchemy geometry -> Shapely geometry
    geom = to_shape(segment.geom)

    if geom.is_empty:
        return []

    if geom.geom_type != "LineString":
        return []

    # -----------------------------------------------------
    # Generate points along the road
    # -----------------------------------------------------

    if SAMPLES_PER_SEGMENT == 1:
        fractions = [0.5]
    else:
        fractions = np.linspace(
            0.0,
            1.0,
            SAMPLES_PER_SEGMENT,
        )

    points = [
        geom.interpolate(float(fraction))
        for fraction in fractions
    ]

    coordinates = [
        (point.x, point.y)
        for point in points
    ]

    # -----------------------------------------------------
    # Sample DEM
    # -----------------------------------------------------

    elevations = []

    for value in dem.sample(coordinates):

        elevation = float(value[0])

        # Ignore nodata
        if dem.nodata is not None:
            if np.isclose(elevation, dem.nodata):
                continue

        # Ignore invalid values
        if not np.isfinite(elevation):
            continue

        elevations.append(elevation)

    return elevations


def calculate_slope(segment, elevations):
    """
    Simple prototype slope estimate.

    slope = atan(vertical_change / horizontal_distance)
    """

    if len(elevations) < 2:
        return 0.0

    if segment.length_m <= 0:
        return 0.0

    elevation_change = abs(
        elevations[-1] - elevations[0]
    )

    slope_rad = np.arctan(
        elevation_change / segment.length_m
    )

    return float(np.degrees(slope_rad))


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    if not DEM_PATH.exists():
        raise FileNotFoundError(
            f"DEM VRT not found: {DEM_PATH}"
        )

    db = SessionLocal()

    try:

        print(f"Opening DEM: {DEM_PATH}")

        with rasterio.open(DEM_PATH) as dem:

            print(f"DEM CRS: {dem.crs}")
            print(f"DEM resolution: {dem.res}")
            print(f"DEM bounds: {dem.bounds}")
            print()

            # -------------------------------------------------
            # Count segments
            # -------------------------------------------------

            total = (
                db.query(RoadSegment)
                .count()
            )

            print(
                f"Processing {total} road segments..."
            )

            print(
                f"DEM samples per segment: "
                f"{SAMPLES_PER_SEGMENT}"
            )

            print()

            processed = 0
            skipped = 0

            last_id = 0

            # -------------------------------------------------
            # Process in batches
            # -------------------------------------------------

            while True:

                segments = (
                    db.query(RoadSegment)
                    .filter(
                        RoadSegment.segment_id > last_id
                    )
                    .order_by(
                        RoadSegment.segment_id
                    )
                    .limit(BATCH_SIZE)
                    .all()
                )

                if not segments:
                    break

                for segment in segments:

                    last_id = segment.segment_id

                    elevations = sample_elevations(
                        dem,
                        segment,
                    )

                    if not elevations:

                        skipped += 1

                        continue

                    # -------------------------------------------------
                    # Calculate terrain features
                    # -------------------------------------------------

                    elevation_m = float(
                        np.mean(elevations)
                    )

                    terrain_roughness = float(
                        np.std(elevations)
                    )

                    slope_deg = calculate_slope(
                        segment,
                        elevations,
                    )

                    # -------------------------------------------------
                    # Get existing feature row
                    # -------------------------------------------------

                    features = (
                        db.query(SegmentFeature)
                        .filter(
                            SegmentFeature.segment_id
                            == segment.segment_id
                        )
                        .first()
                    )

                    # -------------------------------------------------
                    # Create if necessary
                    # -------------------------------------------------

                    if features is None:

                        features = SegmentFeature(
                            segment_id=segment.segment_id
                        )

                        db.add(features)

                    # -------------------------------------------------
                    # Update terrain
                    # -------------------------------------------------

                    features.elevation_m = elevation_m
                    features.slope_deg = slope_deg
                    features.terrain_roughness = (
                        terrain_roughness
                    )

                    processed += 1

                # -------------------------------------------------
                # Commit batch
                # -------------------------------------------------

                db.commit()

                print(
                    f"Processed: "
                    f"{processed}/{total} "
                    f"| Skipped: {skipped}"
                )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()

    print()
    print("Terrain feature generation complete.")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")


# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    main()
