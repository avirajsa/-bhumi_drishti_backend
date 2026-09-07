#!/usr/bin/env bash

set -euo pipefail

BUCKET="s3://copernicus-dem-30m"
OUTPUT_DIR="data/terrain/COP30_NER"
TILE_LIST="/tmp/copernicus_tiles.txt"
NER_TILES="/tmp/ner_tiles.txt"

mkdir -p "$OUTPUT_DIR"

# ================================================================
# 1. Download official tile list
# ================================================================

echo "Downloading Copernicus GLO-30 tile list..."

aws s3 cp \
    --no-sign-request \
    "$BUCKET/tileList.txt" \
    "$TILE_LIST"


# ================================================================
# 2. Find tiles covering NER
#
# Latitude:
#     20 <= lat < 30
#
# Longitude:
#     87 <= lon < 98
#
# Tile naming:
#
#     Copernicus_DSM_COG_10_N20_00_E087_00_DEM
#
# ================================================================

echo "Selecting NER tiles..."

python - "$TILE_LIST" "$NER_TILES" <<'PY'
import re
import sys

input_file = sys.argv[1]
output_file = sys.argv[2]

pattern = re.compile(
    r"^Copernicus_DSM_COG_10_"
    r"([NS])(\d{2})_00_"
    r"([EW])(\d{3})_00_DEM$"
)

selected = []

with open(input_file) as f:
    for line in f:
        tile = line.strip()

        match = pattern.match(tile)

        if not match:
            continue

        lat_direction, lat_value, lon_direction, lon_value = match.groups()

        lat = int(lat_value)
        lon = int(lon_value)

        if lat_direction == "S":
            lat = -lat

        if lon_direction == "W":
            lon = -lon

        # NER bounding box
        if (
            20 <= lat < 30
            and 87 <= lon < 98
        ):
            selected.append(tile)

selected.sort()

with open(output_file, "w") as f:
    for tile in selected:
        f.write(tile + "\n")

print(f"Selected {len(selected)} tiles.")
PY


# ================================================================
# 3. Show selected tiles
# ================================================================

echo
echo "================================================"
echo "NER tiles"
echo "================================================"

cat "$NER_TILES"

TILE_COUNT=$(wc -l < "$NER_TILES")

echo
echo "================================================"
echo "Tiles to download: $TILE_COUNT"
echo "================================================"
echo


# ================================================================
# 4. Download tiles
#
# Actual S3 structure:
#
#   bucket/
#       TILE_NAME/
#           TILE_NAME.tif
#
# ================================================================

while IFS= read -r tile; do

    [[ -z "$tile" ]] && continue

    filename="${tile}.tif"

    remote_path="$BUCKET/$tile/$filename"
    local_path="$OUTPUT_DIR/$filename"

    if [[ -f "$local_path" ]]; then
        echo "[SKIP] $filename"
        continue
    fi

    echo
    echo "[DOWNLOAD] $filename"

    aws s3 cp \
        --no-sign-request \
        "$remote_path" \
        "$local_path"

done < "$NER_TILES"


# ================================================================
# 5. Final summary
# ================================================================

echo
echo "================================================"
echo "Download complete"
echo "================================================"

TILES_PRESENT=$(find "$OUTPUT_DIR" -type f -name "*.tif" | wc -l)

echo "DEM tiles present: $TILES_PRESENT"
echo
echo "Disk usage:"
du -sh "$OUTPUT_DIR"

echo
echo "Location:"
echo "$OUTPUT_DIR"

