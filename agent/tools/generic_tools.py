"""
agent/tools/generic_tools.py
-----------------------------
6 generic tools that power every complex workflow the agent handles.

DEFENSIVE NORMALISATION (this version):
    All string filter VALUES are trimmed and matched case-insensitively
    by default. This means "Workshop - Youth..." matches even if the
    LLM sends "workshop- youth..." (different case, missing space,
    extra space). This is implemented ONCE in _build_mongo_filter and
    applies automatically to every tool that uses it — query_records,
    aggregate_records, mutate_record. No need to repeat logic per tool.

    Numeric values, booleans, ObjectIds, and dict operators ($in, $gte
    etc.) are left untouched — normalisation only applies to plain
    string values, since those are the ones vulnerable to casing/
    whitespace mismatches.
"""

import logging
import re
import time
import smtplib
import os
import pytz

from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime as dt_now
from werkzeug.security import generate_password_hash

from bson import ObjectId
from langchain_core.tools import tool

from db import db
from agent.schema_config import enrich_payload

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ACCESS CONTROL + VALIDATION CONFIG
# ═══════════════════════════════════════════════════════════════

WRITE_PERMISSIONS = {
    "users"                : ["admin"],
    "activities"           : ["admin"],
    "announcements"        : ["admin"],
    "registrations"        : ["admin", "volunteer"],
    "agent_scheduled_jobs" : ["admin", "volunteer"],
    "agent_subscriptions"  : ["admin", "volunteer"],
    "agent_memory"         : ["admin", "volunteer"],
}

REQUIRED_FIELDS = {
    "users"        : ["email", "password", "role"],
    "activities"   : ["title", "description", "date",
                      "attendance_hours", "no_of_volunteers"],
    "announcements": ["title", "content"],
    "registrations": ["user_id", "activity_id", "user_email", "activity_title"],
}

READABLE_COLLECTIONS = {
    "users", "activities", "registrations",
    "announcements", "agent_subscriptions", "agent_scheduled_jobs",
}

# Fields that should NEVER be normalised even though they are strings —
# exact-match identifiers, not human-typed free text.
EXACT_MATCH_FIELDS = {
    "_id", "user_id", "activity_id", "email", "user_email",
    "role", "status", "attendance_status", "job_type", "channel",
    "created_via", "created_by",
}


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _log_tool_call(user_id, tool_name, params, result_count, error, duration_ms):
    """Write one audit record. Never raises — errors are silently logged."""
    try:
        db.agent_audit_log.insert_one({
            "user_id"     : user_id,
            "tool_called" : tool_name,
            "parameters"  : params,
            "result_count": result_count,
            "error"       : error,
            "duration_ms" : duration_ms,
            "timestamp"   : datetime.now(timezone.utc),
        })
    except Exception as exc:
        logger.warning(f"Audit log write failed: {exc}")


def _send_email(to_email: str, subject: str, message: str) -> bool:
    sender  = os.getenv("GMAIL_SENDER_EMAIL")
    app_pwd = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not app_pwd:
        logger.error("GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set in .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = to_email
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_pwd)
            server.sendmail(sender, to_email, msg.as_string())

        logger.info(f"Email sent to {to_email}")
        return True

    except Exception as exc:
        logger.error(f"Email send failed to {to_email}: {exc}")
        return False


def _serialize(doc: dict) -> dict:
    """Convert ObjectId and datetime fields to strings for LLM consumption."""
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        elif isinstance(v, list):
            result[k] = [_serialize(i) if isinstance(i, dict) else
                         str(i) if isinstance(i, ObjectId) else i
                         for i in v]
        else:
            result[k] = v
    return result


def _normalise_string(value: str) -> str:
    """Trim leading/trailing whitespace and collapse internal multiple
    spaces into one. Does NOT lowercase here — case-insensitivity is
    handled separately via regex, so the original casing is preserved
    for display purposes, only whitespace is cleaned."""
    return re.sub(r"\s+", " ", value.strip())


def _case_insensitive_exact(value: str):
    """
    Build a MongoDB regex filter that matches the value case-insensitively
    and tolerant of leading/trailing whitespace differences in the stored
    document. Anchors the match so it's still an "exact" match semantically,
    just casing/whitespace-tolerant — not a partial/substring match.
    """
    cleaned = _normalise_string(value)
    # Escape regex special characters in the user-provided text
    escaped = re.escape(cleaned)
    # Allow flexible whitespace between words (handles "Workshop -" vs "Workshop-")
    flexible = escaped.replace(r"\ ", r"\s*")
    return {"$regex": f"^{flexible}$", "$options": "i"}


