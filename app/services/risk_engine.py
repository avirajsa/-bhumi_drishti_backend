from typing import Dict, Any, Tuple
from app.db.models import SegmentFeature, RoadSegment


def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, val))


def compute_flood_hazard(feat: SegmentFeature) -> float:
    # 24h rainfall contribution (up to 0.50)
    rain_score = min(0.50, (feat.rainfall_24h_mm / 120.0) * 0.50)
    
    # Flood zone contribution (up to 0.25)
    zone_score = 0.25 if feat.within_flood_zone else 0.0
    
    # River proximity contribution (up to 0.15)
    if feat.distance_to_river_m < 100:
        river_score = 0.15
    elif feat.distance_to_river_m < 300:
        river_score = 0.08
    else:
        river_score = 0.0
        
    # Recent field reports contribution (up to 0.25)
    report_score = min(0.25, feat.flood_reports_24h * 0.125)

    total = rain_score + zone_score + river_score + report_score
    return round(clamp(total), 2)


def compute_landslide_hazard(feat: SegmentFeature) -> float:
    # Slope contribution (up to 0.40)
    slope_score = min(0.40, (feat.slope_deg / 25.0) * 0.40)
    
    # Cumulative 72h rainfall contribution (up to 0.40)
    rain_score = min(0.40, (feat.rainfall_72h_mm / 200.0) * 0.40)
    
    # Roughness contribution (up to 0.10)
    rough_score = min(0.10, feat.terrain_roughness * 0.10)
    
    # Field reports contribution (up to 0.25)
    report_score = min(0.25, feat.landslide_reports_24h * 0.125)

    total = slope_score + rain_score + rough_score + report_score
    return round(clamp(total), 2)


def compute_road_damage_hazard(feat: SegmentFeature, segment: RoadSegment = None) -> float:
    # Damage reports in past 30 days (up to 0.50)
    damage_score = min(0.50, (feat.road_damage_reports_30d / 3.0) * 0.50)
    
    # Active construction (up to 0.30)
    construction_score = 0.30 if feat.construction_active else 0.0
    
    # Unpaved/dirt surface penalty (up to 0.20)
    surface_score = 0.0
    if segment and segment.surface:
        s = segment.surface.lower()
        if s in ("unpaved", "dirt", "gravel", "earth", "ground"):
            surface_score = 0.20

    total = damage_score + construction_score + surface_score
    return round(clamp(total), 2)


def compute_congestion_hazard(feat: SegmentFeature) -> float:
    total = clamp(feat.congestion_ratio)
    return round(total, 2)


def evaluate_segment_risk(feat: SegmentFeature, segment: RoadSegment = None) -> Tuple[float, str, Dict[str, float]]:
    """
    Computes flood, landslide, road damage, congestion hazards and overall blockage risk.
    Returns (overall_blockage_risk, risk_category, hazard_dict)
    """
    h_flood = compute_flood_hazard(feat)
    h_landslide = compute_landslide_hazard(feat)
    h_damage = compute_road_damage_hazard(feat, segment)
    h_congestion = compute_congestion_hazard(feat)

    # Max hazard represents the highest individual vulnerability factor
    max_hazard = max(h_flood, h_landslide, h_damage, h_congestion)
    avg_other_hazards = (h_flood + h_landslide + h_damage + h_congestion - max_hazard) / 3.0

    # Composite blockage risk heavily reflects severe single-point hazards
    overall_raw = (0.70 * max_hazard) + (0.30 * avg_other_hazards)
    overall_risk = round(clamp(overall_raw), 2)

    # Risk Category mapping
    if overall_risk >= 0.75:
        category = "CRITICAL"
    elif overall_risk >= 0.55:
        category = "HIGH"
    elif overall_risk >= 0.30:
        category = "MEDIUM"
    else:
        category = "LOW"

    hazards = {
        "flood": h_flood,
        "landslide": h_landslide,
        "road_damage": h_damage,
        "congestion": h_congestion
    }

    return overall_risk, category, hazards
