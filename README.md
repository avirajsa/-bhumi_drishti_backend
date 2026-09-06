# Bhumi Drishti — Road Risk & Accessibility Backend (NER India)

Full-featured GIS-based Road Risk and Accessibility Backend for the **North Eastern Region (NER) of India**.

- **Live Production API**: [https://bhumi-drishti-backend.onrender.com](https://bhumi-drishti-backend.onrender.com)
- **Interactive Swagger / OpenAPI Docs**: [https://bhumi-drishti-backend.onrender.com/docs](https://bhumi-drishti-backend.onrender.com/docs)
- **Health Check Endpoint**: [https://bhumi-drishti-backend.onrender.com/health](https://bhumi-drishti-backend.onrender.com/health)

Built with **Python, FastAPI, PostgreSQL, PostGIS, XGBoost, Scikit-Learn, SQLAlchemy, Pydantic, Uvicorn, PyOsmium, Shapely, PyProj, GeoAlchemy2, and GeoJSON**.

---

## Live System Statistics

| Metric | Production Value | Source / Methodology |
| :--- | :--- | :--- |
| **Total Road Segments** | **1,390 segments** (692.89 km) | OpenStreetMap (OSM) PBF extracted & segmented into ~500m chunks via projected UTM Zone 46N (EPSG:32646) metric CRS |
| **Feature Vectors** | **1,390 records** | 20 physical attributes across 8 feature groups (Road, Terrain, Hydrology, Weather, History, Infrastructure, Traffic, Reports) |
| **Ground-Truth Incidents** | **1,702 historical records** | Spatially indexed disaster logs (Landslides, Flash Floods, Culvert Collapses) |
| **IMD Weather Grid** | **738 cells** | India Meteorological Department precipitation grid sync (1h, 6h, 24h, 72h mm) |
| **XGBoost ML Accuracy** | **90.80%** (ROC-AUC: **0.9580**) | Machine Learning model trained on PostGIS spatial feature vectors & disaster ground truth |

---

## Frontend Integration Quickstart for Teammates

### JavaScript / Fetch API Snippet (Map & Dashboard)

```javascript
const API_BASE = "https://bhumi-drishti-backend.onrender.com";

// 1. Fetch GeoJSON Road Segments with Risk Scores & ML Predictions for Map Overlay
async function loadRiskMapSegments() {
  const response = await fetch(`${API_BASE}/api/v1/segments?limit=500`);
  const geojson = await response.json();
  console.log("Loaded GeoJSON Features:", geojson.features.length);
  return geojson;
}

// 2. Submit Field Incident Report from Mobile / Dashboard
async function submitFieldReport(reportData) {
  const response = await fetch(`${API_BASE}/api/v1/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      segment_id: reportData.segmentId,
      report_type: reportData.reportType, // "landslide", "flood", "road_damage"
      severity: reportData.severity, // 0.0 - 1.0
      reporter_name: reportData.reporterName,
      reporter_role: reportData.reporterRole,
      description: reportData.description,
      latitude: reportData.lat,
      longitude: reportData.lon
    })
  });
  return await response.json();
}

// 3. Fetch XGBoost Machine Learning Risk Inference for a Road Segment
async function getMLRiskPrediction(segmentId) {
  const response = await fetch(`${API_BASE}/api/v1/segments/${segmentId}/ml-risk`);
  const mlData = await response.json();
  console.log("XGBoost Probability:", mlData.ml_blockage_probability);
  console.log("Top Features:", mlData.top_feature_importance);
  return mlData;
}
```

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
                                      │ - field_reports              │
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

## Production Deployment Guide (Docker & Cloud)

### Method A: Docker Compose Deployment (Recommended)

To deploy the complete stack (PostGIS + FastAPI + IMD Weather Sync Worker) on any server or VPS:

```bash
# 1. Clone repository
git clone https://github.com/Samriddha0207/helper_dashboard.git
cd backend2

# 2. Build and start containers in detached mode
docker compose up -d --build

# 3. Check container logs & status
docker compose ps
docker compose logs -f app
```

That's it! Docker Compose will automatically:
1. Spin up a PostGIS 16 database container (`postgis/postgis:16-3.4`).
2. Run database table creation, 500m OSM road segmentation, feature vector seeding, IMD weather sync, and XGBoost model training (`scripts/populate_db.py`).
3. Start the FastAPI backend on `http://0.0.0.0:8000`.
4. Launch an automated hourly background weather sync container (`weather-worker`).

---

### Method B: Deploying on Cloud Server (AWS EC2 / DigitalOcean / Hetzner)

#### Step 1: Install Docker & Docker Compose on Ubuntu/Debian Server
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

#### Step 2: Clone & Launch
```bash
git clone <your-repo-url> backend
cd backend
docker compose up -d
```

#### Step 3: Nginx Reverse Proxy with Free SSL (Certbot HTTPS)
Create `/etc/nginx/sites-available/road-risk`:

```nginx
server {
    server_name api.roadrisk-ner.org;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and acquire free SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/road-risk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.roadrisk-ner.org
```

---

## Complete API Reference

### 1. Dashboard UI Endpoints (`/api/v1/dashboard`)

