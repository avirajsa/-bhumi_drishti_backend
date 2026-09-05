from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.segment import GeoJSONFeatureCollection, GeoJSONFeature
from app.services.segments import get_road_segments, get_road_segment_by_id

router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("", response_model=GeoJSONFeatureCollection)
def list_segments(
    road_type: Optional[str] = Query(None, description="Filter by road_type (e.g. primary, secondary)"),
    risk_category: Optional[str] = Query(None, description="Filter by risk category (LOW, MEDIUM, HIGH, CRITICAL)"),
    min_risk: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum overall blockage risk score"),
    min_lon: Optional[float] = Query(None, description="Bounding box minimum longitude"),
    min_lat: Optional[float] = Query(None, description="Bounding box minimum latitude"),
    max_lon: Optional[float] = Query(None, description="Bounding box maximum longitude"),
    max_lat: Optional[float] = Query(None, description="Bounding box maximum latitude"),
    limit: int = Query(500, ge=1, le=1000, description="Max segments to return"),
    db: Session = Depends(get_db),
):
    """
    Get all or filtered road segments as a GeoJSON FeatureCollection with risk scores.
    """
    return get_road_segments(
        db=db,
        road_type=road_type,
        risk_category=risk_category,
        min_risk=min_risk,
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        limit=limit,
    )


@router.get("/{segment_id}", response_model=GeoJSONFeature)
def get_segment(
    segment_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a single road segment by segment_id with metadata, risk score, and GeoJSON geometry.
    """
    segment = get_road_segment_by_id(db=db, segment_id=segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail=f"Road segment with id {segment_id} not found")
    return segment
