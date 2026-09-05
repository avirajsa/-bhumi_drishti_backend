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


def test_field_report_crud_and_status_workflow(client):
    # 1. Create a field report with GPS coordinates
    report_payload = {
        "segment_id": 1,
        "report_type": "landslide",
        "severity": 0.85,
        "reporter_name": "Patrol Officer Sharma",
        "reporter_role": "Patrol Officer",
        "description": "Active rockfall blocking right lane on GS Road",
        "latitude": 26.14,
        "longitude": 91.73
    }

    create_resp = client.post("/api/v1/reports", json=report_payload)
    assert create_resp.status_code == 200
    report_data = create_resp.json()
    
    assert report_data["segment_id"] == 1
    assert report_data["report_type"] == "landslide"
    assert report_data["status"] == "SUBMITTED"
    report_id = report_data["report_id"]

    # 2. List dashboard field reports
    list_resp = client.get("/api/v1/reports?status=SUBMITTED")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total_count"] > 0
    assert any(r["report_id"] == report_id for r in list_data["reports"])

    # 3. Update report status to VERIFIED
    patch_resp = client.patch(f"/api/v1/reports/{report_id}/status", json={"status": "VERIFIED"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "VERIFIED"


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
