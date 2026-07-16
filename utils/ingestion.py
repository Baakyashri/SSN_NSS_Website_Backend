import os
import re
import io
import logging
import hashlib
import requests
from datetime import datetime, timezone
from bson import ObjectId

from pypdf import PdfReader
from docx import Document

from db import db

logger = logging.getLogger(__name__)

# Cache fastembed model and failure state
_fastembed_model = None
_fastembed_failed = False

# ─────────────────────────────────────────────────────────────
# 1. PII SCRUBBER
# ─────────────────────────────────────────────────────────────

def scrub_pii(text: str) -> str:
    """
    Redacts sensitive user data:
    - Emails (standard pattern)
    - 10-digit phone numbers (optionally starting with +91 or 91)
    - 11-13 digit roll numbers (format-agnostic digits with optional spaces/hyphens)
    """
    if not text:
        return text

    # 1. Emails
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    text = re.sub(email_pattern, "[EMAIL_REDACTED]", text)

    # 2. Phone Numbers: 10 digits starting with [6-9]
    # Allow optional +91 or 91 country code and optional separators
    phone_pattern = r'\b(?:\+91[\s-]?)?[6-9]\d{9}\b'
    text = re.sub(phone_pattern, "[PHONE_REDACTED]", text)

    # 3. Roll Numbers: 11 to 13 digits separated by optional spaces or hyphens.
    # Excludes 10-digit phone numbers to prevent overlap/double redaction.
    # e.g., "3122 23 5001 025" or "123456789012"
    roll_pattern = r'\b\d(?:[\s-]*\d){10,12}\b'
    text = re.sub(roll_pattern, "[ROLL_REDACTED]", text)

    return text

# ─────────────────────────────────────────────────────────────
# 2. TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────

def _extract_text_pdf(file_bytes: bytes) -> str:
    """Extract all text pages from PDF bytes."""
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def _extract_text_docx(file_bytes: bytes) -> str:
    """Extract all text paragraphs from DOCX bytes."""
    doc = Document(io.BytesIO(file_bytes))
    text = ""
    for para in doc.paragraphs:
        if para.text:
            text += para.text + "\n"
    return text

def extract_text(file_bytes: bytes, filename: str) -> str:
    """Dispatches text extraction based on file extension."""
    ext = filename.split(".")[-1].lower()
    if ext == "pdf":
        return _extract_text_pdf(file_bytes)
    elif ext in ("docx", "doc"):
        # Note: python-docx only supports docx. .doc files will raise an error
        # but we handle it gracefully.
        if ext == "doc":
            logger.warning(f"Legacy .doc format '{filename}' cannot be parsed by python-docx. Suggest converting to .docx.")
            return ""
        return _extract_text_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

# ─────────────────────────────────────────────────────────────
# 3. CHUNKING UTILITY
# ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
    """
    Split text into chunks of maximum `chunk_size` characters with `overlap`.
    Aligns boundaries to newlines or sentence endings if possible.
    """
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:].strip())
            break

        # Look for a paragraph boundary or sentence boundary near the target end
        boundary = -1
        for sep in ('\n', '. ', ' '):
            pos = text.rfind(sep, start + chunk_size - 120, end)
            if pos != -1:
                boundary = pos + len(sep)
                break

        if boundary != -1:
            end = boundary

        chunks.append(text[start:end].strip())
        start = end - overlap

        # Safety catch for infinite loop
        if start >= end:
            start = end

    return chunks

# ─────────────────────────────────────────────────────────────
# 4. EMBEDDING ENGINE
# ─────────────────────────────────────────────────────────────

def get_embeddings(chunks: list) -> list:
    """
    Generates embedding vectors for a list of text chunks.
    First tries local fastembed, falling back to Gemini text-embedding-004.
    """
    global _fastembed_model, _fastembed_failed

    if not chunks:
        return []

    # 1. Try local fastembed
    if not _fastembed_failed:
        try:
            if _fastembed_model is None:
                logger.info("Initializing local fastembed embedding model...")
                from fastembed import TextEmbedding
                # Default is "BAAI/bge-small-en-v1.5" (384 dimensions)
                _fastembed_model = TextEmbedding()

            embeddings = [[float(val) for val in e] for e in _fastembed_model.embed(chunks)]
            logger.info(f"Generated {len(embeddings)} embeddings using local fastembed.")
            return embeddings
        except Exception as e:
            logger.warning(f"fastembed initialization/execution failed. Falling back to Gemini: {e}")
            _fastembed_failed = True

    # 2. Fallback to Gemini API
    logger.info("Generating embeddings using Gemini text-embedding-004 API fallback...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Embedding fallback unavailable.")

    import google.generativeai as genai
    genai.configure(api_key=api_key)

    response = genai.embed_content(
        model="models/text-embedding-004",
        content=chunks,
        task_type="retrieval_document"
    )

    if 'embeddings' not in response:
        raise RuntimeError("Failed to retrieve embeddings from Gemini API response.")

    embeddings = response['embeddings']
    logger.info(f"Generated {len(embeddings)} embeddings using Gemini API.")
    return embeddings

