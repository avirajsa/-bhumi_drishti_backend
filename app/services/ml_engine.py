import os
import joblib
import numpy as np
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.db.models import RoadSegment, SegmentFeature

MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models", "road_risk_model.joblib"))

_model_cache = None


def get_trained_model():
    global _model_cache
    if _model_cache is None:
        if os.path.exists(MODEL_PATH):
            _model_cache = joblib.load(MODEL_PATH)
        else:
            print(f"Warning: XGBoost ML model file not found at {MODEL_PATH}")
            return None
    return _model_cache


def predict_segment_ml_risk(db: Session, segment_id: int) -> Optional[Dict[str, Any]]:
    segment = db.query(RoadSegment).filter(RoadSegment.segment_id == segment_id).first()
    if not segment:
        return None

    feat = db.query(SegmentFeature).filter(SegmentFeature.segment_id == segment_id).first()
    if not feat:
        return None

    model_bundle = get_trained_model()
    if not model_bundle:
        return {
            "segment_id": segment_id,
            "ml_blockage_probability": 0.0,
            "ml_risk_category": "UNKNOWN (Model not trained yet)",
            "top_feature_importance": {},
            "model_name": "XGBoostClassifier v1.0",
        }

    clf = model_bundle["model"]
    
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
        float(segment.length_m),
        float(segment.lanes if segment.lanes else 2),
    ]

    X_sample = np.array([vector])
    prob_blocked = round(float(clf.predict_proba(X_sample)[0][1]), 4)

    if prob_blocked >= 0.75:
        category = "CRITICAL"
    elif prob_blocked >= 0.55:
        category = "HIGH"
    elif prob_blocked >= 0.30:
        category = "MEDIUM"
    else:
        category = "LOW"

    top_importances = dict(list(model_bundle.get("feature_importances", {}).items())[:5])

    return {
        "segment_id": segment_id,
        "ml_blockage_probability": prob_blocked,
        "ml_risk_category": category,
        "top_feature_importance": top_importances,
        "model_name": model_bundle.get("model_type", "XGBoostClassifier v1.0"),
    }