def _build_mongo_filter(filters: dict) -> dict:
    """
    Safely convert LLM-supplied filter dict to a valid PyMongo filter.

    Normalisation rules applied automatically:
      - *_id fields           → cast to ObjectId
      - dict values ($in etc) → passed through, but string items inside
                                $in lists are also normalised
      - plain string values   → case-insensitive, whitespace-tolerant
                                regex match (UNLESS field is in
                                EXACT_MATCH_FIELDS, e.g. email, role)
      - everything else       → passed through unchanged (numbers, bools)
    """
    mongo_filter = {}

    for key, value in filters.items():

        # ── ObjectId fields ───────────────────────────────────
        if key.endswith("_id") and isinstance(value, str):
            try:
                mongo_filter[key] = ObjectId(value.strip())
            except Exception:
                mongo_filter[key] = value
            continue

        # ── Operator dicts: $in, $gte, $lte, $ne, etc ─────────
        if isinstance(value, dict):
            normalised_ops = {}
            for op, op_val in value.items():
                if op == "$in" and isinstance(op_val, list):
                    normalised_ops[op] = [
                        _normalise_string(v).lower() if isinstance(v, str) else v
                        for v in op_val
                    ]
                elif isinstance(op_val, str) and key not in EXACT_MATCH_FIELDS:
                    normalised_ops[op] = _normalise_string(op_val)
                else:
                    normalised_ops[op] = op_val
            mongo_filter[key] = normalised_ops
            continue

        # ── Plain string values ───────────────────────────────
        if isinstance(value, str):
            if key in EXACT_MATCH_FIELDS:
                # exact-match identifiers — just trim, don't fuzzy-match
                mongo_filter[key] = _normalise_string(value)
            else:
                # human-typed free text (titles, names, locations) —
                # case-insensitive, whitespace-tolerant match
                mongo_filter[key] = _case_insensitive_exact(value)
            continue

        # ── Everything else (numbers, booleans, lists of non-str) ──
        mongo_filter[key] = value

    return mongo_filter


def _strip_markdown(text: str) -> str:
    """
    Removes Markdown syntax artifacts (**bold**, *bullet*, # headers,
    `code`) that the LLM sometimes generates when asked to "summarise
    in bullets". The database should store clean plain text — bullet
    rendering is a frontend concern, not a storage concern.

    Converts:
        "**Day 1: Title**\n* point one\n* point two"
    Into:
        "Day 1: Title. point one. point two"
    """
    if not text:
        return text

    cleaned = text

    # Remove bold/italic markers: **text** or *text* → text
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)

    # Remove markdown headers: ### Title → Title
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)

    # Convert bullet markers (* or -) at line start into ". " separators
    cleaned = re.sub(r"^\s*[\*\-]\s+", "", cleaned, flags=re.MULTILINE)

    # Remove inline code backticks
    cleaned = cleaned.replace("`", "")

    # Collapse newlines into single spaces, then clean up double spacing
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def _normalise_payload_strings(payload: dict) -> dict:
    """
    Trims whitespace AND strips Markdown syntax artifacts (**, *, #,
    backticks) on all top-level string values in an insert/update
    payload before writing to the database. The LLM sometimes
    generates Markdown formatting when summarising — that belongs in
    frontend rendering, never in raw stored data. Nested dicts/lists
    are left as-is.
    """
    cleaned = {}
    for key, value in payload.items():
        if isinstance(value, str):
            no_markdown = _strip_markdown(value)
            cleaned[key] = _normalise_string(no_markdown)
        else:
            cleaned[key] = value
    return cleaned


# ═══════════════════════════════════════════════════════════════
# TOOL 1 — query_records
# ═══════════════════════════════════════════════════════════════

