"""
agent_schema.py
---------------
Run this file ONCE to create all agent-owned collections in MongoDB.
These collections are exclusively managed by the agent.
The admin dashboard never reads or writes to these collections.

Usage:
    python agent_schema.py

Safe to re-run — skips collections that already exist.
"""

import logging
from datetime import datetime
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("DB_NAME", "nss_portal")

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]


# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────

def safe_create(name: str):
    """Create collection only if it does not already exist."""
    try:
        db.create_collection(name)
        logger.info(f"  Created  → {name}")
    except CollectionInvalid:
        logger.info(f"  Exists   → {name}  (skipped)")


# ─────────────────────────────────────────────────────────────
# 1. AGENT VOLUNTEER PROFILES
#
# Stores extended volunteer info the agent collects conversationally.
# Linked to the existing `users` collection via user_id.
# Admin dashboard never touches this.
#
# Document shape:
# {
#     "user_id"         : ObjectId,   # → users._id
#     "user_email"      : str,
#     "name"            : str,
#     "department"      : str,        # "CSE", "ECE", "MECH" …
#     "year"            : int,        # 1 | 2 | 3 | 4
#     "phone"           : str,
#     "mandatory_hours" : int,        # default 120
#     "availability"    : [str],      # ["saturday", "sunday", "wednesday"]
#     "tags"            : [str],      # ["blood_donor", "first_aid", "photography"]
#                                     # open-ended — add any string, no schema change needed
#     "created_at"      : datetime,
#     "updated_at"      : datetime
# }
# ─────────────────────────────────────────────────────────────
# not needed since we already have users collection


# ─────────────────────────────────────────────────────────────
# 2. AGENT SCHEDULED JOBS
#
# One-time reminders: "Remind me 10 minutes before the pledge event"
# APScheduler polls this every minute and fires due jobs.
#
# Document shape:
# {
#     "user_id"     : ObjectId,
#     "user_email"  : str,
#     "job_type"    : "reminder",
#     "trigger_at"  : datetime,       # exact UTC time to fire
#     "channel"     : "email",        # "email" | "in_app"
#     "subject"     : str,
#     "message"     : str,
#     "sent"        : bool,           # False → scheduler flips True after send
#     "created_at"  : datetime,
#     "metadata"    : {               # flexible — store any extra context
#         "activity_id"    : str,
#         "activity_title" : str,
#         "minutes_before" : int
#     }
# }
# ─────────────────────────────────────────────────────────────

safe_create("agent_scheduled_jobs")
# Compound index — scheduler queries exactly this filter every minute
db.agent_scheduled_jobs.create_index(
    [("trigger_at", ASCENDING), ("sent", ASCENDING)]
)
db.agent_scheduled_jobs.create_index("user_id")


# ─────────────────────────────────────────────────────────────
# 3. AGENT SUBSCRIPTIONS
#
# Persistent "notify me when" rules.
# e.g. "Notify me whenever a weekend activity with 4+ hours is posted"
# Checked every time admin posts a new activity.
#
# Document shape:
# {
#     "user_id"           : ObjectId,
#     "user_email"        : str,
#     "trigger_condition" : {         # mongo-style filter the new activity must match
#         "day_of_week"       : {"$in": ["saturday", "sunday"]},
#         "attendance_hours"  : {"$gte": 4},
#         "category"          : "blood_donation"   # optional
#     },
#     "channel"    : "email",
#     "active"     : bool,            # user can cancel → set False
#     "created_at" : datetime
# }
# ─────────────────────────────────────────────────────────────

safe_create("agent_subscriptions")
db.agent_subscriptions.create_index("user_id")
db.agent_subscriptions.create_index("active")    # only scan active=True docs


# ─────────────────────────────────────────────────────────────
# 4. AGENT MEMORY
#
# Short-term context the agent carries across sessions per user.
# Prevents asking the same onboarding questions twice.
#
# Document shape:
# {
#     "user_id"      : ObjectId,
#     "last_intent"  : str,           # last thing user asked about
#     "context"      : {              # any key-value state the agent wants to remember
#         "pending_activity_id" : str,
#         "last_hours_checked"  : int,
#         "onboarded"           : bool
#     },
#     "updated_at"   : datetime
# }
# ─────────────────────────────────────────────────────────────

safe_create("agent_memory")
db.agent_memory.create_index("user_id", unique=True)


# ─────────────────────────────────────────────────────────────
# 5. AGENT AUDIT LOG
#
# Every tool call the agent makes — for debugging and transparency.
# Never shown to users; used by developers to trace agent behaviour.
#
# Document shape:
# {
#     "user_id"        : ObjectId,
#     "tool_called"    : str,         # "query_records", "aggregate_records" …
#     "parameters"     : dict,        # exactly what the LLM passed
#     "result_count"   : int,         # how many records returned
#     "error"          : str | None,  # None if successful
#     "duration_ms"    : int,         # how long the tool took
#     "timestamp"      : datetime
# }
# ─────────────────────────────────────────────────────────────

safe_create("agent_audit_log")
db.agent_audit_log.create_index([("timestamp", DESCENDING)])
db.agent_audit_log.create_index("user_id")
db.agent_audit_log.create_index("tool_called")


# ─────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────

logger.info("\nAll agent collections are ready.")
client.close()