# ─────────────────────────────────────────────────────────────
# 5. INGESTION PIPELINE
# ─────────────────────────────────────────────────────────────

def _get_report_file_bytes(report: dict) -> bytes:
    """Download or read report file contents depending on storage type."""
    storage = report.get("storage")
    url = report.get("url", "")

    if not storage:
        storage = "cloudinary" if url.startswith("http") else "local"

    if storage == "local":
        filename = report.get("filename") or url.split("/")[-1]
        from config import Config
        local_path = os.path.join(Config.UPLOAD_FOLDER, "reports", filename)
        with open(local_path, "rb") as f:
            return f.read()

    elif storage == "cloudinary":
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content

    else:
        raise ValueError(f"Unknown storage type: {storage}")

def ingest_report(activity_id: str, report: dict, activity_metadata: dict) -> bool:
    """
    Download/read a single report, extract text, scrub PII, chunk,
    generate embeddings, and upsert to agent_activity_embeddings collection.
    """
    try:
        url = report.get("url")
        filename = report.get("original_name") or report.get("filename") or url.split("/")[-1]
        logger.info(f"Starting ingestion for report '{filename}' (Activity ID: {activity_id})")

        # 1. Get raw file bytes
        file_bytes = _get_report_file_bytes(report)

        # 2. Extract raw text
        raw_text = extract_text(file_bytes, filename)
        if not raw_text.strip():
            logger.warning(f"No text extracted from report '{filename}'. Ingestion skipped.")
            return False

        # 3. Scrub PII
        scrubbed_text = scrub_pii(raw_text)

        # 4. Chunk text
        chunks = chunk_text(scrubbed_text)
        if not chunks:
            logger.info("Scrubbed text yielded zero chunks. Ingestion skipped.")
            return False

        # 5. Generate embeddings
        embeddings = get_embeddings(chunks)

        # 6. Prepare documents
        embedded_docs = []
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            doc = {
                "activity_id": ObjectId(activity_id),
                "title": activity_metadata.get("title", ""),
                "year": activity_metadata.get("year"),
                "month": activity_metadata.get("month"),
                "category": activity_metadata.get("category", ""),
                "chunk_index": i,
                "text": chunk,
                "embedding": vector,
                "report_url": url,
                "source": "manual_upload",
                "ingested_at": datetime.now(timezone.utc)
            }
            embedded_docs.append(doc)

        # 7. Upsert to DB
        # Remove any existing embeddings for this specific report URL to prevent duplicates on update
        db.agent_activity_embeddings.delete_many({"report_url": url})

        if embedded_docs:
            db.agent_activity_embeddings.insert_many(embedded_docs)
            logger.info(f"Ingested report '{filename}': saved {len(embedded_docs)} chunks to database.")
            return True

        return False

    except Exception as e:
        logger.exception(f"Error during ingestion of report '{report.get('url')}': {e}")
        return False


def extract_activity_metadata(activity_doc: dict) -> dict:
    """Safely extracts title, category, year, and month from activity document."""
    title = activity_doc.get("title", "")
    category = activity_doc.get("category", "")
    date_val = activity_doc.get("date")

    year = None
    month = None
    if date_val:
        try:
            if isinstance(date_val, str):
                # Handle ISO format string or YYYY-MM-DD
                parsed = datetime.fromisoformat(date_val.strip())
            elif isinstance(date_val, datetime):
                parsed = date_val
            else:
                parsed = None

            if parsed:
                year = parsed.year
                month = parsed.month
        except Exception:
            # Fallback for manual YYYY-MM-DD split
            try:
                parts = str(date_val).strip().split("-")
                if len(parts) >= 2:
                    year = int(parts[0])
                    month = int(parts[1])
            except Exception:
                pass

    return {
        "title": title,
        "category": category,
        "year": year,
        "month": month
    }


def run_ingestion_in_background(activity_id: str, reports: list, activity_metadata: dict):
    """Fires a background thread to ingest reports without blocking Flask thread."""
    import threading

    def worker():
        try:
            for report in reports:
                if report and report.get("url"):
                    ingest_report(activity_id, report, activity_metadata)
        except Exception as e:
            logger.error(f"Error in background ingestion worker: {e}")

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


# ─────────────────────────────────────────────────────────────
# 6. AUTO-TRIGGER HELPERS
# ─────────────────────────────────────────────────────────────

def is_activity_finalized(activity: dict) -> bool:
    """
    Returns True if an activity's core outcome data is present and
    indicates the event actually happened:
      - description is non-empty
      - attendance_hours is a positive number (not 0 / '' / None)
      - no_of_volunteers is a positive integer
    Deliberately lenient about date — we do not reject future-dated
    activities that were pre-populated with real volunteer data.
    """
    desc = (activity.get("description") or "").strip()
    if not desc:
        return False

    try:
        hours = float(activity.get("attendance_hours") or 0)
        if hours <= 0:
            return False
    except (ValueError, TypeError):
        return False

    try:
        vols = int(float(activity.get("no_of_volunteers") or 0))
        if vols <= 0:
            return False
    except (ValueError, TypeError):
        return False

    return True


