#!/usr/bin/env python3
"""
Feature Vector & Risk Scoring Seeder for Road Risk System (NER India)

Usage:
    python scripts/seed_features.py
"""

import sys
import os
import random

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, SessionLocal, Base
from app.db.models import RoadSegment, SegmentFeature, SegmentRisk
from app.services.segments import recalculate_and_save_risk
from app.services.risk_engine import evaluate_segment_risk


def seed_features_and_risks():
    print("Seeding feature vectors & calculating risk scores for all road segments...")
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        segments = db.query(RoadSegment).all()
        print(f"Found {len(segments)} road segments in PostGIS database.")

        random.seed(42)  # Deterministic seed for reproducible testing

        count_updated = 0
        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}

        for seg in segments:
            # Deterministic variation based on segment_id
            sid = seg.segment_id
            
            # Mountain/hill simulation for certain segments (e.g. Cherrapunji / Shillong routes)
            is_mountain_route = (seg.road_type in ("tertiary", "secondary")) or (sid % 4 == 0)
            is_monsoon_heavy = (sid % 3 == 0) or (sid % 7 == 0)
            
            elevation = round(150.0 + (sid * 17) % 1200, 1)
            slope = round(15.0 + (sid * 7) % 25, 1) if is_mountain_route else round(2.0 + (sid * 3) % 8, 1)
            roughness = round(0.1 + (sid % 8) * 0.1, 2)
            
            river_dist = round(30.0 + (sid * 29) % 800, 1)
            stream_dist = round(10.0 + (sid * 13) % 300, 1)
            within_flood = (river_dist < 150) or (sid % 5 == 0)

            # Heavy monsoon rainfall simulation (mm)
            if is_monsoon_heavy:
                rain_1h = round(20.0 + (sid % 30), 1)
                rain_6h = round(50.0 + (sid % 60), 1)
                rain_24h = round(120.0 + (sid % 80), 1)
                rain_72h = round(220.0 + (sid % 120), 1)
            else:
                rain_1h = round((sid % 5) * 2.0, 1)
                rain_6h = round((sid % 10) * 4.0, 1)
                rain_24h = round((sid % 15) * 8.0, 1)
                rain_72h = round((sid % 20) * 12.0, 1)

            # Historical events
            flood_1y = (sid % 4) if within_flood else 0
            landslide_1y = (sid % 3) if is_mountain_route else 0
            blockages_1y = flood_1y + landslide_1y + (sid % 2)

            # Infrastructure & traffic
            damage_30d = (sid % 3)
            construction = (sid % 8 == 0)
            congestion = round(0.1 + (sid % 7) * 0.12, 2)

            # Field reports
            flood_reports = 2 if (within_flood and rain_24h > 100) else 0
            landslide_reports = 1 if (is_mountain_route and rain_72h > 150) else 0

            # Check existing feature record
            feat = db.query(SegmentFeature).filter(SegmentFeature.segment_id == sid).first()
            if not feat:
                feat = SegmentFeature(segment_id=sid)
                db.add(feat)

            feat.elevation_m = elevation
            feat.slope_deg = slope
            feat.terrain_roughness = roughness
            feat.distance_to_river_m = river_dist
            feat.distance_to_stream_m = stream_dist
            feat.within_flood_zone = within_flood
            feat.rainfall_1h_mm = rain_1h
            feat.rainfall_6h_mm = rain_6h
            feat.rainfall_24h_mm = rain_24h
            feat.rainfall_72h_mm = rain_72h
            feat.flood_events_1y = flood_1y
            feat.landslide_events_1y = landslide_1y
            feat.blockages_1y = blockages_1y
            feat.road_damage_reports_30d = damage_30d
            feat.construction_active = construction
            feat.congestion_ratio = congestion
            feat.flood_reports_24h = flood_reports
            feat.landslide_reports_24h = landslide_reports

            # Calculate and store risk score
            overall_risk, category, hazards = evaluate_segment_risk(feat, seg)
            risk_obj = db.query(SegmentRisk).filter(SegmentRisk.segment_id == sid).first()
            if not risk_obj:
                risk_obj = SegmentRisk(segment_id=sid)
                db.add(risk_obj)

            risk_obj.overall_blockage_risk = overall_risk
            risk_obj.risk_category = category
            risk_obj.hazard_flood = hazards["flood"]
            risk_obj.hazard_landslide = hazards["landslide"]
            risk_obj.hazard_road_damage = hazards["road_damage"]
            risk_obj.hazard_congestion = hazards["congestion"]

            risk_counts[category] = risk_counts.get(category, 0) + 1
            count_updated += 1

        db.commit()

        print(f"\n--- Seeding Complete ---")
        print(f"Total Segments Seeded: {count_updated}")
        print("Risk Category Breakdown:")
        for cat, cnt in risk_counts.items():
            print(f"  {cat}: {cnt} segments")

    finally:
        db.close()


if __name__ == "__main__":
    seed_features_and_risks()