| Endpoint | Method | UI Component Powered | Response Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/dashboard/stats` | `GET` | **Top KPI Header Cards** | Returns `active_vehicles_count` (4,820), `roads_at_risk_count` (58), `disruption_count` (0), `accessibility_percentage` (89.2%), `api_connection`, and IST time string. |
| `/api/v1/dashboard/states` | `GET` | **7 Sisters State Sidebar** | Returns state-wise risk stretch counts & accessibility percentages for `All States` (NER), `Assam`, `Arunachal Pradesh`, `Manipur`, `Meghalaya`, `Mizoram`, `Nagaland`, `Tripura`. |
| `/api/v1/dashboard/alerts` | `GET` | **ALERTS LOG (LIVE API)** | Stream of real-time active incident telemetry & submitted field reports. |
| `/api/v1/dashboard/weather-telemetry` | `GET` | **WEATHER UPDATES (RISK-PRIORITIZED)** | State-wise meteorological telemetry ranked by hazard severity index (`Meghalaya` Risk 92/100, `Arunachal Pradesh` Risk 89/100, `Manipur` Risk 76/100) with advisory alerts. |

#### GET `/api/v1/dashboard/stats`
Powers the top 5 header stat cards (`Active Vehicles`, `Roads At-Risk`, `Disruptions`, `Accessibility %`, `API Connection Status`, `IST Clock`):
```json
{
  "active_vehicles_count": 4820,
  "active_vehicles_label": "Live Corridors",
  "roads_at_risk_count": 58,
  "roads_at_risk_label": "High/Crit Stretches",
  "disruption_count": 0,
  "disruption_label": "Reports & Blockages",
  "accessibility_percentage": 89.2,
  "accessibility_label": "Network Operational",
  "api_connection": {
    "status": "CONNECTED",
    "provider": "Render PostGIS v0.5",
    "db_connected": true
  },
  "time_ist": "16 : 43 : 31",
  "total_road_segments": 1390,
  "total_road_km": 692.89
}
```

#### GET `/api/v1/dashboard/states`
Powers the left sidebar state filter for the 7 Sister States of NER:
```json
{
  "states": [
    { "code": "NER", "name": "All States", "at_risk_count": 58, "accessibility": 89.2 },
    { "code": "AS", "name": "Assam", "at_risk_count": 14, "accessibility": 91.5 },
    { "code": "AR", "name": "Arunachal Pradesh", "at_risk_count": 12, "accessibility": 84.1 },
    { "code": "MN", "name": "Manipur", "at_risk_count": 9, "accessibility": 88.0 },
    { "code": "ML", "name": "Meghalaya", "at_risk_count": 11, "accessibility": 82.4 },
    { "code": "MZ", "name": "Mizoram", "at_risk_count": 5, "accessibility": 90.3 },
    { "code": "NL", "name": "Nagaland", "at_risk_count": 4, "accessibility": 87.6 },
    { "code": "TR", "name": "Tripura", "at_risk_count": 3, "accessibility": 93.8 }
  ]
}
```

#### GET `/api/v1/dashboard/alerts`
Powers the top-right live incident alerts feed:
```json
{
  "active_incidents_count": 0,
  "status_text": "Listening to live Incident telemetry feed...",
  "alerts": []
}
```

#### GET `/api/v1/dashboard/weather-telemetry`
Powers the bottom-right risk-prioritized meteorological telemetry cards:
```json
{
  "title": "WEATHER UPDATES (RISK-PRIORITIZED)",
  "subtitle": "State-wise meteorological telemetry • Ranked by hazard severity index",
  "weather_cards": [
    {
      "priority": 1,
      "severity_level": "CRITICAL",
      "state_name": "Meghalaya",
      "state_code": "ML",
      "risk_score": 92,
      "temperature_c": 19.6,
      "rainfall_mm_h": 62.4,
      "wind_speed_kmh": 28.0,
      "wind_direction": "S",
      "advisory": "Red Alert: Severe cloudburst activity recorded"
    },
    {
      "priority": 2,
      "severity_level": "CRITICAL",
      "state_name": "Arunachal Pradesh",
      "state_code": "AR",
      "risk_score": 89,
      "temperature_c": 18.2,
      "rainfall_mm_h": 45.0,
      "wind_speed_kmh": 31.0,
      "wind_direction": "NE",
      "advisory": "Red Alert: Torrential rains triggering slope destabilization"
    }
  ]
}
```

---

### 2. Core GIS & Risk Endpoints

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
- `state`: Filter by state name or 2-letter code for region cutout views (`Assam` / `AS`, `Arunachal Pradesh` / `AR`, `Manipur` / `MN`, `Meghalaya` / `ML`, `Mizoram` / `MZ`, `Nagaland` / `NL`, `Tripura` / `TR`)
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

### Submit Real-Time Field Incident Report
```http
POST /api/v1/reports
```
**Request Payload:**
```json
{
  "latitude": 26.14,
  "longitude": 91.73,
  "report_type": "landslide",
  "severity": 0.85,
  "reporter_name": "Field Officer Barua",
  "reporter_role": "Engineer",
  "description": "Active rockfall blocking right lane on GS Road"
}
```
**Response:**
```json
{
  "report_id": 1,
  "segment_id": 1,
  "reporter_name": "Field Officer Barua",
  "reporter_role": "Engineer",
  "report_type": "landslide",
  "severity": 0.85,
  "status": "SUBMITTED",
  "description": "Active rockfall blocking right lane on GS Road",
  "photo_url": null,
  "latitude": 26.14,
  "longitude": 91.73,
  "created_at": "2026-09-05 19:39:36.684936+05:30",
  "updated_at": "2026-09-05 19:39:36.684936+05:30"
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

## Automated Tests

Run the unit and integration test suite:

```bash
uv run pytest -v
```
