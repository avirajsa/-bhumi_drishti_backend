from typing import Any, Dict, List, Optional
from pydantic import BaseModel


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
