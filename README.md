# Road Risk & Accessibility System — Backend Prototype (NER India)

Prototype backend for a GIS-based road risk and accessibility system focused on the **North Eastern Region (NER) of India**.

Built with **Python, FastAPI, PostgreSQL, PostGIS, SQLAlchemy, Pydantic, Uvicorn, PyOsmium, Shapely, PyProj, GeoAlchemy2, and GeoJSON**.

---

## Prototype Features

1. **OSM PBF Data Importer**: Reads OpenStreetMap extracts and filters road-related highway ways.
2. **PostGIS Spatial Storage**: Stores geometries as `LineString` in WGS84 (EPSG:4326) with a GiST spatial index.
3. **Road Segmentation**: Splitting long OSM road ways into ~500 m segments in metric projection (UTM 46N / EPSG:32646) while retaining original OSM way ID and tags.
4. **FastAPI GeoJSON API**: Exposes road segments formatted as standard GeoJSON `FeatureCollection` and single `Feature` endpoints.

---

## Core Data Model (`road_segments`)

| Field | Type | Description |
|---|---|---|
| `segment_id` | `INTEGER` (PK) | Internal primary key |
| `osm_way_id` | `BIGINT` | Original OpenStreetMap way ID |
| `road_type` | `VARCHAR` | Mapped from OSM `highway` tag |
| `lanes` | `INTEGER` | Number of lanes |
| `surface` | `VARCHAR` | Surface material (asphalt, concrete, etc.) |
| `bridge` | `BOOLEAN` | Whether segment is a bridge |
| `oneway` | `BOOLEAN` | Whether road is one-way |
| `maxspeed` | `VARCHAR` | Speed limit tag |
| `name` | `VARCHAR` | Road name |
| `ref` | `VARCHAR` | Highway reference (e.g. NH-27, AH-1) |
| `length_m` | `FLOAT` | Segment length in meters |
| `created_at` | `TIMESTAMP` | Record creation timestamp |
| `geom` | `GEOMETRY(LineString, 4326)` | Spatial LineString geometry with GiST index |

---

## Quickstart & Setup Instructions

### 1. Requirements

- Python 3.10+
- `uv` (Fast Python package installer)
- PostgreSQL with PostGIS extension enabled

### 2. Install Dependencies

```bash
uv sync --all-extras
```

Or using `uv pip`:

```bash
uv pip install -e .[dev]
```

### 3. Database Configuration

Set up environment variables (or rely on defaults in `.env`):

```bash
cp .env.example .env
```

Ensure PostGIS is enabled on your PostgreSQL database:

```sql
CREATE DATABASE road_risk;
\c road_risk;
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 4. Import OSM Road Data & Run Segmentation

Run the importer script to process an OSM PBF extract. If no file path is specified, a sample extract for NER India roads will be created and imported:

```bash
# Import default sample NER India roads
uv run python scripts/import_osm.py

# Or import your own custom OSM PBF file
uv run python scripts/import_osm.py /path/to/northeast-latest.osm.pbf
```

### 5. Start the FastAPI Server

```bash
uv run uvicorn app.main:app --reload
```

Server will run at `http://127.0.0.1:8000`.

---

## API Documentation & Examples

### Health Check

```http
GET /health
```

**Request:**
```bash
curl http://127.0.0.1:8000/health
```

**Response:**
```json
{
  "status": "ok"
}
```

---

### Get Road Segments (GeoJSON FeatureCollection)

```http
GET /api/v1/segments
```

**Optional Query Filters:**
- `road_type`: Filter by road type (e.g. `primary`, `secondary`, `tertiary`, `trunk`)
- `min_lon`, `min_lat`, `max_lon`, `max_lat`: Bounding box geographic filter
- `limit`: Maximum features to return (default 500)

**Example Requests:**
```bash
# Get all segments
curl "http://127.0.0.1:8000/api/v1/segments?limit=10"

# Filter by primary roads
curl "http://127.0.0.1:8000/api/v1/segments?road_type=primary"

# Filter by bounding box
curl "http://127.0.0.1:8000/api/v1/segments?min_lon=91.70&min_lat=26.00&max_lon=91.90&max_lat=26.20"
```

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
        "bridge": false,
        "oneway": false,
        "maxspeed": "60",
        "name": "GS Road (Guwahati - Shillong Highway, NH-27)",
        "ref": "NH-27",
        "length_m": 492.31
      }
    }
  ]
}
```

---

### Get Single Road Segment

```http
GET /api/v1/segments/{segment_id}
```

**Request:**
```bash
curl http://127.0.0.1:8000/api/v1/segments/1
```

**Response:**
```json
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
    "bridge": false,
    "oneway": false,
    "maxspeed": "60",
    "name": "GS Road (Guwahati - Shillong Highway, NH-27)",
    "ref": "NH-27",
    "length_m": 492.31
  }
}
```

---

## Database Inspection Queries

Use `psql` to inspect stored road segments:

```sql
-- Total segment count
SELECT COUNT(*) FROM road_segments;

-- Inspect segments with OSM metadata & lengths
SELECT
    segment_id,
    osm_way_id,
    road_type,
    name,
    ref,
    length_m,
    ST_GeometryType(geom) AS geom_type
FROM road_segments
ORDER BY segment_id ASC
LIMIT 10;

-- Segment summary by road type
SELECT
    road_type,
    COUNT(*) AS total_segments,
    ROUND(SUM(length_m)::numeric / 1000.0, 2) AS total_km
FROM road_segments
GROUP BY road_type
ORDER BY total_km DESC;
```

---

## Running Automated Tests

```bash
uv run pytest -v
```
