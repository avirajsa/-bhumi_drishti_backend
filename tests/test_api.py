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
    assert isinstance(data["features"], list)
    assert len(data["features"]) > 0

    feature = data["features"][0]
    assert feature.get("type") == "Feature"
    assert "geometry" in feature
    assert feature["geometry"].get("type") == "LineString"
    assert "coordinates" in feature["geometry"]

    props = feature.get("properties", {})
    assert "segment_id" in props
    assert "osm_way_id" in props
    assert "road_type" in props
    assert "length_m" in props


def test_get_segments_filtered_by_road_type(client):
    response = client.get("/api/v1/segments?road_type=primary")
    assert response.status_code == 200
    data = response.json()

    assert data.get("type") == "FeatureCollection"
    for feature in data.get("features", []):
        assert feature["properties"]["road_type"] == "primary"


def test_get_single_segment(client):
    response = client.get("/api/v1/segments/1")
    assert response.status_code == 200
    data = response.json()

    assert data.get("type") == "Feature"
    assert "geometry" in data
    assert data["geometry"].get("type") == "LineString"
    assert data["properties"]["segment_id"] == 1
    assert "length_m" in data["properties"]


def test_get_single_segment_not_found(client):
    response = client.get("/api/v1/segments/999999")
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()
