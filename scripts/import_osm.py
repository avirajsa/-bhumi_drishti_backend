#!/usr/bin/env python3
"""
Real OpenStreetMap PBF Importer & Road Segmenter
for Road Risk & Accessibility System (NER India)

IMPORTANT:
    This script NEVER generates sample/fabricated road data.

    A real OpenStreetMap .osm.pbf file MUST be supplied.

Usage:
    python scripts/import_osm.py path/to/real.osm.pbf

Example:
    python scripts/import_osm.py data/osm/north-eastern-zone-latest.osm.pbf

Behavior:
    1. Validates the supplied PBF file.
    2. Reads actual OpenStreetMap Ways using pyosmium.
    3. Extracts actual OSM road attributes and coordinates.
    4. Converts each OSM road Way into ~500 m segments.
    5. Stores the resulting geometries in PostGIS.
    6. Stores the original OSM Way ID for provenance.

There is NO:
    - sample road generation
    - random data
    - fabricated coordinates
    - fabricated road attributes
    - fallback dataset
"""

import sys
import os
import math
from typing import Optional

import pyproj
import osmium

from shapely.geometry import LineString
from shapely.ops import transform, substring

from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.database import engine, SessionLocal, Base
from app.db.models import RoadSegment


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WGS84_CRS = "EPSG:4326"

TARGET_SEGMENT_LENGTH_M = 500.0

# Vehicular road classes we actually want for a road-risk/accessibility system.
#
# This is a FILTER, not fabricated data.
#
# OSM highway=* values outside this set are ignored.
ALLOWED_HIGHWAY_TYPES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "service",
    "living_street",
    "road",
    "track",
}


# ---------------------------------------------------------------------------
# OSM tag parsing
# ---------------------------------------------------------------------------

def parse_boolean_tag(val: Optional[str]) -> Optional[bool]:
    """
    Convert common OSM boolean tag values into Python bool.

    Examples:
        yes   -> True
        true  -> True
        1     -> True
        no    -> False
        false -> False
        0     -> False

    Unknown/missing values remain None.

    IMPORTANT:
        We do NOT guess when OSM doesn't provide a usable value.
    """
    if val is None:
        return None

    val_clean = val.strip().lower()

    if val_clean in ("yes", "true", "1"):
        return True

    if val_clean in ("no", "false", "0"):
        return False

    return None


def parse_int_tag(val: Optional[str]) -> Optional[int]:
    """
    Convert an OSM integer tag to int.

    Unknown/non-integer values remain None.

    We deliberately do not guess values.
    """
    if val is None:
        return None

    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# UTM helpers
# ---------------------------------------------------------------------------

def utm_zone_from_longitude(longitude: float) -> int:
    """
    Determine the UTM zone containing a longitude.

    UTM zones are 6 degrees wide:

        Zone 1:   -180 to -174
        Zone 2:   -174 to -168
        ...
        Zone 46:    84 to 90
        Zone 47:    90 to 96
        Zone 48:    96 to 102

    NER spans multiple zones, so we do not force everything into Zone 46.
    """
    zone = int((longitude + 180.0) / 6.0) + 1

    # Protect against invalid edge values.
    return max(1, min(zone, 60))


def metric_crs_for_line(line_wgs84: LineString) -> str:
    """
    Select the UTM CRS based on the longitude of the line's centroid.

    Northern Hemisphere:
        EPSG:326XX

    Example:
        UTM zone 46N -> EPSG:32646
        UTM zone 47N -> EPSG:32647
        UTM zone 48N -> EPSG:32648
    """
    centroid = line_wgs84.centroid
    zone = utm_zone_from_longitude(centroid.x)

    return f"EPSG:{32600 + zone}"


def transform_to_metric(line_wgs84: LineString):
    """
    Transform a WGS84 LineString into an appropriate UTM zone.

    Returns:
        (metric_line, transformer_to_wgs84)
    """
    metric_crs = metric_crs_for_line(line_wgs84)

    transformer_to_metric = pyproj.Transformer.from_crs(
        WGS84_CRS,
        metric_crs,
        always_xy=True,
    ).transform

    transformer_to_wgs84 = pyproj.Transformer.from_crs(
        metric_crs,
        WGS84_CRS,
        always_xy=True,
    ).transform

    line_metric = transform(
        transformer_to_metric,
        line_wgs84,
    )

    return line_metric, transformer_to_wgs84


