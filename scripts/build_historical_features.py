from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import (
    RoadSegment,
    SegmentFeature,
    HistoricalIncident,
)


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

LOOKBACK_DAYS = 365
BATCH_SIZE = 100


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=LOOKBACK_DAYS)

        segments = db.query(RoadSegment).all()

        print(f"Processing {len(segments)} road segments...")
        print(f"Incident window: {cutoff} → {now}")

        processed = 0

        for segment in segments:

            # -------------------------------------------------
            # Historical incidents for this segment
            # -------------------------------------------------

            incidents = (
                db.query(HistoricalIncident)
                .filter(
                    HistoricalIncident.segment_id == segment.segment_id
                )
                .all()
            )

            flood_events = 0
            landslide_events = 0
            blockage_events = 0

            for incident in incidents:

                # Determine event date
                event_date = incident.occurred_at

                if event_date is None and incident.event_year:
                    # We only know the year, so don't pretend
                    # we know the exact date.
                    #
                    # For this prototype, count year-level
                    # incidents if they belong to the current
                    # lookback year.
                    if incident.event_year == now.year:
                        event_date = now
                    else:
                        continue

                if event_date is not None:

                    # Make naive datetimes comparable
                    if event_date.tzinfo is not None:
                        event_date = event_date.replace(tzinfo=None)

                    cutoff_naive = cutoff.replace(tzinfo=None)
                    now_naive = now.replace(tzinfo=None)

                    if not (
                        cutoff_naive <= event_date <= now_naive
                    ):
                        continue

                incident_type = incident.incident_type.upper()

                if incident_type == "FLOOD":
                    flood_events += 1

                elif incident_type == "LANDSLIDE":
                    landslide_events += 1

                elif incident_type == "BLOCKAGE":
                    blockage_events += 1

            # -------------------------------------------------
            # Create or update SegmentFeature
            # -------------------------------------------------

            features = (
                db.query(SegmentFeature)
                .filter(
                    SegmentFeature.segment_id == segment.segment_id
                )
                .first()
            )

            if features is None:
                features = SegmentFeature(
                    segment_id=segment.segment_id
                )
                db.add(features)

            features.flood_events_1y = flood_events
            features.landslide_events_1y = landslide_events
            features.blockages_1y = blockage_events

            processed += 1

            if processed % BATCH_SIZE == 0:
                db.commit()
                print(
                    f"Processed {processed}/{len(segments)}"
                )

        db.commit()

        print()
        print("Historical feature generation complete.")
        print(f"Segments processed: {processed}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
