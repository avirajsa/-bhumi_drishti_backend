#!/usr/bin/env python3
"""
OSM PBF Importer & Road Segmenter for Road Risk & Accessibility System (NER India)

Usage:
    python scripts/import_osm.py [path/to/extract.osm.pbf]

If no PBF file is provided, a sample OSM PBF extract for NER India roads will be created and imported automatically.
"""

import sys
import os
import math
import pyproj
import osmium
from shapely.geometry import LineString
from shapely.ops import transform, substring
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, SessionLocal, Base
from app.db.models import RoadSegment

# Set up CRS transformations (WGS84 <-> UTM Zone 46N for North Eastern Region of India)
WGS84_CRS = "EPSG:4326"
UTM_NER_CRS = "EPSG:32646"

transformer_to_metric = pyproj.Transformer.from_crs(WGS84_CRS, UTM_NER_CRS, always_xy=True).transform
transformer_to_wgs84 = pyproj.Transformer.from_crs(UTM_NER_CRS, WGS84_CRS, always_xy=True).transform

TARGET_SEGMENT_LENGTH_M = 500.0


def parse_boolean_tag(val: str | None) -> bool | None:
    if val is None:
        return None
    val_clean = val.strip().lower()
    if val_clean in ("yes", "true", "1"):
        return True
    if val_clean in ("no", "false", "0"):
        return False
    return None


def parse_int_tag(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val.strip())
    except ValueError:
        return None


def create_sample_ner_pbf(output_path: str):
    """
    Generate a realistic sample OSM PBF file containing roads in North Eastern Region (NER) India.
    Includes highways around Guwahati, Shillong, Tezpur, and Agartala.
    """
    print(f"Creating sample NER OSM PBF extract at: {output_path}")
    writer = osmium.SimpleWriter(output_path)

    # Sample road routes in NER India
    sample_roads = [
        {
            "way_id": 100001,
            "highway": "primary",
            "name": "GS Road (Guwahati - Shillong Highway, NH-27)",
            "ref": "NH-27",
            "lanes": "4",
            "surface": "asphalt",
            "maxspeed": "60",
            "nodes": [
                (1, 91.7362, 26.1438),
                (2, 91.7510, 26.1280),
                (3, 91.7700, 26.1100),
                (4, 91.7950, 26.0850),
                (5, 91.8200, 26.0500),
                (6, 91.8500, 26.0100),
                (7, 91.8800, 25.9600),
                (8, 91.8980, 25.9180),
            ]
        },
        {
            "way_id": 100002,
            "highway": "secondary",
            "name": "Shillong Bypass Road",
            "ref": "SH-2",
            "lanes": "2",
            "surface": "asphalt",
            "maxspeed": "50",
            "bridge": "yes",
            "nodes": [
                (10, 91.8980, 25.9180),
                (11, 91.9200, 25.8900),
                (12, 91.9450, 25.8600),
                (13, 91.9700, 25.8300),
            ]
        },
        {
            "way_id": 100003,
            "highway": "tertiary",
            "name": "Cherrapunji - Laitkynsew Mountain Road",
            "ref": "MDR-12",
            "lanes": "1",
            "surface": "paved",
            "maxspeed": "40",
            "nodes": [
                (20, 91.7300, 25.2800),
                (21, 91.7450, 25.2700),
                (22, 91.7600, 25.2550),
                (23, 91.7720, 25.2400),
            ]
        },
        {
            "way_id": 100004,
            "highway": "trunk",
            "name": "Tezpur - Kaziranga Asian Highway (AH-1)",
            "ref": "AH-1",
            "lanes": "4",
            "surface": "asphalt",
            "maxspeed": "80",
            "nodes": [
                (30, 92.8000, 26.6300),
                (31, 92.8300, 26.6150),
                (32, 92.8700, 26.5900),
                (33, 92.9200, 26.5700),
                (34, 92.9700, 26.5500),
            ]
        },
        {
            "way_id": 100005,
            "highway": "residential",
            "name": "Zoo Road Tiniali Connector",
            "lanes": "2",
            "surface": "concrete",
            "nodes": [
                (40, 91.7750, 26.1650),
                (41, 91.7780, 26.1680),
                (42, 91.7820, 26.1710),
            ]
        }
    ]

    created_node_ids = set()
    for r in sample_roads:
        node_ids = []
        for nid, lon, lat in r["nodes"]:
            if nid not in created_node_ids:
                node = osmium.osm.mutable.Node(id=nid, location=(lon, lat))
                writer.add_node(node)
                created_node_ids.add(nid)
            node_ids.append(nid)

        tags = {
            "highway": r["highway"],
            "name": r["name"],
        }
        for k in ("ref", "lanes", "surface", "maxspeed", "bridge", "oneway"):
            if k in r:
                tags[k] = r[k]

        way = osmium.osm.mutable.Way(id=r["way_id"], nodes=node_ids, tags=tags)
        writer.add_way(way)

    writer.close()
    print("Sample NER PBF generated successfully.")


