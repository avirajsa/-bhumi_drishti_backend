#!/usr/bin/env python3

"""
XGBoost Training Pipeline for Bhumi Drishti
Road Disruption Susceptibility Prediction

Usage:
    uv run python scripts/train_model.py
"""

import os
import sys
import joblib
import numpy as np

from sqlalchemy import text

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    roc_auc_score,
    precision_score,
    recall_score,
    confusion_matrix,
    classification_report,
)

from xgboost import XGBClassifier


# ---------------------------------------------------------
# PROJECT PATH
# ---------------------------------------------------------

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

sys.path.insert(0, PROJECT_ROOT)


from app.db.database import SessionLocal


# ---------------------------------------------------------
# FEATURES
# ---------------------------------------------------------

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

    "road_damage_reports_30d",
    "construction_active",
    "congestion_ratio",

    "flood_reports_24h",
    "landslide_reports_24h",

    "length_m",
    "lanes",
]


# ---------------------------------------------------------
# DATA EXTRACTION
# ---------------------------------------------------------

def extract_dataset_from_postgis(db):
    """
    Extract training data directly using PostgreSQL.

    Target:
        1 = segment has at least one severe historical incident
        0 = otherwise

    Severe incident:
        historical_incidents.severity >= 0.45
    """

    print("Extracting dataset from PostGIS...")

    query = text("""
        SELECT

            rs.segment_id,

            sf.elevation_m,
            sf.slope_deg,
            sf.terrain_roughness,

            sf.distance_to_river_m,
            sf.distance_to_stream_m,
            sf.within_flood_zone,

            sf.rainfall_1h_mm,
            sf.rainfall_6h_mm,
            sf.rainfall_24h_mm,
            sf.rainfall_72h_mm,

            sf.flood_events_1y,
            sf.landslide_events_1y,

            sf.road_damage_reports_30d,
            sf.construction_active,
            sf.congestion_ratio,

            sf.flood_reports_24h,
            sf.landslide_reports_24h,

            rs.length_m,
            COALESCE(rs.lanes, 2) AS lanes,

            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM historical_incidents hi
                    WHERE hi.segment_id = rs.segment_id
                      AND hi.severity >= 0.45
                )
                THEN 1
                ELSE 0
            END AS target

        FROM road_segments rs

        INNER JOIN segment_features sf
            ON sf.segment_id = rs.segment_id
    """)

    rows = db.execute(query).fetchall()

    print(f"Rows retrieved: {len(rows):,}")

    X = []
    y = []
    segment_ids = []

    for row in rows:

        values = list(row)

        segment_id = values[0]

        # Feature columns are everything after segment_id
        # and before target.
        features = values[1:-1]

        target = values[-1]

        # Convert NULL values to 0.
        #
        # Ideally, important missing data should be handled
        # more carefully later. For this prototype this keeps
        # the pipeline simple.
        feature_vector = [
            float(value) if value is not None else 0.0
            for value in features
        ]

        X.append(feature_vector)
        y.append(int(target))
        segment_ids.append(segment_id)

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.int32)

    return X, y, segment_ids


# ---------------------------------------------------------
# TRAIN MODEL
# ---------------------------------------------------------

