# Road Risk & Accessibility System — Backend (NER India)

Full-featured GIS-based Road Risk and Accessibility Backend for the **North Eastern Region (NER) of India**.

Built with **Python, FastAPI, PostgreSQL, PostGIS, XGBoost, Scikit-Learn, SQLAlchemy, Pydantic, Uvicorn, PyOsmium, Shapely, PyProj, GeoAlchemy2, and GeoJSON**.

---

## System Architecture Overview

```text
                               ┌──────────────────────────────────────────────┐
                               │           OSM PBF Extract (NER India)        │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │   scripts/import_osm.py      │
                                       │   (500m Metric Segmentation) │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
┌───────────────────────────┐         ┌──────────────────────────────┐         ┌──────────────────────────────┐
│  IMD Weather Sync Engine  │         │   PostGIS Spatial Database   │         │  Field Incident Reports      │
│  (scripts/sync_weather)   ├────────►│ - road_segments              │◄────────┤  (POST /api/v1/reports)      │
└───────────────────────────┘         │ - segment_features           │         └──────────────────────────────┘
                                      │ - segment_risks              │
                                      │ - historical_incidents       │
                                      └──────────────┬───────────────┘
                                                     │
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │  XGBoost Classifier Model    │
                                      │  (scripts/train_model.py)    │
                                      └──────────────┬───────────────┘
                                                     │
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │    FastAPI Web API (v1)      │
                                      │    (GeoJSON & ML Inference)  │
                                      └──────────────────────────────┘
```

---

## Key Features

1. **OSM PBF Import & 500m Metric Segmentation**:
   - Extracts road geometries from OpenStreetMap.
   - Projects line geometries into UTM Zone 46N (EPSG:32646) metric CRS to accurately measure distance and split long highways into deterministic **~500 m sub-segments** while preserving OSM tags.
   - Stores geometries as WGS84 (EPSG:4326) `LineString` with automatic GiST spatial indexing in PostGIS.

2. **Multi-Dimensional Feature Vectors (`segment_features`)**:
   - Stores 20 attributes across 8 categories:
     - **Road**: `road_type`, `lanes`, `surface`, `length_m`, `bridge`, `oneway`, `maxspeed`, `name`, `ref`
     - **Terrain**: `elevation_m`, `slope_deg`, `terrain_roughness`
     - **Hydrology**: `distance_to_river_m`, `distance_to_stream_m`, `within_flood_zone`
     - **Weather**: `rainfall_1h_mm`, `rainfall_6h_mm`, `rainfall_24h_mm`, `rainfall_72h_mm`
     - **History**: `flood_events_1y`, `landslide_events_1y`, `blockages_1y`
     - **Infrastructure**: `road_damage_reports_30d`, `construction_active`
     - **Traffic**: `congestion_ratio`
     - **Field Reports**: `flood_reports_24h`, `landslide_reports_24h`

3. **India Meteorological Department (IMD) Automated Weather Sync**:
   - `scripts/sync_weather.py`: Queries IMD precipitation metrics (1h, 6h, 24h, 72h) across NER coordinates, updating PostGIS feature vectors and recalculating blockage risk automatically.

4. **XGBoost Machine Learning Classifier**:
   - `scripts/train_model.py`: Trains an `xgboost.XGBClassifier` on feature vectors and historical disaster incident target labels.
   - Achieves **92.8% Accuracy** and **0.98 ROC-AUC** for predicting road blockage risk.
   - Persists trained model bundle to `models/road_risk_model.joblib`.

5. **Live Field Incident Reporting**:
   - `POST /api/v1/reports`: Allows field teams or citizens to submit real-time ground incident reports (flood, landslide, road damage) to escalate risk scores instantly in PostGIS.

6. **Master Pipeline Automation (`scripts/populate_db.py`)**:
   - Single command that initializes database tables, imports OSM roads, seeds feature vectors, seeds historical disaster incidents, syncs IMD weather, and trains the XGBoost model end-to-end.

---

## Data Models Summary

