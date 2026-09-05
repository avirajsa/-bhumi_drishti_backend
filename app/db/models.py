from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, func, Index
from geoalchemy2 import Geometry
from app.db.database import Base


class RoadSegment(Base):
    __tablename__ = "road_segments"

    segment_id = Column(Integer, primary_key=True, autoincrement=True)
    osm_way_id = Column(BigInteger, nullable=False, index=True)
    road_type = Column(String, nullable=True, index=True)
    lanes = Column(Integer, nullable=True)
    surface = Column(String, nullable=True)
    bridge = Column(Boolean, nullable=True)
    oneway = Column(Boolean, nullable=True)
    maxspeed = Column(String, nullable=True)
    name = Column(String, nullable=True)
    ref = Column(String, nullable=True)
    length_m = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Geometry column LineString 4326 with automatic GiST index
    geom = Column(Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False)
