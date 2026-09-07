from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from app.db.database import SessionLocal


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BATCH_SIZE = 5000


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    db = SessionLocal()

    try:

        total = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM road_segments
                """
            )
        ).scalar_one()

        print(
            f"Building hydrology features for "
            f"{total} road segments..."
        )

        last_id = 0
        processed = 0

        while True:

            max_id = last_id + BATCH_SIZE

            print(
                f"\nProcessing segments "
                f"{last_id + 1} → {max_id}"
            )

            # -------------------------------------------------
            # Nearest river + stream
            # -------------------------------------------------

            result = db.execute(
                text(
                    """
                    UPDATE segment_features AS sf

                    SET
                        distance_to_river_m =
                            COALESCE(
                                river.distance_m,
                                100000.0
                            ),

                        distance_to_stream_m =
                            COALESCE(
                                stream.distance_m,
                                100000.0
                            ),

                        within_flood_zone = FALSE

                    FROM road_segments AS rs

                    LEFT JOIN LATERAL (

                        SELECT
                            ST_Distance(
                                rs.geom::geography,
                                hf.geom::geography
                            ) AS distance_m

                        FROM hydrology_features AS hf

                        WHERE
                            hf.waterway = 'river'
                            AND hf.geom IS NOT NULL

                        ORDER BY
                            hf.geom <-> rs.geom

                        LIMIT 1

                    ) AS river ON TRUE

                    LEFT JOIN LATERAL (

                        SELECT
                            ST_Distance(
                                rs.geom::geography,
                                hf.geom::geography
                            ) AS distance_m

                        FROM hydrology_features AS hf

                        WHERE
                            hf.waterway = 'stream'
                            AND hf.geom IS NOT NULL

                        ORDER BY
                            hf.geom <-> rs.geom

                        LIMIT 1

                    ) AS stream ON TRUE

                    WHERE
                        sf.segment_id = rs.segment_id

                        AND rs.segment_id > :last_id

                        AND rs.segment_id <= :max_id
                    """
                ),
                {
                    "last_id": last_id,
                    "max_id": max_id,
                },
            )

            db.commit()

            processed += result.rowcount

            print(
                f"Updated: {result.rowcount}"
            )

            if max_id >= total:
                break

            last_id = max_id

        print()
        print(
            "Hydrology feature generation complete."
        )
        print(
            f"Total updated: {processed}"
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


if __name__ == "__main__":
    main()