@tool
def query_records(
    collection: str,
    filters: dict,
    fields: list = [],
    limit: int = 50,
    user_id: str = "",
    sort_by: str = "",
    sort_order: str = "asc",
) -> list:
    """
    Fetch filtered documents from any NSS database collection.
    String filter values are automatically matched case-insensitively
    and are tolerant of extra/missing whitespace — you don't need to
    worry about exact casing or spacing when filtering by title, name,
    location, etc.

    Args:
        collection : One of: users, activities, registrations,
                     announcements, agent_subscriptions, agent_scheduled_jobs.
        filters    : MongoDB-style filter dict. Use $in for array fields.
                     Pass {} for no filter.
        fields     : List of field names to return. Pass [] for all fields.
        sort_by    : Field name to sort results by. Pass "" for no sort.
        sort_order : "asc" or "desc".
        limit      : Max documents to return. Default 50. Max 200.
        user_id    : ID of the user invoking the agent (for audit log).

    Returns:
        List of matching documents as dicts (ObjectIds converted to strings).
    """
    start     = time.time()
    params    = dict(collection=collection, filters=filters,
                     fields=fields, sort_by=sort_by,
                     sort_order=sort_order, limit=limit)

    try:
        collection = collection.strip().lower()

        if collection not in READABLE_COLLECTIONS:
            raise ValueError(f"Collection '{collection}' is not accessible.")

        limit      = min(int(limit or 50), 200)
        projection = {f: 1 for f in fields} if fields else {}
        mfilter    = _build_mongo_filter(filters or {})
        cursor     = db[collection].find(mfilter, projection)

        if sort_by:
            direction = 1 if sort_order == "asc" else -1
            cursor    = cursor.sort(sort_by, direction)

        results = [_serialize(doc) for doc in cursor.limit(limit)]
        _log_tool_call(user_id, "query_records", params,
                       len(results), None,
                       int((time.time() - start) * 1000))
        return results

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"query_records failed: {exc}")
        _log_tool_call(user_id, "query_records", params,
                       0, error_msg,
                       int((time.time() - start) * 1000))
        return [{"error": error_msg}]


# ═══════════════════════════════════════════════════════════════
# TOOL 2 — aggregate_records
# ═══════════════════════════════════════════════════════════════

@tool
def aggregate_records(
    collection: str,
    match_filters: dict,
    group_by: str,
    metric: str,
    metric_field: str = "",
    sort_by_result: str = "desc",
    limit: int = 50,
    user_id: str = "",
) -> list:
    """
    Compute grouped statistics on any NSS collection.
    String filters in match_filters are normalised the same way as
    query_records — case-insensitive, whitespace-tolerant.

    Args:
        collection     : Collection to aggregate over.
        match_filters  : Pre-aggregation filter dict. Pass {} for all docs.
        group_by       : Field to group results by. Use "month" for
                         registrations/activities grouped by month.
        metric         : "sum", "count", or "avg".
        metric_field   : Field to apply the metric on.
        sort_by_result : "asc" or "desc".
        limit          : Max groups to return.
        user_id        : ID of the user invoking the agent (for audit log).

    Returns:
        List of {group_value, result} dicts.
    """
    start  = time.time()
    params = dict(collection=collection, match_filters=match_filters,
                  group_by=group_by, metric=metric,
                  metric_field=metric_field, limit=limit)

    METRIC_MAP = {"sum": "$sum", "count": "$sum", "avg": "$avg"}

    try:
        collection = collection.strip().lower()
        group_by   = group_by.strip()

        agg_op   = METRIC_MAP.get(metric.strip().lower(), "$sum")
        mfilter  = _build_mongo_filter(match_filters or {})
        sort_dir = 1 if sort_by_result.strip().lower() == "asc" else -1
        limit    = min(int(limit or 50), 500)

        if group_by.lower() == "month":
            group_id = {"$month": "$date"}
        else:
            group_id = f"${group_by}"

        agg_value = (
            {"$sum": 1}
            if metric.strip().lower() == "count"
            else {agg_op: f"${metric_field}"}
        )

        pipeline = [
            {"$match": mfilter},
            {"$group": {"_id": group_id, "result": agg_value}},
            {"$sort":  {"result": sort_dir}},
            {"$limit": limit},
        ]

        results = [_serialize(doc) for doc in db[collection].aggregate(pipeline)]
        _log_tool_call(user_id, "aggregate_records", params,
                       len(results), None,
                       int((time.time() - start) * 1000))
        return results

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"aggregate_records failed: {exc}")
        _log_tool_call(user_id, "aggregate_records", params,
                       0, error_msg,
                       int((time.time() - start) * 1000))
        return [{"error": error_msg}]


# ═══════════════════════════════════════════════════════════════
# TOOL 3 — get_volunteer_hours_summary
# ═══════════════════════════════════════════════════════════════

