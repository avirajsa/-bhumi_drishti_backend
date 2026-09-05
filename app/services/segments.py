import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_Intersects

from app.db.models import RoadSegment


def get_road_segments(
    db: Session,
    road_type: Optional[str] = None,
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Fetch road segments with optional filtering by road_type and/or bounding box.
    Returns a GeoJSON FeatureCollection dictionary.
    """
    query = db.query(RoadSegment, ST_AsGeoJSON(RoadSegment.geom).label("geojson"))

    if road_type:
        query = query.filter(RoadSegment.road_type == road_type)

    if min_lon is not None and min_lat is not None and max_lon is not None and max_lat is not None:
        bbox_geom = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        query = query.filter(ST_Intersects(RoadSegment.geom, bbox_geom))

    results = query.limit(limit).all()

    features = []
    for segment, geojson_str in results:
        geometry = json.loads(geojson_str)
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "segment_id": segment.segment_id,
                "osm_way_id": segment.osm_way_id,
                "road_type": segment.road_type,
                "lanes": segment.lanes,
                "surface": segment.surface,
                "bridge": segment.bridge,
                "oneway": segment.oneway,
                "maxspeed": segment.maxspeed,
                "name": segment.name,
                "ref": segment.ref,
                "length_m": round(segment.length_m, 2),
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }


def get_road_segment_by_id(db: Session, segment_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch a single road segment by segment_id.
    Returns a GeoJSON Feature dictionary or None if not found.
    """
    result = db.query(
        RoadSegment, ST_AsGeoJSON(RoadSegment.geom).label("geojson")
    ).filter(RoadSegment.segment_id == segment_id).first()

    if not result:
        return None

    segment, geojson_str = result
    geometry = json.loads(geojson_str)

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "segment_id": segment.segment_id,
            "osm_way_id": segment.osm_way_id,
            "road_type": segment.road_type,
            "lanes": segment.lanes,
            "surface": segment.surface,
            "bridge": segment.bridge,
            "oneway": segment.oneway,
            "maxspeed": segment.maxspeed,
            "name": segment.name,
            "ref": segment.ref,
            "length_m": round(segment.length_m, 2),
        }
    }