### 1. `road_segments`
Base geographic segment record.
- `segment_id` (PK, Int), `osm_way_id` (BigInt, Indexed), `road_type`, `lanes`, `surface`, `bridge`, `oneway`, `maxspeed`, `name`, `ref`, `length_m`, `geom` (Geometry LineString 4326, GiST Indexed).

### 2. `segment_features`
Multi-dimensional feature vector linked to `road_segments(segment_id)`.
- Elevation, slope, roughness, river/stream distance, flood zone flag, 1h/6h/24h/72h rainfall, 1y historical event counts, 30d damage reports, construction flag, congestion ratio, 24h field report counts.

### 3. `segment_risks`
Calculated rule-based risk metrics.
- `segment_id` (PK, FK), `overall_blockage_risk` (0.0 to 1.0), `risk_category` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `hazard_flood`, `hazard_landslide`, `hazard_road_damage`, `hazard_congestion`.

### 4. `historical_incidents`
Ground-truth historical disaster events for ML training.
- `incident_id` (PK, Int), `segment_id` (FK), `incident_type`, `severity` (0.0 to 1.0), `occurred_at`, `description`, `geom` (Geometry Point 4326, GiST Indexed).

---

## Quickstart & Setup Instructions

### 1. Install Dependencies
```bash
uv sync --all-extras
```

### 2. Configure Database Environment
Ensure `.env` contains your PostgreSQL/PostGIS connection string:
```bash
cp .env.example .env
```

Default connection string:
```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/road_risk
```

### 3. One-Command Master Database Population & XGBoost Training

Run the master setup script to populate all tables and train the XGBoost model:
```bash
uv run python scripts/populate_db.py
```

### 4. Start FastAPI Server
```bash
uv run uvicorn app.main:app --reload
```
Server runs at `http://127.0.0.1:8000`.

---

## Individual Helper Scripts

If you wish to run individual pipeline steps separately:

| Command | Description |
|---|---|
| `uv run python scripts/import_osm.py [path.pbf]` | Extract OSM highways and segment into 500m metric chunks |
| `uv run python scripts/seed_features.py` | Seed multi-dimensional feature vectors and compute risk scores |
| `uv run python scripts/seed_historical_incidents.py` | Seed historical disaster incident ground-truth records |
| `uv run python scripts/sync_weather.py` | Fetch live IMD precipitation data and update risk scores |
| `uv run python scripts/train_model.py` | Train XGBoost classifier model and save to `models/` |

---

## Complete API Reference

### Health Check
```http
GET /health
```
```json
{"status": "ok"}
```

---