def train_and_save_ml_model():

    print()
    print("=" * 60)
    print("BHUMI DRISHTI - XGBOOST TRAINING")
    print("=" * 60)
    print()

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # LOAD DATA
        # -------------------------------------------------

        X, y, segment_ids = extract_dataset_from_postgis(db)

        print()
        print("Dataset")
        print("-" * 40)

        print(f"Samples : {X.shape[0]:,}")
        print(f"Features: {X.shape[1]}")

        if X.shape[1] != len(FEATURE_NAMES):
            raise RuntimeError(
                f"Feature mismatch: "
                f"X contains {X.shape[1]} columns but "
                f"FEATURE_NAMES contains {len(FEATURE_NAMES)}."
            )

        # -------------------------------------------------
        # CLASS BALANCE
        # -------------------------------------------------

        positive_count = int(np.sum(y == 1))
        negative_count = int(np.sum(y == 0))

        print(f"Positive: {positive_count:,}")
        print(f"Negative: {negative_count:,}")

        if positive_count == 0:
            raise RuntimeError(
                "No positive samples found. "
                "There are no historical incidents with "
                "severity >= 0.45."
            )

        if negative_count == 0:
            raise RuntimeError(
                "No negative samples found."
            )

        positive_ratio = positive_count / len(y)

        print(f"Positive ratio: {positive_ratio * 100:.2f}%")

        # -------------------------------------------------
        # CLASS WEIGHT
        # -------------------------------------------------

        scale_pos_weight = negative_count / positive_count

        print(
            f"scale_pos_weight: "
            f"{scale_pos_weight:.2f}"
        )

        # -------------------------------------------------
        # TRAIN / TEST SPLIT
        # -------------------------------------------------

        print()
        print("Splitting dataset...")

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.25,
            random_state=42,
            stratify=y,
        )

        print(f"Training samples: {len(X_train):,}")
        print(f"Testing samples : {len(X_test):,}")

        # -------------------------------------------------
        # XGBOOST
        # -------------------------------------------------

        print()
        print("Training XGBoost...")

        model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,

            subsample=0.8,
            colsample_bytree=0.8,

            objective="binary:logistic",
            eval_metric="auc",

            scale_pos_weight=scale_pos_weight,

            random_state=42,
            n_jobs=-1,
        )

        model.fit(
            X_train,
            y_train,
        )

        print("Training complete.")

        # -------------------------------------------------
        # PREDICTION
        # -------------------------------------------------

        y_pred = model.predict(X_test)

        y_prob = model.predict_proba(X_test)[:, 1]

        # -------------------------------------------------
        # METRICS
        # -------------------------------------------------

        accuracy = accuracy_score(
            y_test,
            y_pred,
        )

        precision = precision_score(
            y_test,
            y_pred,
            zero_division=0,
        )

        recall = recall_score(
            y_test,
            y_pred,
            zero_division=0,
        )

        if len(np.unique(y_test)) > 1:
            roc_auc = roc_auc_score(
                y_test,
                y_prob,
            )
        else:
            roc_auc = float("nan")

        # -------------------------------------------------
        # RESULTS
        # -------------------------------------------------

        print()
        print("=" * 60)
        print("MODEL EVALUATION")
        print("=" * 60)

        print(f"Accuracy : {accuracy:.4f}")
        print(f"ROC-AUC  : {roc_auc:.4f}")
        print(f"Precision: {precision:.4f}")
        print(f"Recall   : {recall:.4f}")

        # -------------------------------------------------
        # CONFUSION MATRIX
        # -------------------------------------------------

        cm = confusion_matrix(
            y_test,
            y_pred,
        )

        print()
        print("Confusion Matrix")
        print("-" * 40)

        print(cm)

        # -------------------------------------------------
        # CLASSIFICATION REPORT
        # -------------------------------------------------

        print()
        print("Classification Report")
        print("-" * 40)

        print(
            classification_report(
                y_test,
                y_pred,
                target_names=[
                    "Safe",
                    "Disrupted",
                ],
                zero_division=0,
            )
        )

        # -------------------------------------------------
        # FEATURE IMPORTANCE
        # -------------------------------------------------

        print()
        print("Feature Importance")
        print("-" * 40)

        importances = model.feature_importances_

        feature_importance = sorted(
            zip(FEATURE_NAMES, importances),
            key=lambda x: x[1],
            reverse=True,
        )

        feature_importance_dict = {}

        for name, importance in feature_importance:

            importance = float(importance)

            feature_importance_dict[name] = round(
                importance,
                6,
            )

            print(
                f"{name:<30} "
                f"{importance:.6f}"
            )

        # -------------------------------------------------
        # SAVE MODEL
        # -------------------------------------------------

        models_dir = os.path.join(
            PROJECT_ROOT,
            "models",
        )

        os.makedirs(
            models_dir,
            exist_ok=True,
        )

        model_path = os.path.join(
            models_dir,
            "road_risk_model.joblib",
        )

        artifact = {
            "model": model,

            "feature_names": FEATURE_NAMES,

            "metrics": {
                "accuracy": round(
                    float(accuracy),
                    4,
                ),

                "roc_auc": round(
                    float(roc_auc),
                    4,
                ),

                "precision": round(
                    float(precision),
                    4,
                ),

                "recall": round(
                    float(recall),
                    4,
                ),
            },

            "feature_importances": feature_importance_dict,

            "model_type": "XGBoostClassifier",

            "target_definition": (
                "1 if segment has at least one "
                "historical incident with severity >= 0.45, "
                "otherwise 0"
            ),

            "trained_at": str(
                np.datetime64("now")
            ),
        }

        joblib.dump(
            artifact,
            model_path,
        )

        print()
        print("=" * 60)
        print("MODEL SAVED")
        print("=" * 60)

        print(model_path)
        print()

    finally:
        db.close()


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":
    train_and_save_ml_model()
