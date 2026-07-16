"""
agent/nodes/verify_node.py
----------------------------
Runs automatically after every tool call. If the last tool call was
mutate_record with an insert/update operation, this node re-queries
the database to confirm the write actually happened — BEFORE the
agent is allowed to tell the user "success".

This solves the hallucination problem at the architecture level
instead of relying on prompt instructions the LLM might ignore.

How it fits in the graph:
    agent → tools → verify → agent → (loop or END)

The verify node does NOT call the LLM. It's pure Python logic that
inspects the last tool result and, if needed, performs one extra
database read to confirm reality.
"""

import json
import logging

from langchain_core.messages import ToolMessage
from bson import ObjectId

from db import db

logger = logging.getLogger(__name__)


def verify_node(state: dict) -> dict:
    """
    Inspects the most recent tool message. If it was a successful
    mutate_record insert, performs a confirmation read and appends
    a system-style confirmation message so the agent's next response
    is grounded in verified reality, not just the tool's claim.
    """
    messages = state["messages"]

    if not messages:
        return {"messages": []}

    last_message = messages[-1]

    # Only act on actual tool result messages
    if not isinstance(last_message, ToolMessage):
        return {"messages": []}

    # Only verify mutate_record calls — other tools are read-only
    # and don't need this check
    if last_message.name != "mutate_record":
        return {"messages": []}

    try:
        result = json.loads(last_message.content)
    except (json.JSONDecodeError, TypeError):
        return {"messages": []}

    # Only verify successful inserts — updates/deletes already return
    # modified_count/deleted_count which is self-verifying
    if result.get("status") != "success" or "inserted_id" not in result:
        return {"messages": []}

    inserted_id  = result["inserted_id"]
    verification = _confirm_document_exists(inserted_id)

    # Inject a verification result as a new tool-style message so the
    # agent's next reasoning step sees PROOF, not just a claim
    verification_message = ToolMessage(
        content = json.dumps(verification),
        name    = "verify_insertion",
        tool_call_id = f"verify_{inserted_id}",
    )

    return {"messages": [verification_message]}


def _confirm_document_exists(inserted_id: str) -> dict:
    """
    Searches across all writable collections for the inserted_id.
    Returns whether the document was actually found in the database.
    """
    WRITABLE_COLLECTIONS = [
        "users", "activities", "announcements", "registrations",
        "agent_scheduled_jobs", "agent_subscriptions", "agent_memory",
        "agent_report_jobs",
    ]

    try:
        oid = ObjectId(inserted_id)
    except Exception:
        return {
            "verified": False,
            "reason"  : "inserted_id was not a valid ObjectId — cannot verify."
        }

    for collection_name in WRITABLE_COLLECTIONS:
        doc = db[collection_name].find_one({"_id": oid})
        if doc:
            return {
                "verified"  : True,
                "collection": collection_name,
                "message"   : (
                    f"Confirmed: document {inserted_id} exists in "
                    f"'{collection_name}'. You may now tell the user "
                    f"the operation succeeded."
                )
            }

    return {
        "verified": False,
        "reason"  : (
            f"Document {inserted_id} was NOT found in any collection. "
            f"Do NOT tell the user the operation succeeded. "
            f"Inform them something went wrong and offer to retry."
        )
    }