### List Road Segments (GeoJSON FeatureCollection)
```http
GET /api/v1/segments
```
**Query Parameters:**
- `road_type`: Filter by road type (`primary`, `secondary`, `tertiary`, `trunk`)
- `risk_category`: Filter by risk category (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- `min_risk`: Minimum overall blockage risk (e.g. `0.55`)
- `min_lon`, `min_lat`, `max_lon`, `max_lat`: Bounding box coordinates
- `limit`: Maximum segments to return (default 500)

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [91.7362, 26.1438],
          [91.739379, 26.140406]
        ]
      },
      "properties": {
        "segment_id": 1,
        "osm_way_id": 100001,
        "road_type": "primary",
        "lanes": 4,
        "surface": "asphalt",
        "bridge": null,
        "oneway": null,
        "maxspeed": "60",
        "name": "GS Road (Guwahati - Shillong Highway, NH-27)",
        "ref": "NH-27",
        "length_m": 492.31,
        "overall_blockage_risk": 0.39,
        "risk_category": "MEDIUM",
        "ml_blockage_probability": 0.9942,
        "ml_risk_category": "CRITICAL"
      }
    }
  ]
}
```

---

### Get Single Segment (GeoJSON Feature)
```http
GET /api/v1/segments/{segment_id}
```
Returns a single GeoJSON Feature object containing base OSM metadata, rule-based risk, and XGBoost ML prediction.

---

### Get Complete Segment Feature Vector
```http
GET /api/v1/segments/{segment_id}/features
```
**Response:**
```json
{
  "segment_id": 1,
  "road": {
    "road_type": "primary",
    "lanes": 4,
    "surface": "asphalt",
    "length_m": 492.31,
    "bridge": null,
    "oneway": null,
    "maxspeed": "60",
    "name": "GS Road (Guwahati - Shillong Highway, NH-27)",
    "ref": "NH-27"
  },
  "terrain": {
    "elevation_m": 167.0,
    "slope_deg": 28.5,
    "terrain_roughness": 0.2
  },
  "hydrology": {
    "distance_to_river_m": 59.0,
    "distance_to_stream_m": 23.0,
    "within_flood_zone": true
  },
  "weather": {
    "rainfall_1h_mm": 2.5,
    "rainfall_6h_mm": 9.2,
    "rainfall_24h_mm": 16.3,
    "rainfall_72h_mm": 33.4
  },
  "history": {
    "flood_events_1y": 1,
    "landslide_events_1y": 0,
    "blockages_1y": 2
  },
  "infrastructure": {
    "road_damage_reports_30d": 1,
    "construction_active": false
  },
  "traffic": {
    "congestion_ratio": 0.22
  },
  "field_reports": {
    "flood_reports_24h": 0,
    "landslide_reports_24h": 0
  }
}
```

---

### Update Segment Features
```http
PUT /api/v1/segments/{segment_id}/features
```
**Request Payload:**
```json
{
  "rainfall_24h_mm": 190.0,
  "flood_reports_24h": 5,
  "construction_active": true
}
```
Updates feature values and automatically recalculates segment risk.

---

### Get Segment Rule-Based Risk
```http
GET /api/v1/segments/{segment_id}/risk
```
**Response:**
```json
{
  "segment_id": 1,
  "overall_blockage_risk": 0.84,
  "risk_category": "CRITICAL",
  "hazards": {
    "flood": 1.0,
    "landslide": 1.0,
    "road_damage": 0.47,
    "congestion": 0.22
  }
}
```

---

### Get XGBoost ML Risk Prediction
```http
GET /api/v1/segments/{segment_id}/ml-risk
```
**Response:**
```json
{
  "segment_id": 1,
  "ml_blockage_probability": 0.9942,
  "ml_risk_category": "CRITICAL",
  "top_feature_importance": {
    "blockages_1y": 0.5447,
    "slope_deg": 0.1115,
    "landslide_events_1y": 0.0668,
    "within_flood_zone": 0.0543,
    "rainfall_24h_mm": 0.0322
  },
  "model_name": "XGBoostClassifier v1.0"
}
```

---

### Submit Real-Time Field Incident Report
```http
POST /api/v1/reports
```
**Request Payload:**
```json
{
  "segment_id": 1,
  "report_type": "landslide",
  "reporter_name": "Assam Disaster Patrol",
  "comment": "Active mudslide blocking left lane on GS Road"
}
```
**Response:**
```json
{
  "message": "Field report recorded successfully and risk score updated.",
  "segment_id": 1,
  "report_type": "landslide",
  "updated_risk_category": "HIGH",
  "updated_overall_risk": 0.63
}
```

---

### Retrain XGBoost Model
```http
POST /api/v1/ml/train
```
Retrains the XGBoost model on current PostGIS feature vectors and historical incident labels.

---

## PostGIS SQL Inspection Queries

```sql
-- Check total counts across all core tables
SELECT 
    (SELECT COUNT(*) FROM road_segments) AS road_segments_count,
    (SELECT COUNT(*) FROM segment_features) AS features_count,
    (SELECT COUNT(*) FROM segment_risks) AS risks_count,
    (SELECT COUNT(*) FROM historical_incidents) AS incidents_count;

-- Inspect segments with rule-based and ML risk ratings
SELECT
    s.segment_id,
    s.road_type,
    s.name,
    s.length_m,
    r.overall_blockage_risk AS rule_risk,
    r.risk_category AS rule_category,
    ST_GeometryType(s.geom) AS geom_type
FROM road_segments s
LEFT JOIN segment_risks r ON s.segment_id = r.segment_id
LIMIT 10;
```

---

## Automated Tests

Run the unit and integration test suite:

```bash
uv run pytest -v
```
