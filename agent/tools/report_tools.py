"""
agent/tools/report_tools.py
----------------------------
Two new LangGraph agent tools:

  semantic_search_reports   — lightweight qualitative search via Atlas
                              Vector Search; available to all users.
  request_report            — queues a full analytical report job;
                              restricted to admin / NSS-coordinator role.

Both follow the same audit-logging pattern as generic_tools.py:
_log_tool_call writes to agent_audit_log on every invocation.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from langchain_core.tools import tool

from db import db

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Roles allowed to submit report generation jobs
# ─────────────────────────────────────────────────────────────
REPORT_ADMIN_ROLES = {"admin", "nss-coordinator"}

# Minimum chunks needed to include a narrative section in the report
# (activities below this threshold get a stats-only report with a note)
NARRATIVE_MIN_CHUNKS = 2


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _log_tool_call(user_id, tool_name, params, result_count, error, duration_ms):
    """Mirror of the generic_tools audit logger — writes to agent_audit_log."""
    try:
        db.agent_audit_log.insert_one({
            "user_id":      user_id,
            "tool_called":  tool_name,
            "parameters":   params,
            "result_count": result_count,
            "error":        error,
            "duration_ms":  duration_ms,
            "timestamp":    datetime.now(timezone.utc),
        })
    except Exception as exc:
        logger.warning(f"Audit log write failed: {exc}")


# ─────────────────────────────────────────────────────────────
# TOOL 1 — semantic_search_reports
# ─────────────────────────────────────────────────────────────

@tool
def semantic_search_reports(
    query: str,
    filters: dict = {},
    top_k: int = 5,
    user_id: str = "",
) -> list:
    """
    Search qualitative / narrative content from uploaded activity reports
    and agent-generated report summaries using semantic similarity.

    Use this for questions like:
      - "What challenges were faced in blood donation camps?"
      - "Find events similar to the digital literacy workshop."
      - "What did volunteers say about the tree plantation drive?"

    Do NOT use this for counting, totals, or date-range stats — use
    aggregate_records / query_records for those.

    Args:
        query   : Natural-language question or topic to search for.
        filters : Optional pre-filter dict. Supported keys:
                    year (int), month (int), category (str),
                    activity_id (str ObjectId), source ("manual_upload"
                    or "agent_generated").
        top_k   : Number of most-relevant chunks to return (max 10).
        user_id : Invoking user ID for audit log.

    Returns:
        List of dicts: {activity_id, title, year, month, category,
        source, text, score}.  Score is cosine similarity (higher = more
        relevant).  Returns [] if no embeddings exist.
    """
    start  = time.time()
    params = dict(query=query, filters=filters, top_k=top_k)

    try:
        top_k = min(int(top_k or 5), 10)

        # ── 1. Build query embedding ─────────────────────────
        from utils.ingestion import get_embeddings
        query_vector = get_embeddings([query])[0]

        # ── 2. Build Atlas Vector Search pipeline ────────────
        # Pre-filter reduces the ANN search space before scoring.
        # Only fields stored as top-level keys in the collection can
        # be used in pre-filter (year, month, category, activity_id, source).
        pre_filter = {}
        for key, val in (filters or {}).items():
            if key == "activity_id" and isinstance(val, str):
                try:
                    pre_filter[key] = ObjectId(val)
                except Exception:
                    pass
            elif key in ("year", "month") and val is not None:
                pre_filter[key] = int(val)
            elif key in ("category", "source") and val:
                pre_filter[key] = val

        vector_stage = {
            "$vectorSearch": {
                "index":         "agent_embeddings_index",   # Atlas vector index name
                "path":          "embedding",
                "queryVector":   query_vector,
                "numCandidates": top_k * 10,
                "limit":         top_k,
            }
        }
        if pre_filter:
            vector_stage["$vectorSearch"]["filter"] = pre_filter

        pipeline = [
            vector_stage,
            {
                "$project": {
                    "activity_id": {"$toString": "$activity_id"},
                    "title":       1,
                    "year":        1,
                    "month":       1,
                    "category":    1,
                    "source":      1,
                    "text":        1,
                    "score":       {"$meta": "vectorSearchScore"},
                }
            }
        ]

        results = list(db.agent_activity_embeddings.aggregate(pipeline))
        _log_tool_call(user_id, "semantic_search_reports", params,
                       len(results), None,
                       int((time.time() - start) * 1000))
        return results

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"semantic_search_reports failed: {exc}")
        _log_tool_call(user_id, "semantic_search_reports", params,
                       0, error_msg,
                       int((time.time() - start) * 1000))
        return [{"error": error_msg}]


# ─────────────────────────────────────────────────────────────
# TOOL 2 — request_report
# ─────────────────────────────────────────────────────────────

@tool
def request_report(
    scope: str,
    role: str = "volunteer",
    user_id: str = "",
    user_email: str = "",
    year: int = None,
    month: int = None,
    activity_id: str = "",
    category: str = "",
    comparison_year: int = None,
) -> dict:
    """
    Request generation of a rich analytical report.
    Returns immediately with a job_id; the report is compiled in the
    background and the user is notified by email when ready.

    RESTRICTED TO: admin and NSS-coordinator roles only.

    Supported scopes:
      "annual"          — full-year report (requires: year)
      "monthly"         — single-month report (requires: year, month)
      "single_activity" — one event report (requires: activity_id)
      "category"        — all events of a category (requires: category,
                          optionally year)
      "comparison"      — year-over-year comparison (requires: year,
                          comparison_year)

    Args:
        scope           : One of the scopes listed above.
        role            : Role of the requesting user (access control).
        user_id         : Requesting user's ID (for audit log + notification).
        user_email      : Requesting user's email (for completion notification).
        year            : 4-digit year integer.
        month           : Month integer 1–12.
        activity_id     : ObjectId string of a specific activity.
        category        : Activity category string.
        comparison_year : Second year for "comparison" scope.

    Returns:
        {"status": "queued", "job_id": "...", "message": "..."}
        or {"status": "error", "reason": "..."}
    """
    start  = time.time()
    params = dict(scope=scope, year=year, month=month,
                  activity_id=activity_id, category=category,
                  comparison_year=comparison_year)

    # ── Role check ───────────────────────────────────────────
    if (role or "").strip().lower() not in REPORT_ADMIN_ROLES:
        _log_tool_call(user_id, "request_report", params, 0,
                       "access_denied", int((time.time() - start) * 1000))
        return {
            "status": "error",
            "reason": (
                f"Report generation is restricted to admin / NSS-coordinator roles. "
                f"Current role: '{role}'. Contact your coordinator to request a report."
            )
        }

    # ── Scope validation ─────────────────────────────────────
    VALID_SCOPES = {"annual", "monthly", "single_activity", "category", "comparison"}
    scope = (scope or "").strip().lower()
    if scope not in VALID_SCOPES:
        return {"status": "error", "reason": f"Unknown scope '{scope}'. Valid: {VALID_SCOPES}"}

    if scope == "annual" and not year:
        return {"status": "error", "reason": "'annual' scope requires year."}
    if scope == "monthly" and (not year or not month):
        return {"status": "error", "reason": "'monthly' scope requires year and month."}
    if scope == "single_activity" and not activity_id:
        return {"status": "error", "reason": "'single_activity' scope requires activity_id."}
    if scope == "category" and not category:
        return {"status": "error", "reason": "'category' scope requires category."}
    if scope == "comparison" and (not year or not comparison_year):
        return {"status": "error", "reason": "'comparison' scope requires year and comparison_year."}

    try:
        # ── Build job document ───────────────────────────────
        job_doc = {
            "user_id":        user_id,
            "user_email":     user_email,
            "status":         "pending",
            "params": {
                "scope":           scope,
                "year":            year,
                "month":           month,
                "activity_id":     activity_id,
                "category":        category,
                "comparison_year": comparison_year,
            },
            "output_file_url": None,
            "error_reason":    None,
            "created_at":      datetime.now(timezone.utc),
            "updated_at":      datetime.now(timezone.utc),
        }

        result = db.agent_report_jobs.insert_one(job_doc)
        job_id = str(result.inserted_id)

        scope_desc = {
            "annual":          f"annual report for {year}",
            "monthly":         f"monthly report for {year}-{month:02d}",
            "single_activity": f"report for activity {activity_id}",
            "category":        f"'{category}' category report"
                               + (f" for {year}" if year else ""),
            "comparison":      f"year-over-year comparison {year} vs {comparison_year}",
        }

        _log_tool_call(user_id, "request_report", params, 1, None,
                       int((time.time() - start) * 1000))
        return {
            "status":  "queued",
            "job_id":  job_id,
            "message": (
                f"Your {scope_desc[scope]} has been queued (job ID: {job_id}). "
                f"You will receive an email at {user_email} when it is ready. "
                f"You can also check progress at /reports/jobs/{job_id}."
            )
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"request_report failed: {exc}")
        _log_tool_call(user_id, "request_report", params, 0, error_msg,
                       int((time.time() - start) * 1000))
        return {"status": "error", "reason": error_msg}