# ---------------------------------------------------------------------------
# OSM extraction
# ---------------------------------------------------------------------------

class RoadExtractorHandler(osmium.SimpleHandler):
    """
    Osmium handler that extracts real OSM road Ways.

    No road geometry is generated here.

    Every coordinate comes directly from OSM.
    Every road attribute comes directly from OSM.
    """

    def __init__(self):
        super().__init__()

        # List of dictionaries containing actual OSM road data.
        self.roads = []

        # Statistics useful for diagnostics.
        self.ways_seen = 0
        self.roads_kept = 0
        self.roads_skipped = 0

    def way(self, w):
        """
        Called by pyosmium for every OSM Way in the PBF.
        """

        self.ways_seen += 1

        # ---------------------------------------------------------------
        # Must have highway tag.
        # ---------------------------------------------------------------

        if "highway" not in w.tags:
            self.roads_skipped += 1
            return

        highway_type = w.tags.get("highway")

        # ---------------------------------------------------------------
        # Keep only road classes relevant to the application.
        # ---------------------------------------------------------------

        if highway_type not in ALLOWED_HIGHWAY_TYPES:
            self.roads_skipped += 1
            return

        # ---------------------------------------------------------------
        # Extract actual OSM node coordinates.
        # ---------------------------------------------------------------

        coords = []

        for node in w.nodes:
            if not node.location.valid():
                continue

            coords.append(
                (
                    node.lon,
                    node.lat,
                )
            )

        # A LineString needs at least two coordinates.
        if len(coords) < 2:
            self.roads_skipped += 1
            return

        # ---------------------------------------------------------------
        # Store actual OSM attributes.
        # ---------------------------------------------------------------

        road = {
            "osm_way_id": int(w.id),

            "highway": highway_type,

            "name": w.tags.get("name"),

            "ref": w.tags.get("ref"),

            "lanes": parse_int_tag(
                w.tags.get("lanes")
            ),

            "surface": w.tags.get("surface"),

            "bridge": parse_boolean_tag(
                w.tags.get("bridge")
            ),

            "oneway": parse_boolean_tag(
                w.tags.get("oneway")
            ),

            "maxspeed": w.tags.get("maxspeed"),

            "coords": coords,
        }

        self.roads.append(road)
        self.roads_kept += 1


# ---------------------------------------------------------------------------
# Road segmentation
# ---------------------------------------------------------------------------