class RoadExtractorHandler(osmium.SimpleHandler):
    """
    PyOsmium handler to extract ways with 'highway' tag and their node geometries.
    """
    def __init__(self):
        super().__init__()
        self.roads = []

    def way(self, w):
        if "highway" not in w.tags:
            return

        highway_type = w.tags.get("highway")
        # Ignore non-road elements
        if highway_type in ("footway", "pedestrian", "steps", "path", "cycleway", "bridleway"):
            return

        coords = []
        for n in w.nodes:
            if n.location.valid():
                coords.append((n.lon, n.lat))

        if len(coords) < 2:
            return

        self.roads.append({
            "osm_way_id": w.id,
            "highway": highway_type,
            "name": w.tags.get("name"),
            "ref": w.tags.get("ref"),
            "lanes": parse_int_tag(w.tags.get("lanes")),
            "surface": w.tags.get("surface"),
            "bridge": parse_boolean_tag(w.tags.get("bridge")),
            "oneway": parse_boolean_tag(w.tags.get("oneway")),
            "maxspeed": w.tags.get("maxspeed"),
            "coords": coords
        })


def segment_and_store_roads(roads_data, db: Session):
    """
    Takes parsed road data, projects geometries to UTM, splits lines > 500m,
    and inserts road segment records into PostGIS.
    """
    total_segments_inserted = 0
    total_distance_m = 0.0

    for road in roads_data:
        line_wgs84 = LineString(road["coords"])
        line_metric = transform(transformer_to_metric, line_wgs84)
        total_len_m = line_metric.length

        if total_len_m <= 0:
            continue

        if total_len_m <= TARGET_SEGMENT_LENGTH_M:
            num_segments = 1
        else:
            num_segments = math.ceil(total_len_m / TARGET_SEGMENT_LENGTH_M)

        step_len = total_len_m / num_segments

        for i in range(num_segments):
            start_d = i * step_len
            end_d = min((i + 1) * step_len, total_len_m)

            sub_line_metric = substring(line_metric, start_d, end_d)
            sub_line_wgs84 = transform(transformer_to_wgs84, sub_line_metric)
            seg_len_m = sub_line_metric.length

            # Convert Shapely LineString WGS84 to WKB/GeoAlchemy2 for PostGIS insertion
            wkb_geom = from_shape(sub_line_wgs84, srid=4326)

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

    db.commit()
    return total_segments_inserted, total_distance_m


def main():
    if len(sys.argv) > 1:
        pbf_path = sys.argv[1]
    else:
        pbf_path = os.path.join(os.path.dirname(__file__), "sample_ner.pbf")
        if not os.path.exists(pbf_path):
            create_sample_ner_pbf(pbf_path)

    if not os.path.exists(pbf_path):
        print(f"Error: PBF file not found at {pbf_path}")
        sys.exit(1)

    print(f"Processing OSM PBF file: {pbf_path}")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    # Extract roads with pyosmium
    handler = RoadExtractorHandler()
    idx = osmium.index.create_map("flex_mem")
    lh = osmium.NodeLocationsForWays(idx)
    lh.ignore_errors()

    reader = osmium.io.Reader(pbf_path)
    osmium.apply(reader, lh, handler)
    reader.close()

    print(f"Extracted {len(handler.roads)} road ways from OSM PBF.")

    # Insert into database
    db = SessionLocal()
    try:
        segments_cnt, total_dist_m = segment_and_store_roads(handler.roads, db)
        print(f"\n--- Import Complete ---")
        print(f"Total Road Segments Inserted: {segments_cnt}")
        print(f"Total Road Distance: {total_dist_m / 1000.0:.2f} km")
    finally:
        db.close()


if __name__ == "__main__":
    main()
