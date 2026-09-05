from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.segment import (
    SegmentFeatureVectorResponse,
    SegmentFeatureUpdateRequest,
    SegmentRiskResponse
)
from app.services.segments import (
    get_segment_features,
    update_segment_features,
    get_segment_risk
)

router = APIRouter(prefix="/segments", tags=["features & risk"])


@router.get("/{segment_id}/features", response_model=SegmentFeatureVectorResponse)
def read_segment_features(
    segment_id: int,
    db: Session = Depends(get_db),
):
    """
    Get full multi-dimensional feature vector (Road, Terrain, Hydrology, Weather, History, Infrastructure, Traffic, Field Reports) for a segment.
    """
    features = get_segment_features(db=db, segment_id=segment_id)
    if not features:
        raise HTTPException(status_code=404, detail=f"Road segment with id {segment_id} not found")
    return features


@router.put("/{segment_id}/features", response_model=SegmentFeatureVectorResponse)
def modify_segment_features(
    segment_id: int,
    body: SegmentFeatureUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update feature vector parameters (e.g. live rainfall, field report updates) for a segment.
    Automatically recalculates risk score and risk category.
    """
    update_data = body.model_dump(exclude_unset=True)
    updated_features = update_segment_features(db=db, segment_id=segment_id, update_dict=update_data)
    if not updated_features:
        raise HTTPException(status_code=404, detail=f"Road segment with id {segment_id} not found")
    return updated_features


@router.get("/{segment_id}/risk", response_model=SegmentRiskResponse)
def read_segment_risk(
    segment_id: int,
    db: Session = Depends(get_db),
):
    """
    Get current blockage risk assessment, risk category, and individual hazard scores.
    """
    risk = get_segment_risk(db=db, segment_id=segment_id)
    if not risk:
        raise HTTPException(status_code=404, detail=f"Road segment with id {segment_id} not found")
    return risk
