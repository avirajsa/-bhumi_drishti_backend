from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
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

    # Relationships
    features = relationship("SegmentFeature", back_populates="segment", uselist=False, cascade="all, delete-orphan")
    risk = relationship("SegmentRisk", back_populates="segment", uselist=False, cascade="all, delete-orphan")
    incidents = relationship("HistoricalIncident", back_populates="segment", cascade="all, delete-orphan")
    reports = relationship("FieldReport", back_populates="segment")


class SegmentFeature(Base):
    __tablename__ = "segment_features"

    segment_id = Column(Integer, ForeignKey("road_segments.segment_id", ondelete="CASCADE"), primary_key=True)
    
    # TERRAIN
    elevation_m = Column(Float, default=100.0, nullable=False)
    slope_deg = Column(Float, default=5.0, nullable=False)
    terrain_roughness = Column(Float, default=0.2, nullable=False)

    # HYDROLOGY
    distance_to_river_m = Column(Float, default=500.0, nullable=False)
    distance_to_stream_m = Column(Float, default=200.0, nullable=False)
    within_flood_zone = Column(Boolean, default=False, nullable=False)

    # WEATHER
    rainfall_1h_mm = Column(Float, default=0.0, nullable=False)
    rainfall_6h_mm = Column(Float, default=0.0, nullable=False)
    rainfall_24h_mm = Column(Float, default=0.0, nullable=False)
    rainfall_72h_mm = Column(Float, default=0.0, nullable=False)

    # HISTORY
    flood_events_1y = Column(Integer, default=0, nullable=False)
    landslide_events_1y = Column(Integer, default=0, nullable=False)
    blockages_1y = Column(Integer, default=0, nullable=False)

    # INFRASTRUCTURE
    road_damage_reports_30d = Column(Integer, default=0, nullable=False)
    construction_active = Column(Boolean, default=False, nullable=False)

    # TRAFFIC
    congestion_ratio = Column(Float, default=0.1, nullable=False)

    # FIELD REPORTS
    flood_reports_24h = Column(Integer, default=0, nullable=False)
    landslide_reports_24h = Column(Integer, default=0, nullable=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to segment
    segment = relationship("RoadSegment", back_populates="features")


class SegmentRisk(Base):
    __tablename__ = "segment_risks"

    segment_id = Column(Integer, ForeignKey("road_segments.segment_id", ondelete="CASCADE"), primary_key=True)
    
    overall_blockage_risk = Column(Float, default=0.0, nullable=False, index=True)
    risk_category = Column(String, default="LOW", nullable=False, index=True)
    
    hazard_flood = Column(Float, default=0.0, nullable=False)
    hazard_landslide = Column(Float, default=0.0, nullable=False)
    hazard_road_damage = Column(Float, default=0.0, nullable=False)
    hazard_congestion = Column(Float, default=0.0, nullable=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to segment
    segment = relationship("RoadSegment", back_populates="risk")


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    incident_id = Column(Integer, primary_key=True, autoincrement=True)
    segment_id = Column(Integer, ForeignKey("road_segments.segment_id", ondelete="CASCADE"), nullable=False, index=True)
    incident_type = Column(String, nullable=False, index=True)  # landslide, flood, road_damage, blockage
    severity = Column(Float, default=0.5, nullable=False)
    description = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Point geometry in EPSG:4326 with automatic GiST spatial index
    geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)

    # Relationship back to segment
    segment = relationship("RoadSegment", back_populates="incidents")


class FieldReport(Base):
    __tablename__ = "field_reports"

    report_id = Column(Integer, primary_key=True, autoincrement=True)
    segment_id = Column(Integer, ForeignKey("road_segments.segment_id", ondelete="SET NULL"), nullable=True, index=True)
    reporter_name = Column(String, default="Field Responder", nullable=False)
    reporter_role = Column(String, default="Patrol Officer", nullable=False)  # Patrol Officer, Citizen, Engineer
    report_type = Column(String, nullable=False, index=True)  # flood, landslide, road_damage, blockage
    severity = Column(Float, default=0.5, nullable=False)
    status = Column(String, default="SUBMITTED", nullable=False, index=True)  # SUBMITTED, UNDER_REVIEW, VERIFIED, RESOLVED
    description = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Point geometry in EPSG:4326 with automatic GiST spatial index
    geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)

    # Relationship back to segment
    segment = relationship("RoadSegment", back_populates="reports")
