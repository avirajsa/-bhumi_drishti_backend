from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.segment import MLRiskResponse
from app.services.ml_engine import predict_segment_ml_risk
from scripts.train_model import train_and_save_ml_model, extract_dataset_from_postgis

router = APIRouter(tags=["machine learning"])


@router.get("/segments/{segment_id}/ml-risk", response_model=MLRiskResponse)
def get_ml_segment_risk(
    segment_id: int,
    db: Session = Depends(get_db),
):
    """
    Predict road blockage probability, ML risk category, and top feature importances using the trained Machine Learning model.
    """
    prediction = predict_segment_ml_risk(db=db, segment_id=segment_id)
    if not prediction:
        raise HTTPException(status_code=404, detail=f"Road segment with id {segment_id} not found")
    return prediction


@router.post("/ml/train")
def train_machine_learning_model():
    """
    Trigger retraining of the ML model on current PostGIS feature vectors and historical incident ground-truth labels.
    """
    try:
        train_and_save_ml_model()
        return {
            "status": "success",
            "message": "Machine Learning model retrained and updated successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model training failed: {str(e)}")
