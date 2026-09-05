from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import RoadSegment, SegmentFeature
from app.services.segments import recalculate_and_save_risk, get_segment_risk

router = APIRouter(prefix="/reports", tags=["field reports"])


class FieldReportCreate(BaseModel):
    segment_id: int = Field(..., description="Target road segment ID")
    report_type: str = Field(..., description="Report type: 'flood', 'landslide', or 'road_damage'")
    reporter_name: Optional[str] = Field("Field Inspector", description="Name/organization of reporter")
    comment: Optional[str] = Field(None, description="Observation details")


class FieldReportResponse(BaseModel):
    message: str
    segment_id: int
    report_type: str
    updated_risk_category: str
    updated_overall_risk: float


@router.post("", response_model=FieldReportResponse)
def submit_field_report(
    report: FieldReportCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a real-time field incident report (flood, landslide, or road damage) for a segment.
    Instantly updates field report counters in PostGIS and recalculates blockage risk.
    """
    segment = db.query(RoadSegment).filter(RoadSegment.segment_id == report.segment_id).first()
    if not segment:
        raise HTTPException(status_code=404, detail=f"Road segment with id {report.segment_id} not found")

    feat = db.query(SegmentFeature).filter(SegmentFeature.segment_id == report.segment_id).first()
    if not feat:
        feat = SegmentFeature(segment_id=report.segment_id)
        db.add(feat)

    report_type_clean = report.report_type.strip().lower()
    if report_type_clean == "flood":
        feat.flood_reports_24h += 1
    elif report_type_clean == "landslide":
        feat.landslide_reports_24h += 1
    elif report_type_clean in ("road_damage", "damage"):
        feat.road_damage_reports_30d += 1
    else:
        raise HTTPException(status_code=400, detail="Invalid report_type. Must be 'flood', 'landslide', or 'road_damage'")

    db.commit()
    db.refresh(feat)

    # Recalculate risk instantly
    risk = recalculate_and_save_risk(db, segment, feat)

    return {
        "message": "Field report recorded successfully and risk score updated.",
        "segment_id": report.segment_id,
        "report_type": report_type_clean,
        "updated_risk_category": risk.risk_category,
        "updated_overall_risk": risk.overall_blockage_risk,
    }
