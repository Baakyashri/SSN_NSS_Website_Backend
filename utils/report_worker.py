"""
utils/report_worker.py
-----------------------
Background worker that processes agent_report_jobs.

Pipeline per job:
  1. Mark job "processing"
  2. Fetch structured stats via MongoDB aggregation
  3. Retrieve narrative chunks via Atlas Vector Search
  4. Check chunk count — decide narrative vs stats-only mode
  5. Call LLM (via llm_factory) to synthesise narrative sections
  6. Generate matplotlib charts in memory
  7. Compile PDF with reportlab
  8. Save PDF, update job "completed", notify user by email
  9. Feed synthesised narrative back into agent_activity_embeddings

Rate-limiting:  a configurable inter-job sleep prevents quota bursting
                when processing a backlog of auto-triggered jobs.
"""

import io
import logging
import os
import time
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")          # non-interactive backend, safe in threads
import matplotlib.pyplot as plt

from bson import ObjectId
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, HRFlowable,
)

from agent.llm_factory import get_llm, switch_model
from db import db
from utils.ingestion import (
    extract_activity_metadata,
    index_generated_report_narrative,
    get_embeddings,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

GENERATED_REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads", "generated_reports"
)
os.makedirs(GENERATED_REPORTS_DIR, exist_ok=True)

NARRATIVE_MIN_CHUNKS = 2   # below this → stats-only report + disclaimer
INTER_JOB_SLEEP_SEC  = 5   # pause between consecutive LLM calls to respect rate limits


# ─────────────────────────────────────────────────────────────
# EMAIL HELPER  (reuses same SMTP credentials as scheduler.py)
# ─────────────────────────────────────────────────────────────

def _send_completion_email(to_email: str, job_id: str, file_url: str, scope_desc: str):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender  = os.getenv("GMAIL_SENDER_EMAIL")
    app_pwd = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not app_pwd:
        logger.warning("Gmail credentials missing — completion email not sent.")
        return

    subject = f"[NSS Portal] Your report is ready: {scope_desc}"
    body = (
        f"Hi,\n\n"
        f"Your requested NSS report has been generated.\n\n"
        f"Report  : {scope_desc}\n"
        f"Download: {file_url}\n"
        f"Job ID  : {job_id}\n\n"
        f"You can also download it from the Reports section of the portal.\n\n"
        f"— NSS AI Agent"
    )
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_pwd)
            server.sendmail(sender, to_email, msg.as_string())
        logger.info(f"Completion email sent → {to_email}")
    except Exception as exc:
        logger.error(f"Completion email failed → {to_email}: {exc}")


# ─────────────────────────────────────────────────────────────
# LLM HELPER — single call with retry on rate-limit
# ─────────────────────────────────────────────────────────────

def _llm_invoke(prompt: str) -> str:
    """Invoke the LLM with automatic model switching on quota errors."""
    for attempt in range(len([]) + 10):   # up to 10 model switches
        try:
            llm, info = get_llm()
            response  = llm.invoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            err = str(exc).lower()
            if any(k in err for k in ("quota", "rate", "limit", "429", "exhausted")):
                logger.warning(f"LLM quota hit ({info['model']}), switching model…")
                try:
                    switch_model()
                    time.sleep(2)
                except Exception:
                    raise RuntimeError("All LLM models exhausted. Cannot generate report.")
            else:
                raise


# ─────────────────────────────────────────────────────────────
# STATS COLLECTORS
# ─────────────────────────────────────────────────────────────

