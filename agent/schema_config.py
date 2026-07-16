"""
agent/schema_config.py
------------------------
Single source of truth for fields that should be AUTO-COMPUTED rather
than asked from the user or guessed by the LLM.

Why this file exists:
    The LLM should never be trusted to calculate deterministic values
    (like "what day of week was 2025-01-21") — that's a job for code.
    This registry lets mutate_record enrich any collection's payload
    generically, without hardcoded if-checks per collection.

How to extend:
    1. Write a small function that takes the payload dict and returns
       the computed value.
    2. Register it under the right collection in COMPUTED_FIELDS.
    That's it — no changes needed anywhere else.
"""

from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# COMPUTE FUNCTIONS
# Each function takes the full payload dict and returns one value.
# ═══════════════════════════════════════════════════════════════

def compute_day_of_week(payload: dict):
    """
    Derives day_of_week list from the 'date' field.
    Returns [] if date is missing or unparseable — never raises.
    """
    date_val = payload.get("date")

    if not date_val:
        return []

    try:
        if isinstance(date_val, str):
            parsed = datetime.fromisoformat(date_val)
        elif isinstance(date_val, datetime):
            parsed = date_val
        else:
            return []

        return [parsed.strftime("%A").lower()]

    except (ValueError, TypeError):
        return []


def compute_registered_count(payload: dict):
    """New activities always start with zero registrations."""
    return 0


def compute_attendance_status_default(payload: dict):
    """New registrations always start as pending until marked present/absent."""
    return "pending"


# ═══════════════════════════════════════════════════════════════
# COMPUTED FIELDS REGISTRY
#
# Structure:
#   collection_name → { field_name : compute_function }
#
# A field is only auto-computed if it is missing or empty in the
# payload the LLM provided. If the LLM (or admin) explicitly gave
# a value, that value is respected and NOT overwritten.
# ═══════════════════════════════════════════════════════════════

COMPUTED_FIELDS = {

    "activities": {
        "day_of_week"     : compute_day_of_week,
        "registered_count": compute_registered_count,
    },

    "registrations": {
        "attendance_status": compute_attendance_status_default,
    },

    # Add future collections here as new derived-field needs arise.
    # Example:
    # "users": {
    #     "age": compute_age_from_dob,
    # },
}


# ═══════════════════════════════════════════════════════════════
# GENERIC ENRICHMENT FUNCTION
# Called from mutate_record — works for ANY collection automatically.
# ═══════════════════════════════════════════════════════════════

def enrich_payload(collection: str, payload: dict) -> dict:
    """
    Auto-fill computed fields for the given collection.
    Never overwrites a value the user/LLM already explicitly provided.

    Args:
        collection : Name of the target collection.
        payload    : The document being inserted.

    Returns:
        The enriched payload dict.
    """
    computed_fields = COMPUTED_FIELDS.get(collection, {})

    for field_name, compute_fn in computed_fields.items():
        existing_value = payload.get(field_name)

        # Only compute if missing, None, empty string, or empty list
        is_empty = existing_value in (None, "", [], {})

        if is_empty:
            payload[field_name] = compute_fn(payload)

    return payload