def segment_and_store_roads(
    roads_data,
    db: Session,
):
    """
    Convert actual OSM Ways into approximately 500 m segments.

    No geometry is fabricated.

    Every segment is a substring of an actual OSM road Way.
    """

    total_segments_inserted = 0
    total_distance_m = 0.0

    for road_index, road in enumerate(roads_data, start=1):

        coords = road["coords"]

        # ---------------------------------------------------------------
        # Create geometry from actual OSM coordinates.
        # ---------------------------------------------------------------

        try:
            line_wgs84 = LineString(coords)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create geometry for OSM Way "
                f"{road['osm_way_id']}: {exc}"
            ) from exc

        if line_wgs84.is_empty:
            continue

        if not line_wgs84.is_valid:
            # We don't silently repair geometry because doing so could
            # alter the actual source geometry.
            print(
                f"WARNING: Skipping invalid geometry for "
                f"OSM Way {road['osm_way_id']}"
            )
            continue

        # ---------------------------------------------------------------
        # Convert to a local metric CRS.
        # ---------------------------------------------------------------

        try:
            line_metric, transformer_to_wgs84 = transform_to_metric(
                line_wgs84
            )
        except Exception as exc:
            raise RuntimeError(
                f"CRS transformation failed for OSM Way "
                f"{road['osm_way_id']}: {exc}"
            ) from exc

        total_len_m = line_metric.length

        if total_len_m <= 0:
            continue

        # ---------------------------------------------------------------
        # Determine number of ~500 m segments.
        # ---------------------------------------------------------------

        if total_len_m <= TARGET_SEGMENT_LENGTH_M:
            num_segments = 1
        else:
            num_segments = math.ceil(
                total_len_m / TARGET_SEGMENT_LENGTH_M
            )

        # Dividing the road evenly means the final segment isn't tiny.
        step_len = total_len_m / num_segments

        # ---------------------------------------------------------------
        # Generate each segment as a substring of the real OSM geometry.
        # ---------------------------------------------------------------

        for segment_index in range(num_segments):

            start_d = segment_index * step_len

            end_d = min(
                (segment_index + 1) * step_len,
                total_len_m,
            )

            sub_line_metric = substring(
                line_metric,
                start_d,
                end_d,
            )

            if sub_line_metric.is_empty:
                continue

            # Convert the segment back to WGS84 for PostGIS storage.
            sub_line_wgs84 = transform(
                transformer_to_wgs84,
                sub_line_metric,
            )

            if sub_line_wgs84.is_empty:
                continue

            seg_len_m = sub_line_metric.length

            # -----------------------------------------------------------
            # Convert Shapely geometry to GeoAlchemy/PostGIS geometry.
            # -----------------------------------------------------------

            wkb_geom = from_shape(
                sub_line_wgs84,
                srid=4326,
            )

            # -----------------------------------------------------------
            # Create database record.
            #
            # All attributes originate from the OSM Way.
            # -----------------------------------------------------------

            segment_record = RoadSegment(
                osm_way_id=road["osm_way_id"],

                road_type=road["highway"],

                lanes=road["lanes"],

                surface=road["surface"],

                bridge=road["bridge"],

                oneway=road["oneway"],

                maxspeed=road["maxspeed"],

                name=road["name"],

                ref=road["ref"],

                length_m=seg_len_m,

                geom=wkb_geom,
            )

            db.add(segment_record)

            total_segments_inserted += 1
            total_distance_m += seg_len_m

        # ---------------------------------------------------------------
        # Periodic flush so SQLAlchemy doesn't hold every object forever.
        # ---------------------------------------------------------------

        if road_index % 1000 == 0:
            db.flush()

            print(
                f"Processed {road_index:,} / "
                f"{len(roads_data):,} road Ways | "
                f"segments pending: "
                f"{total_segments_inserted:,}"
            )

    # ---------------------------------------------------------------
    # Commit the complete import.
    # ---------------------------------------------------------------

    db.commit()

    return (
        total_segments_inserted,
        total_distance_m,
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_pbf_path(pbf_path: str):
    """
    Strictly validate the input.

    There is NO fallback.

    Missing/invalid input = error + exit.
    """

    if not pbf_path:
        raise ValueError(
            "No PBF file was supplied."
        )

    if not os.path.exists(pbf_path):
        raise FileNotFoundError(
            f"PBF file does not exist: {pbf_path}"
        )

    if not os.path.isfile(pbf_path):
        raise ValueError(
            f"PBF path is not a regular file: {pbf_path}"
        )

    if not os.access(pbf_path, os.R_OK):
        raise PermissionError(
            f"PBF file is not readable: {pbf_path}"
        )

    if not pbf_path.lower().endswith(
        (".pbf", ".osm.pbf")
    ):
        raise ValueError(
            f"Input does not appear to be an OSM PBF file: "
            f"{pbf_path}"
        )

    file_size = os.path.getsize(pbf_path)

    if file_size == 0:
        raise ValueError(
            f"PBF file is empty: {pbf_path}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    # ------------------------------------------------------------------
    # REQUIRE exactly one real PBF input.
    # ------------------------------------------------------------------

    if len(sys.argv) != 2:
        print(
            "ERROR: A real OpenStreetMap .osm.pbf file is required.",
            file=sys.stderr,
        )

        print(
            "\nUsage:",
            file=sys.stderr,
        )

        print(
            "  python scripts/import_osm.py "
            "/path/to/real.osm.pbf",
            file=sys.stderr,
        )

        sys.exit(2)

    pbf_path = os.path.abspath(sys.argv[1])

    # ------------------------------------------------------------------
    # Validate input.
    # ------------------------------------------------------------------

    try:
        validate_pbf_path(pbf_path)
    except Exception as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=" * 70)
    print("REAL OSM ROAD IMPORT")
    print("=" * 70)

    print(f"Input PBF : {pbf_path}")
    print(
        f"File size : "
        f"{os.path.getsize(pbf_path) / (1024 * 1024):.2f} MB"
    )

    print(
        f"Target segment length: "
        f"{TARGET_SEGMENT_LENGTH_M:.0f} m"
    )

    print(
        "Synthetic/fallback data: DISABLED"
    )

    print("=" * 70)

    # ------------------------------------------------------------------
    # Ensure database tables exist.
    # ------------------------------------------------------------------

    try:
        Base.metadata.create_all(
            bind=engine
        )
    except Exception as exc:
        print(
            f"ERROR: Could not initialize database tables: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Read actual OSM PBF.
    # ------------------------------------------------------------------

    handler = RoadExtractorHandler()

    try:
        print("\nReading actual OpenStreetMap PBF...")

        idx = osmium.index.create_map(
            "flex_mem"
        )

        location_handler = osmium.NodeLocationsForWays(
            idx
        )

        location_handler.ignore_errors()

        reader = osmium.io.Reader(
            pbf_path
        )

        try:
            osmium.apply(
                reader,
                location_handler,
                handler,
            )
        finally:
            reader.close()

    except Exception as exc:
        print(
            "\nERROR: Failed to read the OSM PBF.",
            file=sys.stderr,
        )

        print(
            f"Reason: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)

    # ------------------------------------------------------------------
    # Print extraction statistics.
    # ------------------------------------------------------------------

    print("\n--- OSM Extraction ---")

    print(
        f"OSM Ways examined : "
        f"{handler.ways_seen:,}"
    )

    print(
        f"Road Ways retained: "
        f"{handler.roads_kept:,}"
    )

    print(
        f"Ways skipped      : "
        f"{handler.roads_skipped:,}"
    )

    if not handler.roads:
        print(
            "\nERROR: No usable road Ways were found in "
            "the supplied OSM PBF.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Open database session.
    # ------------------------------------------------------------------

    db = SessionLocal()

    try:

        # --------------------------------------------------------------
        # Clear existing road segments.
        #
        # This is intentionally destructive for a clean re-import.
        # --------------------------------------------------------------

        print(
            "\nRemoving existing RoadSegment records..."
        )

        db.query(
            RoadSegment
        ).delete(
            synchronize_session=False
        )

        db.commit()

        print(
            "Existing RoadSegment records removed."
        )

        # --------------------------------------------------------------
        # Segment and insert real OSM roads.
        # --------------------------------------------------------------

        print(
            "\nSegmenting and storing actual OSM roads..."
        )

        segments_cnt, total_dist_m = (
            segment_and_store_roads(
                handler.roads,
                db,
            )
        )

        # --------------------------------------------------------------
        # Final result.
        # --------------------------------------------------------------

        print("\n" + "=" * 70)
        print("IMPORT COMPLETE")
        print("=" * 70)

        print(
            f"OSM road Ways imported : "
            f"{handler.roads_kept:,}"
        )

        print(
            f"Road segments inserted : "
            f"{segments_cnt:,}"
        )

        print(
            f"Total road distance     : "
            f"{total_dist_m / 1000.0:,.2f} km"
        )

        print(
            "Data source             : "
            "OpenStreetMap PBF supplied by user"
        )

        print(
            "Synthetic road data     : "
            "NONE"
        )

        print("=" * 70)

    except Exception as exc:

        # --------------------------------------------------------------
        # Roll back if anything goes wrong during insertion.
        # --------------------------------------------------------------

        db.rollback()

        print(
            "\nERROR: Road import failed.",
            file=sys.stderr,
        )

        print(
            f"Reason: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()

