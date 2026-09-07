from sqlalchemy import text

from app.db.database import SessionLocal


def main():
    db = SessionLocal()

    try:
        print("[INFO] Building weather features...")

        query = text("""
            UPDATE segment_features sf
            SET
                rainfall_1h_mm = COALESCE(w.rainfall_mm, 0.0)
            FROM (
                SELECT
                    rs.segment_id,
                    wo.rainfall_mm
                FROM road_segments rs
                CROSS JOIN LATERAL (
                    SELECT
                        rainfall_mm
                    FROM weather_observations wo
                    ORDER BY
                        wo.geom <-> rs.geom
                    LIMIT 1
                ) wo
            ) w
            WHERE sf.segment_id = w.segment_id;
        """)

        result = db.execute(query)

        db.commit()

        print("=" * 60)
        print("WEATHER FEATURES COMPLETE")
        print("=" * 60)
        print(f"Segments updated: {result.rowcount}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