@tool
def get_volunteer_hours_summary(
    target_user_id: str,
    extra_filters: dict,
    invoking_user_id: str,
) -> list:
    """
    Return completed hours, remaining hours, and activity count per volunteer.
    Joins registrations → activities → users in one pipeline.

    Args:
        target_user_id  : ObjectId string of a specific volunteer, or
                          "all" to fetch every volunteer.
        extra_filters   : Additional filters on users (department, year).
                          Pass {} for no extra filters.
        invoking_user_id: ID of the user invoking the agent (for audit log).

    Returns:
        List of dicts with keys: user_id, name, email, department, year,
        completed_hours, mandatory_hours, remaining_hours, activities_attended.
    """
    start  = time.time()
    params = dict(target_user_id=target_user_id, extra_filters=extra_filters)

    try:
        target_user_id = (target_user_id or "").strip()

        if target_user_id and target_user_id.lower() != "all":
            try:
                uid_filter = {"_id": ObjectId(target_user_id)}
            except Exception:
                uid_filter = {"email": _normalise_string(target_user_id)}
        else:
            uid_filter = {"role": "volunteer"}

        if extra_filters:
            uid_filter.update(_build_mongo_filter(extra_filters))

        profiles = list(db.users.find(uid_filter))

        if not profiles:
            return [{"message": "No volunteers found for the given filters."}]

        user_id_map = {str(p["_id"]): p for p in profiles}
        oid_list    = [p["_id"] for p in profiles]

        pipeline = [
            {
                "$match": {
                    "user_id"          : {"$in": oid_list},
                    "attendance_status": "present",
                }
            },
            {
                "$lookup": {
                    "from"        : "activities",
                    "localField"  : "activity_id",
                    "foreignField": "_id",
                    "as"          : "activity",
                }
            },
            {"$unwind": "$activity"},
            {
                "$group": {
                    "_id"                : "$user_id",
                    "completed_hours"    : {"$sum": "$activity.attendance_hours"},
                    "activities_attended": {"$sum": 1},
                }
            },
        ]

        hours_map = {
            str(r["_id"]): {
                "completed_hours"    : r["completed_hours"],
                "activities_attended": r["activities_attended"],
            }
            for r in db.registrations.aggregate(pipeline)
        }

        results = []
        for uid_str, profile in user_id_map.items():
            h = hours_map.get(uid_str, {"completed_hours": 0, "activities_attended": 0})
            mandatory = profile.get("mandatory_hours", 120)
            completed = h["completed_hours"]

            results.append({
                "user_id"            : uid_str,
                "name"               : profile.get("name", ""),
                "email"              : profile.get("email", ""),
                "department"         : profile.get("department", ""),
                "year"               : profile.get("year", ""),
                "completed_hours"    : completed,
                "mandatory_hours"    : mandatory,
                "remaining_hours"    : max(mandatory - completed, 0),
                "activities_attended": h["activities_attended"],
            })

        _log_tool_call(invoking_user_id, "get_volunteer_hours_summary",
                       params, len(results), None,
                       int((time.time() - start) * 1000))
        return results

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"get_volunteer_hours_summary failed: {exc}")
        _log_tool_call(invoking_user_id, "get_volunteer_hours_summary",
                       params, 0, error_msg,
                       int((time.time() - start) * 1000))
        return [{"error": error_msg}]


# ═══════════════════════════════════════════════════════════════
# TOOL 4 — mutate_record
# ═══════════════════════════════════════════════════════════════

