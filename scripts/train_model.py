#!/usr/bin/env python3
"""
XGBoost Machine Learning Training Pipeline for Road Blockage Risk Prediction (NER India)

Usage:
    python scripts/train_model.py
"""

import sys
import os
import joblib
import numpy as np
from typing import Tuple, List, Dict, Any
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, SessionLocal
from app.db.models import RoadSegment, SegmentFeature, HistoricalIncident

from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, precision_score, recall_score


FEATURE_NAMES = [
    "elevation_m",
    "slope_deg",
    "terrain_roughness",
    "distance_to_river_m",
    "distance_to_stream_m",
    "within_flood_zone",
    "rainfall_1h_mm",
    "rainfall_6h_mm",
    "rainfall_24h_mm",
    "rainfall_72h_mm",
    "flood_events_1y",
    "landslide_events_1y",
    "blockages_1y",
    "road_damage_reports_30d",
    "construction_active",
    "congestion_ratio",
    "flood_reports_24h",
    "landslide_reports_24h",
    "length_m",
    "lanes",
]


def extract_dataset_from_postgis(db: Session) -> Tuple[np.ndarray, np.ndarray, List[int]]:
    segments = db.query(RoadSegment).all()
    X = []
    y = []
    segment_ids = []

    for seg in segments:
        feat = db.query(SegmentFeature).filter(SegmentFeature.segment_id == seg.segment_id).first()
        if not feat:
            continue

        # Count severe historical incidents for this segment
        incident_count = db.query(HistoricalIncident).filter(
            HistoricalIncident.segment_id == seg.segment_id,
            HistoricalIncident.severity >= 0.45
        ).count()

        # Binary target label: 1 if segment has severe historical incident logs, 0 otherwise
        target_label = 1 if (incident_count > 0 or feat.blockages_1y >= 2) else 0

        vector = [
            float(feat.elevation_m),
            float(feat.slope_deg),
            float(feat.terrain_roughness),
            float(feat.distance_to_river_m),
            float(feat.distance_to_stream_m),
            1.0 if feat.within_flood_zone else 0.0,
            float(feat.rainfall_1h_mm),
            float(feat.rainfall_6h_mm),
            float(feat.rainfall_24h_mm),
            float(feat.rainfall_72h_mm),
            float(feat.flood_events_1y),
            float(feat.landslide_events_1y),
            float(feat.blockages_1y),
            float(feat.road_damage_reports_30d),
            1.0 if feat.construction_active else 0.0,
            float(feat.congestion_ratio),
            float(feat.flood_reports_24h),
            float(feat.landslide_reports_24h),
            float(seg.length_m),
            float(seg.lanes if seg.lanes else 2),
        ]

        X.append(vector)
        y.append(target_label)
        segment_ids.append(seg.segment_id)

    return np.array(X), np.array(y), segment_ids


def train_and_save_ml_model():
    print("Extracting feature vector dataset & ground-truth labels from PostGIS...")
    db = SessionLocal()
    try:
        X, y, segment_ids = extract_dataset_from_postgis(db)
        print(f"Extracted {X.shape[0]} samples with {X.shape[1]} features.")
        print(f"Class Balance: {np.sum(y == 1)} Blocked/High-Risk (1), {np.sum(y == 0)} Safe (0)")

        if len(X) < 10:
            print("Error: Not enough data samples to train model.")
            return

        # Train / Test split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

        # Train XGBoost Classifier
        clf = XGBClassifier(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.05,
            eval_metric="logloss",
            random_state=42,
        )
        clf.fit(X_train, y_train)

        # Evaluate performance
        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 1.0
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)

        print("\n--- XGBoost Model Evaluation Results ---")
        print(f"Accuracy:  {acc * 100:.2f}%")
        print(f"ROC-AUC:   {auc:.4f}")
        print(f"Precision: {prec:.4f}")
        print(f"Recall:    {rec:.4f}")

        # Compute feature importances
        importances = clf.feature_importances_
        feature_importance_dict = {
            name: round(float(imp), 4)
            for name, imp in sorted(zip(FEATURE_NAMES, importances), key=lambda t: t[1], reverse=True)
        }

        print("\nTop 5 XGBoost Features by Gain:")
        for name, imp in list(feature_importance_dict.items())[:5]:
            print(f"  - {name}: {imp:.4f}")

        # Ensure models directory exists
        models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
        os.makedirs(models_dir, exist_ok=True)
        model_filepath = os.path.join(models_dir, "road_risk_model.joblib")

        model_artifact = {
            "model": clf,
            "feature_names": FEATURE_NAMES,
            "metrics": {
                "accuracy": round(acc, 4),
                "roc_auc": round(auc, 4),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
            },
            "feature_importances": feature_importance_dict,
            "trained_at": str(np.datetime64("now")),
            "model_type": "XGBoostClassifier v1.0",
        }

        joblib.dump(model_artifact, model_filepath)
        print(f"\nTrained XGBoost model saved successfully to: {model_filepath}")

    finally:
        db.close()


if __name__ == "__main__":
    train_and_save_ml_model()
