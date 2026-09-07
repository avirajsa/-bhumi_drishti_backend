import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

GPKG_PATH = PROJECT_ROOT / "data/hydrology/waterways.gpkg"

DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise RuntimeError("DATABASE_URL is not set")


# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------

url = make_url(DB_URL)

gdal_db = (
    f"PG:"
    f"dbname='{url.database}' "
    f"host='{url.host}' "
    f"port='{url.port or 5432}' "
    f"user='{url.username}' "
    f"password='{url.password}'"
)


# ---------------------------------------------------------
# HYDROLOGY QUERY
# ---------------------------------------------------------

SQL = """
SELECT
    fid,
    id,
    name,
    name_en,
    waterway,
    natural_class,
    water,

    CASE
        WHEN waterway = 'river'
            THEN 'RIVER'

        WHEN waterway = 'stream'
            THEN 'STREAM'

        WHEN natural_class IN ('water', 'wetland')
            OR water IN (
                'pond',
                'reservoir',
                'lake',
                'basin',
                'river',
                'canal',
                'oxbow',
                'lagoon',
                'waterbody'
            )
            THEN 'WATER_BODY'

        ELSE NULL
    END AS feature_type,

    geom

FROM waterways

WHERE
    waterway IN ('river', 'stream')
    OR natural_class IN ('water', 'wetland')
    OR water IN (
        'pond',
        'reservoir',
        'lake',
        'basin',
        'river',
        'canal',
        'oxbow',
        'lagoon',
        'waterbody'
    )
"""


# ---------------------------------------------------------
# INGEST
# ---------------------------------------------------------

def main():
    if not GPKG_PATH.exists():
        raise FileNotFoundError(
            f"Hydrology dataset not found: {GPKG_PATH}"
        )

    print("[INFO] Ingesting NER hydrology data...")
    print(f"[INFO] Source: {GPKG_PATH}")
    print("[INFO] Destination: hydrology_features")

    command = [
        "ogr2ogr",

        "-f",
        "PostgreSQL",

        gdal_db,

        str(GPKG_PATH),

        "-dialect",
        "SQLite",

        "-sql",
        SQL,

        # NER bounding box
        "-spat",
        "87",
        "20",
        "98",
        "30",

        # Destination
        "-nln",
        "hydrology_features",

        # Source contains mixed geometry types.
        # Keep the destination geometry generic.
        "-nlt",
        "GEOMETRY",

        "-lco",
        "GEOMETRY_NAME=geom",

        "-lco",
        "FID=hydro_id",

        # Prototype: rebuild table if it already exists.
        "-overwrite",

        "-progress",
    ]

    subprocess.run(command, check=True)

    print("[SUCCESS] Hydrology data ingested.")


if __name__ == "__main__":
    main()