@tool
def mutate_record(
    operation  : str,
    collection : str,
    filters    : dict = {},
    payload    : dict = {},
    confirm    : str  = "false",
    user_id    : str  = "",
    role       : str  = "volunteer",
) -> dict:
    """
    Insert, update, or delete a document in the database.

    Role-based access control is enforced. Computed fields (like
    day_of_week derived from date) are auto-filled via schema_config.py.
    Filter VALUES used for update/delete are matched case-insensitively
    and whitespace-tolerant (e.g. "act5" matches "Act5 " or "ACT 5"),
    so you don't need the exact stored casing/spacing to target a record.
    Payload string fields are trimmed of extra whitespace before saving.

    Args:
        operation  : "insert", "update", or "delete".
        collection : Target collection name.
        filters    : For "update"/"delete" — which documents to target.
        payload    : For "insert" — full document. For "update" — fields to set.
        confirm    : Pass the string "true" to proceed, or "false" to abort.
                     Always pass as a quoted string, e.g. "true", not the
                     boolean literal true.
        user_id    : ID of the invoking user.
        role       : Role of the invoking user.

    Returns:
        Dict with status and operation result.
    """
    start = time.time()

    # ── Defensive normalisation of control parameters ────────────
    operation  = (operation or "").strip().lower()
    collection = (collection or "").strip().lower()
    role       = (role or "").strip().lower()
    user_id    = (user_id or "").strip()

    # Groq sometimes sends confirm as a string "true"/"false" instead of bool
    if isinstance(confirm, str):
        confirm = confirm.strip().lower() == "true"

    filters = filters or {}
    payload = payload or {}

    params = dict(operation=operation, collection=collection,
                  filters=filters, payload=payload, role=role)

    if not confirm:
        return {
            "status": "aborted",
            "reason": "confirm flag is False — operation not executed."
        }

    if collection not in WRITE_PERMISSIONS:
        return {
            "status": "error",
            "reason": f"Collection '{collection}' is not writable by the agent."
        }

    allowed_roles = WRITE_PERMISSIONS[collection]
    if role not in allowed_roles:
        return {
            "status": "error",
            "reason": (
                f"Access denied. Only {allowed_roles} can write to "
                f"'{collection}'. Current role: '{role}'."
            )
        }

    # ── Volunteers can only update their OWN user document ───────
    if collection == "users" and role == "volunteer" and operation == "update":
        try:
            filters["_id"] = ObjectId(user_id)
        except Exception:
            return {"status": "error", "reason": "Invalid user_id."}

    if operation == "insert" and collection in REQUIRED_FIELDS:
        required = REQUIRED_FIELDS[collection]
        missing  = [f for f in required if f not in payload]
        if missing:
            return {
                "status" : "validation_error",
                "reason" : f"Missing required fields for '{collection}': {missing}",
                "missing": missing,
            }

    try:
        # filters use the same normalised matching as query_records —
        # this is what fixes "act5" not matching "Act 5" type mismatches
        mfilter = _build_mongo_filter(filters)

        if operation == "insert":
            # ── Hash password before storing — never store plain text ──
            if collection == "users" and "password" in payload:
                payload["password"] = generate_password_hash(payload["password"])
            payload = _normalise_payload_strings(payload)
            payload = enrich_payload(collection, payload)

            payload["created_at"]  = datetime.now(timezone.utc)
            payload["created_via"] = "agent"
            payload["created_by"]  = user_id

            result = db[collection].insert_one(payload)
            out = {
                "status"     : "success",
                "inserted_id": str(result.inserted_id),
                "message"    : f"Record added to '{collection}' successfully."
            }

        elif operation == "update":
            payload = _normalise_payload_strings(payload)
            payload["updated_at"]  = datetime.now(timezone.utc)
            payload["updated_via"] = "agent"

            if not mfilter:
                return {
                    "status": "error",
                    "reason": "Update requires a filter. Refusing bulk update."
                }

            result = db[collection].update_many(mfilter, {"$set": payload})

            if result.matched_count == 0:
                return {
                    "status" : "not_found",
                    "reason" : (
                        f"No document in '{collection}' matched the given "
                        f"filter, even with case-insensitive matching. "
                        f"Double-check the value exists."
                    )
                }

            out = {
                "status"        : "success",
                "matched_count" : result.matched_count,
                "modified_count": result.modified_count,
            }

        elif operation == "delete":
            if not mfilter:
                return {
                    "status": "error",
                    "reason": "Delete requires a filter. Refusing bulk delete."
                }

            result = db[collection].delete_many(mfilter)

            if result.deleted_count == 0:
                return {
                    "status": "not_found",
                    "reason": (
                        f"No document in '{collection}' matched the given "
                        f"filter, even with case-insensitive matching."
                    )
                }

            out = {"status": "success", "deleted_count": result.deleted_count}

        else:
            return {"status": "error", "reason": f"Unknown operation '{operation}'."}

        _log_tool_call(user_id, "mutate_record", params,
                       1, None, int((time.time() - start) * 1000))
        return out

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"mutate_record failed: {exc}")
        _log_tool_call(user_id, "mutate_record", params,
                       0, error_msg, int((time.time() - start) * 1000))
        return {"status": "error", "reason": error_msg}


