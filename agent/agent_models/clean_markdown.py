"""
cleanup_markdown.py
---------------------
One-time script to strip Markdown artifacts (**, *, #, backticks)
from existing 'description' fields in the activities collection.

Run once:
    python cleanup_markdown.py

Safe to re-run — already-clean text is unaffected.
"""

import os
import re
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("DB_NAME", "nss_portal")

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]


def strip_markdown(text: str) -> str:
    if not text:
        return text

    cleaned = text
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[\*\-]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def main():
    activities = list(db.activities.find({}))
    updated_count = 0

    for activity in activities:
        original = activity.get("description", "")
        cleaned  = strip_markdown(original)

        if cleaned != original:
            db.activities.update_one(
                {"_id": activity["_id"]},
                {"$set": {"description": cleaned}}
            )
            updated_count += 1
            print(f"Cleaned: {activity.get('title', 'Untitled')}")

    print(f"\nDone. {updated_count} activity description(s) cleaned out of {len(activities)} total.")
    client.close()


if __name__ == "__main__":
    main()