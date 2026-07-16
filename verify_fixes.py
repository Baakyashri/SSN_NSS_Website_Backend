import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.tools.generic_tools import _case_insensitive_exact
from agent.tools.report_tools import request_report

print("Testing substring regex helper...")
match_regex = _case_insensitive_exact("Meditation")
print("Regex generated:", match_regex)
import re
pattern = match_regex["$regex"]
is_match = bool(re.search(pattern, "online meditation", re.IGNORECASE))
print(f"Matches 'online meditation'? {is_match} (Expected: True)")

print("\nTesting request_report mock trigger...")
from db import db

try:
    res = request_report.invoke(
        dict(
            scope="annual",
            year=2026,
            role="admin",
            user_id="test_user",
            user_email="test@nss-portal.internal"
        )
    )
    print("request_report output:", res)
    if res.get("status") == "queued":
        job_id = res.get("job_id")
        from bson import ObjectId
        db.agent_report_jobs.delete_one({"_id": ObjectId(job_id)})
        print("Cleaned up queued test job successfully.")
except Exception as e:
    print("request_report CRASHED:", e)