# ═══════════════════════════════════════════════════════════════
# TOOL 5 — schedule_job
# ═══════════════════════════════════════════════════════════════
@tool
def schedule_job(
    target_user_id: str,
    user_email    : str,
    job_type      : str,
    trigger_at_iso: str,
    channel       : str,
    subject       : str,
    message       : str,
    metadata      : dict = {},
    invoking_user_id: str = "",
) -> dict:
    """
    Schedule a future email/notification for a user.

    Args:
        target_user_id  : ObjectId string of the user to notify.
        user_email      : Email address of the user to notify.
        job_type        : "reminder".
        trigger_at_iso  : ISO 8601 datetime string for when to fire.
                          Always pass in IST — tool converts to UTC for storage.
        channel         : "email".
        subject         : Email subject line.
        message         : Email body text.
        metadata        : Extra context dict.
        invoking_user_id: ID of the user invoking the agent (for audit log).

    Returns:
        Dict with "status" and "trigger_at" confirmation.
    """
    start  = time.time()
    params = dict(target_user_id=target_user_id, job_type=job_type,
                  trigger_at_iso=trigger_at_iso)

    try:
        target_user_id = target_user_id.strip()
        user_email     = _normalise_string(user_email).lower()

        IST = pytz.timezone("Asia/Kolkata")
        UTC = pytz.utc

        # ── Step 1: Parse datetime ────────────────────────────
        raw_dt = datetime.fromisoformat(trigger_at_iso.strip())

        # If no timezone info, assume IST (all users are in India)
        if raw_dt.tzinfo is None:
            raw_dt = IST.localize(raw_dt)

        # ── Step 2: Convert to UTC for storage ────────────────
        trigger_dt_utc = raw_dt.astimezone(UTC).replace(tzinfo=None)

        # ── Step 3: Keep IST for display ──────────────────────
        trigger_dt_ist = raw_dt.astimezone(IST)

        # ── Step 4: Past-date guard ───────────────────────────
        # Must happen AFTER trigger_dt_utc and trigger_dt_ist are computed
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if trigger_dt_utc < now_utc:
            return {
                "status": "error",
                "reason": (
                    f"The time {trigger_dt_ist.strftime('%d %b %Y %I:%M %p IST')} "
                    f"is in the past. Please provide a future date and time."
                )
            }

        # ── Step 5: Save to DB ────────────────────────────────
        job = {
            "user_id"    : ObjectId(target_user_id),
            "user_email" : user_email,
            "job_type"   : job_type.strip().lower(),
            "trigger_at" : trigger_dt_utc,        # stored as UTC
            "channel"    : channel.strip().lower(),
            "subject"    : _normalise_string(subject),
            "message"    : message.strip(),
            "sent"       : False,
            "created_at" : datetime.now(timezone.utc),
            "metadata"   : metadata or {},
        }

        result = db.agent_scheduled_jobs.insert_one(job)

        out = {
            "status"    : "scheduled",
            "job_id"    : str(result.inserted_id),
            "trigger_at": trigger_dt_ist.isoformat(),
            "message"   : f"Reminder scheduled for {trigger_dt_ist.strftime('%d %b %Y %I:%M %p IST')}",
        }

        _log_tool_call(invoking_user_id, "schedule_job", params,
                       1, None, int((time.time() - start) * 1000))
        return out

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"schedule_job failed: {exc}")
        _log_tool_call(invoking_user_id, "schedule_job", params,
                       0, error_msg, int((time.time() - start) * 1000))
        return {"status": "error", "reason": error_msg}
# ═══════════════════════════════════════════════════════════════
# TOOL 6 — send_notification
# ═══════════════════════════════════════════════════════════════

@tool
def send_notification(
    user_emails  : list,
    subject      : str,
    message      : str,
    invoking_user_id: str = "",
) -> dict:
    """
    Send an immediate email notification to one or more users.

    Args:
        user_emails      : List of email addresses to notify.
        subject          : Email subject line.
        message          : Email body text.
        invoking_user_id : ID of the user invoking the agent (for audit log).

    Returns:
        Dict with total sent count and failed count.
    """
    start  = time.time()
    params = dict(user_emails=user_emails, subject=subject)
    sent   = 0
    failed = 0

    cleaned_emails = [
        _normalise_string(e).lower() for e in (user_emails or []) if e
    ]

    for email in cleaned_emails:
        if _send_email(email, subject, message):
            sent += 1
        else:
            failed += 1

    out = {
        "status": "done",
        "total" : len(cleaned_emails),
        "sent"  : sent,
        "failed": failed,
    }

    _log_tool_call(invoking_user_id, "send_notification", params,
                   sent, None if failed == 0 else f"{failed} failed",
                   int((time.time() - start) * 1000))
    return out