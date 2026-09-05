from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Feature Group Models
class RoadAttributes(BaseModel):
    road_type: Optional[str] = None
    lanes: Optional[int] = None
    surface: Optional[str] = None
    length_m: float
    bridge: Optional[bool] = None
    oneway: Optional[bool] = None
    maxspeed: Optional[str] = None
    name: Optional[str] = None
    ref: Optional[str] = None


class TerrainFeatures(BaseModel):
    elevation_m: float = Field(..., description="Elevation in meters")
    slope_deg: float = Field(..., description="Slope in degrees")
    terrain_roughness: float = Field(..., description="Terrain roughness index (0.0 to 1.0)")


class HydrologyFeatures(BaseModel):
    distance_to_river_m: float = Field(..., description="Distance to nearest river in meters")
    distance_to_stream_m: float = Field(..., description="Distance to nearest stream in meters")
    within_flood_zone: bool = Field(..., description="Whether segment is in a designated flood zone")


class WeatherFeatures(BaseModel):
    rainfall_1h_mm: float = Field(..., description="Cumulative rainfall last 1 hour (mm)")
    rainfall_6h_mm: float = Field(..., description="Cumulative rainfall last 6 hours (mm)")
    rainfall_24h_mm: float = Field(..., description="Cumulative rainfall last 24 hours (mm)")
    rainfall_72h_mm: float = Field(..., description="Cumulative rainfall last 72 hours (mm)")


class HistoryFeatures(BaseModel):
    flood_events_1y: int = Field(..., description="Flood incidents in past 1 year")
    landslide_events_1y: int = Field(..., description="Landslide incidents in past 1 year")
    blockages_1y: int = Field(..., description="Total road blockages in past 1 year")


class InfrastructureFeatures(BaseModel):
    road_damage_reports_30d: int = Field(..., description="Road damage reports in past 30 days")
    construction_active: bool = Field(..., description="Active roadwork or construction")


class TrafficFeatures(BaseModel):
    congestion_ratio: float = Field(..., description="Traffic congestion ratio (0.0 to 1.0)")


class FieldReportFeatures(BaseModel):
    flood_reports_24h: int = Field(..., description="Field flood reports in past 24 hours")
    landslide_reports_24h: int = Field(..., description="Field landslide reports in past 24 hours")


# Complete Feature Vector Response Model
class SegmentFeatureVectorResponse(BaseModel):
    segment_id: int
    road: RoadAttributes
    terrain: TerrainFeatures
    hydrology: HydrologyFeatures
    weather: WeatherFeatures
    history: HistoryFeatures
    infrastructure: InfrastructureFeatures
    traffic: TrafficFeatures
    field_reports: FieldReportFeatures


# Input Model for Updating Features
class SegmentFeatureUpdateRequest(BaseModel):
    elevation_m: Optional[float] = None
    slope_deg: Optional[float] = None
    terrain_roughness: Optional[float] = None
    distance_to_river_m: Optional[float] = None
    distance_to_stream_m: Optional[float] = None
    within_flood_zone: Optional[bool] = None
    rainfall_1h_mm: Optional[float] = None
    rainfall_6h_mm: Optional[float] = None
    rainfall_24h_mm: Optional[float] = None
    rainfall_72h_mm: Optional[float] = None
    flood_events_1y: Optional[int] = None
    landslide_events_1y: Optional[int] = None
    blockages_1y: Optional[int] = None
    road_damage_reports_30d: Optional[int] = None
    construction_active: Optional[bool] = None
    congestion_ratio: Optional[float] = None
    flood_reports_24h: Optional[int] = None
    landslide_reports_24h: Optional[int] = None


# Risk Response Models
class HazardBreakdown(BaseModel):
    flood: float
    landslide: float
    road_damage: float
    congestion: float


class SegmentRiskResponse(BaseModel):
    segment_id: int
    overall_blockage_risk: float
    risk_category: str  # LOW, MEDIUM, HIGH, CRITICAL
    hazards: HazardBreakdown


# Machine Learning Prediction Response Model
class MLRiskResponse(BaseModel):
    segment_id: int
    ml_blockage_probability: float
    ml_risk_category: str
    top_feature_importance: Dict[str, float]
    model_name: str


# Historical Incident Models
class HistoricalIncidentResponse(BaseModel):
    incident_id: int
    segment_id: int
    incident_type: str
    severity: float
    description: Optional[str] = None
    occurred_at: str


# Dashboard Field Report Models
class FieldReportCreateRequest(BaseModel):
    segment_id: Optional[int] = Field(None, description="Target road segment ID (optional if lat/lon provided)")
    report_type: str = Field(..., description="Report type: 'flood', 'landslide', 'road_damage', or 'blockage'")
    severity: float = Field(0.5, ge=0.0, le=1.0, description="Severity score 0.0 to 1.0")
    reporter_name: Optional[str] = Field("Field Responder", description="Name/organization of reporter")
    reporter_role: Optional[str] = Field("Patrol Officer", description="Role: 'Patrol Officer', 'Citizen', 'Engineer'")
    description: Optional[str] = Field(None, description="Observation details")
    photo_url: Optional[str] = Field(None, description="URL of photo attachment")
    latitude: Optional[float] = Field(None, description="GPS latitude (e.g. 26.14)")
    longitude: Optional[float] = Field(None, description="GPS longitude (e.g. 91.73)")


class FieldReportStatusUpdate(BaseModel):
    status: str = Field(..., description="New status: 'SUBMITTED', 'UNDER_REVIEW', 'VERIFIED', 'RESOLVED'")


class FieldReportResponse(BaseModel):
    report_id: int
    segment_id: Optional[int] = None
    reporter_name: str
    reporter_role: str
    report_type: str
    severity: float
    status: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: str
    updated_at: str


class FieldReportListResponse(BaseModel):
    total_count: int
    reports: List[FieldReportResponse]


# Enhanced Segment Properties for GeoJSON Feature Output
class SegmentProperties(BaseModel):
    segment_id: int
    osm_way_id: int
    road_type: Optional[str] = None
    lanes: Optional[int] = None
    surface: Optional[str] = None
    bridge: Optional[bool] = None
    oneway: Optional[bool] = None
    maxspeed: Optional[str] = None
    name: Optional[str] = None
    ref: Optional[str] = None
    length_m: float
    overall_blockage_risk: Optional[float] = None
    risk_category: Optional[str] = None
    ml_blockage_probability: Optional[float] = None
    ml_risk_category: Optional[str] = None


class GeoJSONGeometry(BaseModel):
    type: str = "LineString"
    coordinates: List[Any]


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: SegmentProperties


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]
