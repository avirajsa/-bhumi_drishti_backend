#!/usr/bin/env python3
"""
Automated IMD (India Meteorological Department) Weather Sync Engine for Road Risk Backend (NER India)

Usage:
    python scripts/sync_weather.py
"""

import sys
import os
import json
from typing import Dict, Tuple
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_AsGeoJSON

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, SessionLocal
from app.db.models import RoadSegment, SegmentFeature
from app.services.imd_weather import fetch_imd_weather_for_coordinate
from app.services.segments import recalculate_and_save_risk


def get_segment_centroid(geojson_str: str) -> Tuple[float, float]:
    geom = json.loads(geojson_str)
    coords = geom.get("coordinates", [])
    if not coords:
        return (91.73, 26.14)
    mid_idx = len(coords) // 2
    return coords[mid_idx][0], coords[mid_idx][1]


def sync_imd_weather_and_update_risks():
    print("Starting automated IMD (India Meteorological Department) weather sync for PostGIS road segments...")
    db = SessionLocal()
    try:
        results = db.query(RoadSegment, ST_AsGeoJSON(RoadSegment.geom).label("geojson")).all()
        print(f"Found {len(results)} segments to update using IMD weather data.")

        # Group segments into 0.05° weather grid (~5km resolution across NER)
        grid_cache: Dict[Tuple[float, float], Tuple[float, float, float, float]] = {}
        feats_dict = {f.segment_id: f for f in db.query(SegmentFeature).all()}
        updated_count = 0

        for segment, geojson_str in results:
            lon, lat = get_segment_centroid(geojson_str)
            grid_key = (round(lat, 2), round(lon, 2))

            if grid_key not in grid_cache:
                grid_cache[grid_key] = fetch_imd_weather_for_coordinate(grid_key[0], grid_key[1])

            r1, r6, r24, r72 = grid_cache[grid_key]

            # Update segment features in PostGIS
            feat = feats_dict.get(segment.segment_id)
            if not feat:
                feat = SegmentFeature(segment_id=segment.segment_id)
                db.add(feat)
                feats_dict[segment.segment_id] = feat

            feat.rainfall_1h_mm = r1
            feat.rainfall_6h_mm = r6
            feat.rainfall_24h_mm = r24
            feat.rainfall_72h_mm = r72

            # Recalculate segment risk score without individual commits
            recalculate_and_save_risk(db, segment, feat, commit=False)
            updated_count += 1

        db.commit()
        print(f"\n--- IMD Weather Sync Complete ---")
        print(f"IMD Weather Grid Cells Processed: {len(grid_cache)}")
        print(f"Road Segments Updated: {updated_count}")

    finally:
        db.close()


if __name__ == "__main__":
    sync_imd_weather_and_update_risks()
