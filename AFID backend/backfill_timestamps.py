"""
backfill_timestamps.py
Populate start_time and end_time for existing completed procedures where they are NULL.
Run with: python backfill_timestamps.py
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from database import SessionLocal
import models


def backfill():
    db = SessionLocal()
    try:
        # Find completed procedures missing start_time or end_time
        procedures = (
            db.query(models.Procedure)
            .filter(
                models.Procedure.is_completed == True,
            )
            .all()
        )

        updated = 0
        for p in procedures:
            changed = False

            # Backfill start_time from session_date if missing
            if not getattr(p, 'start_time', None) and getattr(p, 'session_date', None):
                p.start_time = p.session_date
                changed = True

            # Backfill end_time from start_time + duration if missing
            if not getattr(p, 'end_time', None) and getattr(p, 'start_time', None):
                duration = getattr(p, 'duration_minutes', None)
                if duration is not None:
                    p.end_time = p.start_time + timedelta(minutes=duration)
                else:
                    p.end_time = p.start_time + timedelta(minutes=30)  # default fallback
                changed = True

            if changed:
                updated += 1

        db.commit()
        print(f"Backfilled timestamps for {updated} completed procedures.")
    except Exception as e:
        print(f"Error during backfill: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    backfill()