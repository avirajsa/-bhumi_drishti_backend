#!/usr/bin/env python3
"""
Master Database Seeding & XGBoost Training Pipeline for Road Risk Backend (NER India)

Usage:
    python scripts/populate_db.py
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, Base
from sqlalchemy import text

from scripts.import_osm import main as import_osm_main
from scripts.seed_features import seed_features_and_risks
from scripts.seed_historical_incidents import seed_historical_incidents
from scripts.sync_weather import sync_imd_weather_and_update_risks
from scripts.train_model import train_and_save_ml_model


def populate_and_setup_all():
    print("=================================================================")
    print(" ROAD RISK & ACCESSIBILITY SYSTEM (NER INDIA) — MASTER PIPELINE ")
    print("=================================================================")

    # 1. Initialize PostGIS extension and database tables
    print("\n[Step 1/5] Initializing PostGIS Extension and Database Tables...")
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully.")

    # 2. Extract OSM Highways and Segment Roads into ~500m chunks
    print("\n[Step 2/5] Importing OSM Data & Segmenting Roads (~500m metric CRS)...")
    import_osm_main()

    # 3. Seed Feature Vectors across all 8 feature groups
    print("\n[Step 3/5] Seeding Feature Vectors (Terrain, Hydrology, Weather, History, Infrastructure, Traffic, Reports)...")
    seed_features_and_risks()

    # 4. Seed Historical Ground-Truth Disaster Incidents & Sync IMD Weather
    print("\n[Step 4/5] Seeding Historical Disaster Incidents & Syncing Live IMD Weather...")
    seed_historical_incidents()
    sync_imd_weather_and_update_risks()

    # 5. Train XGBoost Machine Learning Classifier
    print("\n[Step 5/5] Training XGBoost Machine Learning Classifier...")
    train_and_save_ml_model()

    print("\n=================================================================")
    print(" PIPELINE COMPLETE: PostGIS DB Populated & XGBoost Model Trained! ")
    print("=================================================================")


if __name__ == "__main__":
    populate_and_setup_all()