def compute_activity_hash(activity: dict) -> str:
    """
    Deterministic SHA-256 hash of core activity fields.
    A changed hash means the admin edited material data → re-generate.
    """
    parts = "|".join([
        activity.get("title", ""),
        activity.get("description", ""),
        str(activity.get("date", "")),
        str(activity.get("attendance_hours", "")),
        str(activity.get("no_of_volunteers", "")),
        activity.get("category", ""),
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def check_and_enqueue_auto_report(activity_id: str, activity_data: dict):
    """
    System-triggered helper called on every activity save.
    Enqueues a 'single_activity' report job when:
      - The activity is finalized (has real outcome data)
      - Either no prior job exists, OR the activity content has
        materially changed since the last job was queued.
    No role check — this is system-initiated, not a user tool call.
    """
    if not is_activity_finalized(activity_data):
        logger.debug(f"Activity {activity_id} not finalized; skipping auto-report trigger.")
        return

    content_hash = compute_activity_hash(activity_data)

    # Find the most recent single_activity job for this activity
    latest_job = db.agent_report_jobs.find_one(
        {"params.activity_id": activity_id, "params.scope": "single_activity"},
        sort=[("created_at", -1)]
    )

    if latest_job:
        status = latest_job.get("status", "")
        # Already queued or running — don't duplicate
        if status in ("pending", "processing"):
            logger.info(
                f"Auto-report: job already {status} for activity {activity_id}, skipping."
            )
            return

        # Completed/failed but content unchanged — skip to avoid unnecessary LLM spend
        last_hash = latest_job.get("params", {}).get("activity_hash", "")
        if last_hash == content_hash:
            logger.info(
                f"Auto-report: content unchanged for activity {activity_id}, skipping re-queue."
            )
            return

        logger.info(
            f"Auto-report: activity {activity_id} content changed — re-enqueuing."
        )
    else:
        logger.info(
            f"Auto-report: new finalized activity {activity_id} — enqueuing report job."
        )

    job_doc = {
        "user_id": "system",
        "user_email": "system@nss-portal.internal",
        "status": "pending",
        "params": {
            "scope": "single_activity",
            "activity_id": activity_id,
            "activity_hash": content_hash,
        },
        "output_file_url": None,
        "error_reason": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    db.agent_report_jobs.insert_one(job_doc)
    logger.info(f"Auto-report job enqueued for activity {activity_id}.")


# ─────────────────────────────────────────────────────────────
# 7. EMBEDDING-FEEDBACK — INDEX AGENT-GENERATED NARRATIVE
# ─────────────────────────────────────────────────────────────

def index_generated_report_narrative(
    activity_id: str,
    activity_metadata: dict,
    narrative_text: str,
    report_url: str,
) -> bool:
    """
    Called by the report worker after PDF compilation.
    Chunks, embeds, and indexes the LLM-synthesized narrative text
    into agent_activity_embeddings under source='agent_generated'.

    This ensures activities without a manually uploaded report still
    contribute qualitative content to future RAG retrievals.
    Manual-upload embeddings are left untouched — both can coexist
    for the same activity.
    """
    try:
        if not narrative_text or not narrative_text.strip():
            logger.warning("index_generated_report_narrative: empty narrative, skipping.")
            return False

        # Defensive PII scrub on generated text (LLM should not include PII,
        # but this is a safety net in case structured data leaked into the prompt)
        scrubbed = scrub_pii(narrative_text)

        chunks = chunk_text(scrubbed)
        if not chunks:
            return False

        embeddings = get_embeddings(chunks)

        embedded_docs = []
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            embedded_docs.append({
                "activity_id": ObjectId(activity_id),
                "title": activity_metadata.get("title", ""),
                "year": activity_metadata.get("year"),
                "month": activity_metadata.get("month"),
                "category": activity_metadata.get("category", ""),
                "chunk_index": i,
                "text": chunk,
                "embedding": vector,
                "report_url": report_url,
                "source": "agent_generated",
                "ingested_at": datetime.now(timezone.utc),
            })

        # Remove only prior agent_generated embeddings for this activity
        # (leave manual_upload embeddings untouched)
        db.agent_activity_embeddings.delete_many({
            "activity_id": ObjectId(activity_id),
            "source": "agent_generated",
        })

        if embedded_docs:
            db.agent_activity_embeddings.insert_many(embedded_docs)
            logger.info(
                f"Indexed {len(embedded_docs)} agent-generated chunks "
                f"for activity {activity_id}."
            )
            return True

        return False

    except Exception as e:
        logger.exception(
            f"index_generated_report_narrative failed for activity {activity_id}: {e}"
        )
        return False
