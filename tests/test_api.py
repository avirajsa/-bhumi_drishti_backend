from sqlalchemy import text
from app.db.database import engine


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_connectivity():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1;")).scalar()
        assert result == 1


def test_get_segments_geojson_structure(client):
    response = client.get("/api/v1/segments")
    assert response.status_code == 200
    data = response.json()

    assert data.get("type") == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) > 0

    feature = data["features"][0]
    assert feature.get("type") == "Feature"
    assert "geometry" in feature
    assert feature["geometry"].get("type") == "LineString"

    props = feature.get("properties", {})
    assert "segment_id" in props
    assert "osm_way_id" in props
    assert "road_type" in props
    assert "length_m" in props
    assert "overall_blockage_risk" in props
    assert "risk_category" in props


def test_get_segments_filtered_by_risk_category(client):
    response = client.get("/api/v1/segments?risk_category=HIGH")
    assert response.status_code == 200
    data = response.json()

    assert data.get("type") == "FeatureCollection"
    for feature in data.get("features", []):
        assert feature["properties"]["risk_category"] == "HIGH"


def test_get_single_segment(client):
    response = client.get("/api/v1/segments/1")
    assert response.status_code == 200
    data = response.json()

    assert data.get("type") == "Feature"
    assert "geometry" in data
    assert data["properties"]["segment_id"] == 1


def test_get_segment_features_structure(client):
    response = client.get("/api/v1/segments/1/features")
    assert response.status_code == 200
    data = response.json()

    assert data["segment_id"] == 1
    assert "road" in data
    assert "terrain" in data
    assert "hydrology" in data
    assert "weather" in data
    assert "history" in data
    assert "infrastructure" in data
    assert "traffic" in data
    assert "field_reports" in data


def test_get_segment_risk(client):
    response = client.get("/api/v1/segments/1/risk")
    assert response.status_code == 200
    data = response.json()

    assert data["segment_id"] == 1
    assert "overall_blockage_risk" in data
    assert "risk_category" in data
    assert "hazards" in data


def test_field_report_submission_escalates_risk(client):
    report_payload = {
        "segment_id": 1,
        "report_type": "landslide",
        "reporter_name": "NER Disaster Response Patrol",
        "comment": "Active mudslide blocking left lane on GS road"
    }

    response = client.post("/api/v1/reports", json=report_payload)
    assert response.status_code == 200
    data = response.json()

    assert data["segment_id"] == 1
    assert data["report_type"] == "landslide"


def test_ml_risk_prediction(client):
    response = client.get("/api/v1/segments/1/ml-risk")
    assert response.status_code == 200
    data = response.json()

    assert data["segment_id"] == 1
    assert "ml_blockage_probability" in data
    assert 0.0 <= data["ml_blockage_probability"] <= 1.0
    assert data["ml_risk_category"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert "top_feature_importance" in data
    assert "model_name" in data