def _collect_single_activity_stats(activity_id: str) -> dict:
    """Fetch one activity's details and registration summary."""
    try:
        oid  = ObjectId(activity_id)
        act  = db.activities.find_one({"_id": oid})
        if not act:
            return {}

        reg_count = db.registrations.count_documents({"activity_id": activity_id})
        # attendance_status may be "present" or status may be "attended" (schema variation)
        attended = db.registrations.count_documents({
            "activity_id": activity_id,
            "$or": [{"attendance_status": "present"}, {"status": "attended"}]
        })

        return {
            "title":            act.get("title", ""),
            "description":      act.get("description", ""),
            "date":             str(act.get("date", "")),
            "location":         act.get("location", "N/A"),
            "status":           act.get("status", ""),
            "category":         act.get("category", ""),
            "attendance_hours": act.get("attendance_hours", 0),
            "no_of_volunteers": act.get("no_of_volunteers", 0),
            "registered":       reg_count,
            "attended":         attended,
            "total_hours_generated": attended * _safe_float(act.get("attendance_hours", 0)),
        }
    except Exception as e:
        logger.error(f"_collect_single_activity_stats error: {e}")
        return {}


def _collect_annual_stats(year: int) -> dict:
    """Aggregate activity and participation stats for a full year."""
    try:
        year_filter = {"$expr": {"$eq": [{"$year": "$date"}, year]}}

        # Handle date stored as string OR datetime
        pipeline_activities = [
            {"$addFields": {
                "date_parsed": {
                    "$cond": {
                        "if":   {"$eq": [{"$type": "$date"}, "string"]},
                        "then": {"$dateFromString": {"dateString": "$date", "onError": None}},
                        "else": "$date"
                    }
                }
            }},
            {"$match": {"$expr": {"$eq": [{"$year": "$date_parsed"}, year]}}},
            {"$group": {
                "_id":         None,
                "total_activities":       {"$sum": 1},
                "total_volunteer_slots":  {"$sum": {"$toInt": {"$ifNull": ["$no_of_volunteers", 0]}}},
                "total_hours_offered":    {"$sum": {"$toDouble": {"$ifNull": ["$attendance_hours", 0]}}},
            }}
        ]
        agg = list(db.activities.aggregate(pipeline_activities))
        stats = agg[0] if agg else {}

        # Category breakdown
        cat_pipeline = [
            {"$addFields": {
                "date_parsed": {
                    "$cond": {
                        "if":   {"$eq": [{"$type": "$date"}, "string"]},
                        "then": {"$dateFromString": {"dateString": "$date", "onError": None}},
                        "else": "$date"
                    }
                }
            }},
            {"$match": {"$expr": {"$eq": [{"$year": "$date_parsed"}, year]}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        categories = list(db.activities.aggregate(cat_pipeline))

        # Monthly activity counts
        monthly_pipeline = [
            {"$addFields": {
                "date_parsed": {
                    "$cond": {
                        "if":   {"$eq": [{"$type": "$date"}, "string"]},
                        "then": {"$dateFromString": {"dateString": "$date", "onError": None}},
                        "else": "$date"
                    }
                }
            }},
            {"$match": {"$expr": {"$eq": [{"$year": "$date_parsed"}, year]}}},
            {"$group": {
                "_id":   {"$month": "$date_parsed"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}},
        ]
        monthly = list(db.activities.aggregate(monthly_pipeline))

        return {
            "year":              year,
            "total_activities":  stats.get("total_activities", 0),
            "total_volunteer_slots": stats.get("total_volunteer_slots", 0),
            "total_hours_offered": stats.get("total_hours_offered", 0),
            "categories":        categories,
            "monthly_breakdown": monthly,
        }
    except Exception as e:
        logger.error(f"_collect_annual_stats error: {e}")
        return {"year": year, "error": str(e)}


def _collect_monthly_stats(year: int, month: int) -> dict:
    """Aggregate stats for a specific month."""
    try:
        pipeline = [
            {"$addFields": {
                "date_parsed": {
                    "$cond": {
                        "if":   {"$eq": [{"$type": "$date"}, "string"]},
                        "then": {"$dateFromString": {"dateString": "$date", "onError": None}},
                        "else": "$date"
                    }
                }
            }},
            {"$match": {"$and": [
                {"$expr": {"$eq": [{"$year":  "$date_parsed"}, year]}},
                {"$expr": {"$eq": [{"$month": "$date_parsed"}, month]}},
            ]}},
        ]
        activities = list(db.activities.aggregate(pipeline))
        total_hours = sum(_safe_float(a.get("attendance_hours", 0)) for a in activities)
        total_vols  = sum(int(float(a.get("no_of_volunteers") or 0)) for a in activities)

        return {
            "year":             year,
            "month":            month,
            "total_activities": len(activities),
            "total_volunteer_slots": total_vols,
            "total_hours_offered":   total_hours,
            "activities":       [
                {
                    "title":    a.get("title", ""),
                    "date":     str(a.get("date", "")),
                    "hours":    a.get("attendance_hours", 0),
                    "category": a.get("category", ""),
                }
                for a in activities
            ],
        }
    except Exception as e:
        logger.error(f"_collect_monthly_stats error: {e}")
        return {"year": year, "month": month, "error": str(e)}


def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0


# ─────────────────────────────────────────────────────────────
# VECTOR RETRIEVAL
# ─────────────────────────────────────────────────────────────

def _retrieve_narrative_chunks(pre_filter: dict, top_k: int = 8, query: str = "") -> list:
    """
    Run Atlas Vector Search against agent_activity_embeddings.
    Falls back to a simple text match if the vector index isn't set up yet.
    Returns list of {text, source, title} dicts.
    """
    try:
        query_text = query or "highlights achievements volunteers outcomes"
        query_vec  = get_embeddings([query_text])[0]

        pipeline = [
            {
                "$vectorSearch": {
                    "index":         "agent_embeddings_index",
                    "path":          "embedding",
                    "queryVector":   query_vec,
                    "numCandidates": top_k * 10,
                    "limit":         top_k,
                    **({"filter": pre_filter} if pre_filter else {}),
                }
            },
            {
                "$project": {
                    "text":    1,
                    "source":  1,
                    "title":   1,
                    "score":   {"$meta": "vectorSearchScore"},
                }
            }
        ]
        return list(db.agent_activity_embeddings.aggregate(pipeline))

    except Exception as e:
        logger.warning(f"Vector search failed ({e}), falling back to simple filter.")
        # Fallback: return most-recent chunks matching the filter
        docs = list(
            db.agent_activity_embeddings
            .find(pre_filter, {"text": 1, "source": 1, "title": 1})
            .sort("ingested_at", -1)
            .limit(top_k)
        )
        return docs


# ─────────────────────────────────────────────────────────────
# CHART GENERATORS  — return BytesIO PNG buffers
# ─────────────────────────────────────────────────────────────

def _chart_monthly_activities(monthly_breakdown: list) -> io.BytesIO:
    """Bar chart: number of activities per month."""
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]
    counts = [0] * 12
    for item in monthly_breakdown:
        m = item.get("_id", 0)
        if 1 <= m <= 12:
            counts[m - 1] = item.get("count", 0)

    fig, ax = plt.subplots(figsize=(8, 3.5))
    bars = ax.bar(MONTHS, counts, color="#1a73e8", edgecolor="white")
    ax.set_title("Activities per Month", fontsize=12, pad=10)
    ax.set_ylabel("Count")
    ax.set_ylim(0, max(counts or [1]) + 1)
    for bar, cnt in zip(bars, counts):
        if cnt:
            ax.text(bar.get_x() + bar.get_width() / 2, cnt + 0.1,
                    str(cnt), ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_category_breakdown(categories: list) -> io.BytesIO:
    """Pie chart: activity distribution by category."""
    labels = [c.get("_id") or "Uncategorised" for c in categories]
    sizes  = [c.get("count", 0) for c in categories]
    if not sizes or sum(sizes) == 0:
        sizes, labels = [1], ["No data"]

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.pie(sizes, labels=labels, autopct="%1.0f%%",
           startangle=140, pctdistance=0.8,
           colors=plt.cm.Set3.colors[:len(labels)])
    ax.set_title("Activity Category Distribution", fontsize=11)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────
# PDF COMPILER
# ─────────────────────────────────────────────────────────────

def _build_pdf(job_id: str, scope_desc: str, stats: dict,
               narrative_sections: dict, charts: list,
               has_narrative: bool) -> str:
    """
    Compile a PDF from stats + narrative + charts using ReportLab.
    Returns the local file path.
    """
    filename  = f"report_{job_id}.pdf"
    file_path = os.path.join(GENERATED_REPORTS_DIR, filename)

    doc   = SimpleDocTemplate(file_path, pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    # Custom styles
    h1    = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16,
                           spaceAfter=6, textColor=colors.HexColor("#1a73e8"))
    h2    = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                           spaceAfter=4, textColor=colors.HexColor("#333333"))
    body  = ParagraphStyle("body", parent=styles["Normal"], fontSize=10,
                           leading=14, spaceAfter=6)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.grey, spaceAfter=4)

    story = []

    # Title
    story.append(Paragraph("NSS Portal — Generated Report", h1))
    story.append(Paragraph(scope_desc, h2))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d %B %Y at %H:%M IST')}",
        small
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    story.append(Spacer(1, 0.4*cm))

    # ── Structured stats table ─────────────────────────────
    story.append(Paragraph("Key Statistics", h2))
    stat_rows = [["Metric", "Value"]]
    STAT_LABELS = {
        "total_activities":       "Total Activities",
        "total_volunteer_slots":  "Volunteer Slots",
        "total_hours_offered":    "Hours Offered",
        "registered":             "Registered",
        "attended":               "Attended",
        "total_hours_generated":  "Hours Generated",
        "attendance_hours":       "Attendance Hours",
        "no_of_volunteers":       "Volunteer Slots",
    }
    for key, label in STAT_LABELS.items():
        if key in stats and stats[key] not in (None, "", 0):
            stat_rows.append([label, str(stats[key])])

    if len(stat_rows) > 1:
        tbl = Table(stat_rows, colWidths=[9*cm, 7*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#f8f9fa"), colors.white]),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Charts ────────────────────────────────────────────
    for chart_buf, chart_label in charts:
        story.append(Paragraph(chart_label, h2))
        img = Image(chart_buf, width=16*cm, height=7*cm)
        story.append(img)
        story.append(Spacer(1, 0.4*cm))

    # ── Narrative / qualitative sections ──────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    story.append(Spacer(1, 0.3*cm))

    if has_narrative:
        story.append(Paragraph("Qualitative Summary", h2))
        for section_title, section_text in narrative_sections.items():
            story.append(Paragraph(section_title, h2))
            for para in (section_text or "").split("\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(), body))
            story.append(Spacer(1, 0.3*cm))
    else:
        story.append(Paragraph("Narrative Data Unavailable", h2))
        story.append(Paragraph(
            "No uploaded report files or agent-generated narratives were found for this "
            "scope. The structured statistics above are derived directly from the database. "
            "Once activity reports are uploaded or auto-generated for this period, a full "
            "qualitative summary will be included in future reports.",
            body
        ))

    # Footer note
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#eeeeee")))
    story.append(Paragraph(
        "This report was auto-generated by the NSS Portal AI Agent. "
        "Narrative sections are synthesised from uploaded report files "
        "and prior agent-generated summaries.",
        small
    ))

    doc.build(story)
    return file_path


# ─────────────────────────────────────────────────────────────
# SCOPE DESCRIPTION HELPER
# ─────────────────────────────────────────────────────────────

def _scope_desc(params: dict) -> str:
    MONTHS = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    scope = params.get("scope", "")
    year  = params.get("year")
    month = params.get("month")
    cat   = params.get("category", "")
    act_id = params.get("activity_id", "")
    cy    = params.get("comparison_year")

    if scope == "annual":
        return f"Annual Report — {year}"
    if scope == "monthly":
        m_name = MONTHS[month] if month and 1 <= month <= 12 else str(month)
        return f"Monthly Report — {m_name} {year}"
    if scope == "single_activity":
        act = db.activities.find_one({"_id": ObjectId(act_id)}) if act_id else None
        title = act.get("title", act_id) if act else act_id
        return f"Activity Report — {title}"
    if scope == "category":
        return f"Category Report — {cat}" + (f" ({year})" if year else "")
    if scope == "comparison":
        return f"Year-over-Year Comparison — {year} vs {cy}"
    return f"Report — {scope}"


# ─────────────────────────────────────────────────────────────
# MAIN WORKER ENTRY POINT
# ─────────────────────────────────────────────────────────────

def process_report_job(job: dict):
    """
    Process a single pending report job end-to-end.
    Called by the scheduler; never raises — all errors are caught
    and written back to agent_report_jobs.
    """
    job_id      = str(job["_id"])
    params      = job.get("params", {})
    user_email  = job.get("user_email", "")
    is_system   = job.get("user_id") == "system"

    logger.info(f"Processing report job {job_id} — scope: {params.get('scope')}")

    # Mark processing
    db.agent_report_jobs.update_one(
        {"_id": job["_id"]},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}}
    )

    try:
        scope = (params.get("scope") or "").strip().lower()

        # ── 1. Collect structured stats ──────────────────────
        stats  = {}
        charts = []
        activity_id_for_rag = params.get("activity_id", "")
        rag_pre_filter: dict = {}

        if scope == "single_activity":
            act_id = params.get("activity_id", "")
            stats  = _collect_single_activity_stats(act_id)
            rag_pre_filter = {"activity_id": ObjectId(act_id)} if act_id else {}

        elif scope == "annual":
            year  = params.get("year")
            stats = _collect_annual_stats(year)
            rag_pre_filter = {"year": year}
            # Charts
            if stats.get("monthly_breakdown"):
                charts.append((_chart_monthly_activities(stats["monthly_breakdown"]),
                                "Activities per Month"))
            if stats.get("categories"):
                charts.append((_chart_category_breakdown(stats["categories"]),
                                "Category Breakdown"))

        elif scope == "monthly":
            year  = params.get("year")
            month = params.get("month")
            stats = _collect_monthly_stats(year, month)
            rag_pre_filter = {"year": year, "month": month}

        elif scope == "category":
            year = params.get("year")
            cat  = params.get("category", "")
            rag_pre_filter = {"category": cat}
            if year:
                rag_pre_filter["year"] = year
            # Build basic stats from query
            pipeline = [{"$match": {"category": cat} if not year
                         else {"category": cat, "year": year}}]
            activities = list(db.agent_activity_embeddings.aggregate(pipeline))
            stats = {"category": cat, "year": year,
                     "chunk_count": len(activities)}

        elif scope == "comparison":
            year  = params.get("year")
            year2 = params.get("comparison_year")
            stats_y1 = _collect_annual_stats(year)
            stats_y2 = _collect_annual_stats(year2)
            stats = {"year": year, "comparison_year": year2,
                     "year1": stats_y1, "year2": stats_y2}
            rag_pre_filter = {"year": {"$in": [year, year2]}}

        # ── 2. Retrieve narrative chunks ─────────────────────
        query_hint = f"{params.get('scope', '')} {params.get('category', '')} {params.get('year', '')} highlights achievements"
        chunks = _retrieve_narrative_chunks(rag_pre_filter, top_k=10, query=query_hint)
        chunk_count = len(chunks)
        has_narrative = chunk_count >= NARRATIVE_MIN_CHUNKS

        logger.info(f"Job {job_id}: retrieved {chunk_count} narrative chunks "
                    f"(has_narrative={has_narrative})")

        # ── 3. LLM narrative synthesis ───────────────────────
        narrative_sections: dict = {}
        full_narrative_text = ""

        if has_narrative:
            excerpts = "\n\n".join(
                f"[{c.get('title', 'Activity')} — {c.get('source', '')}]\n{c.get('text', '')}"
                for c in chunks
            )
            scope_desc_str = _scope_desc(params)

            # Executive summary
            summary_prompt = (
                f"You are an NSS (National Service Scheme) report writer. "
                f"Based on the following report excerpts from NSS activities, "
                f"write a concise executive summary (3-4 paragraphs) for a "
                f"'{scope_desc_str}'. Focus on volunteer achievements, community "
                f"impact, and key highlights. Do not fabricate specific numbers "
                f"not present in the excerpts.\n\n"
                f"EXCERPTS:\n{excerpts}\n\nEXECUTIVE SUMMARY:"
            )
            executive_summary = _llm_invoke(summary_prompt)
            narrative_sections["Executive Summary"] = executive_summary
            full_narrative_text += executive_summary + "\n\n"
            time.sleep(INTER_JOB_SLEEP_SEC)   # quota courtesy pause

            # Key highlights
            highlights_prompt = (
                f"From the same NSS activity report excerpts below, extract 4-6 "
                f"notable highlights or achievements as a structured list. Each "
                f"highlight should be a complete sentence grounded in the excerpts.\n\n"
                f"EXCERPTS:\n{excerpts}\n\nKEY HIGHLIGHTS:"
            )
            highlights = _llm_invoke(highlights_prompt)
            narrative_sections["Key Highlights"] = highlights
            full_narrative_text += highlights + "\n\n"
            time.sleep(INTER_JOB_SLEEP_SEC)

            # Recommendations (for annual/comparison only)
            if scope in ("annual", "comparison"):
                recs_prompt = (
                    f"Based on the NSS activity summaries below, suggest 3-5 "
                    f"actionable recommendations to improve future volunteer "
                    f"programmes. Be specific and grounded in the excerpts.\n\n"
                    f"EXCERPTS:\n{excerpts}\n\nRECOMMENDATIONS:"
                )
                recs = _llm_invoke(recs_prompt)
                narrative_sections["Recommendations"] = recs
                full_narrative_text += recs + "\n\n"
                time.sleep(INTER_JOB_SLEEP_SEC)

        else:
            logger.info(
                f"Job {job_id}: insufficient narrative chunks ({chunk_count} < "
                f"{NARRATIVE_MIN_CHUNKS}); generating stats-only report."
            )

        # ── 4. Build PDF ──────────────────────────────────────
        scope_desc_str = _scope_desc(params)
        file_path = _build_pdf(
            job_id, scope_desc_str, stats,
            narrative_sections, charts, has_narrative
        )
        file_url = f"/uploads/generated_reports/report_{job_id}.pdf"

        # ── 5. Update job as completed ────────────────────────
        db.agent_report_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {
                "status":          "completed",
                "output_file_url": file_url,
                "updated_at":      datetime.now(timezone.utc),
            }}
        )
        logger.info(f"Job {job_id} completed → {file_url}")

        # ── 6. Notify user (not for system-triggered jobs) ───
        if not is_system and user_email and user_email != "system@nss-portal.internal":
            _send_completion_email(user_email, job_id, file_url, scope_desc_str)

        # ── 7. Feed narrative back into RAG ──────────────────
        if full_narrative_text.strip():
            act_id = params.get("activity_id", "")
            if act_id:
                act_doc = db.activities.find_one({"_id": ObjectId(act_id)})
                if act_doc:
                    meta = extract_activity_metadata(act_doc)
                    index_generated_report_narrative(
                        act_id, meta, full_narrative_text, file_url
                    )
                    logger.info(f"Job {job_id}: narrative fed back into RAG.")

    except Exception as exc:
        logger.exception(f"Report job {job_id} failed: {exc}")
        db.agent_report_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {
                "status":       "failed",
                "error_reason": str(exc),
                "updated_at":   datetime.now(timezone.utc),
            }}
        )
