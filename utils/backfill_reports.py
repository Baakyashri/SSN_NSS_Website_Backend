import os
import sys
import logging
from dotenv import load_dotenv
load_dotenv() 
# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db
from utils.ingestion import ingest_report, extract_activity_metadata

# Setup logging to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("backfill")

def run_backfill():
    logger.info("Starting historical report backfill...")

    # Find all activities with at least one report
    query = {
        "reports": {
            "$exists": True,
            "$type": "array",
            "$not": {"$size": 0}
        }
    }
    activities = list(db.activities.find(query))
    logger.info(f"Found {len(activities)} activities with reports to backfill.")

    success_count = 0
    fail_count = 0
    total_reports_processed = 0

    for activity in activities:
        activity_id = str(activity["_id"])
        activity_title = activity.get("title", "Untitled Activity")
        reports = activity.get("reports", [])

        logger.info(f"Processing activity '{activity_title}' ({activity_id}) with {len(reports)} report(s)")
        metadata = extract_activity_metadata(activity)

        for report in reports:
            url = report.get("url")
            if not url:
                logger.warning("Report missing URL field. Skipping.")
                fail_count += 1
                continue

            total_reports_processed += 1
            success = ingest_report(activity_id, report, metadata)
            if success:
                success_count += 1
            else:
                fail_count += 1

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETED SUMMARY:")
    logger.info(f"  Activities found: {len(activities)}")
    logger.info(f"  Total reports found: {total_reports_processed}")
    logger.info(f"  Successfully ingested: {success_count}")
    logger.info(f"  Failed: {fail_count}")
    logger.info("=" * 60)

if __name__ == "__main__":
    run_backfill()
