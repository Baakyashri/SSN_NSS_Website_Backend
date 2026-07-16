"""
routes/report_job_routes.py
-----------------------------
REST endpoints for the frontend to track and download agent-generated reports.

  GET  /reports/jobs            — list all jobs for the requesting user
  GET  /reports/jobs/<job_id>  — poll a specific job status
  GET  /reports/jobs/<job_id>/download — stream the completed PDF file

Authentication: JWT required on all endpoints.
Admins see all jobs; volunteers only see jobs they requested.
"""

import os
from flask import Blueprint, jsonify, request, send_file, abort
from flask_jwt_extended import jwt_required, get_jwt

from bson import ObjectId
from db import db

report_jobs_bp = Blueprint("report_jobs", __name__)

GENERATED_REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads", "generated_reports"
)


def _serialize_job(job: dict) -> dict:
    """Convert ObjectId / datetime fields to strings for JSON."""
    return {
        "job_id":          str(job["_id"]),
        "scope":           job.get("params", {}).get("scope", ""),
        "params":          {k: str(v) if isinstance(v, ObjectId) else v
                            for k, v in job.get("params", {}).items()},
        "status":          job.get("status", ""),
        "error_reason":    job.get("error_reason"),
        "output_file_url": job.get("output_file_url"),
        "created_at":      job["created_at"].isoformat() if job.get("created_at") else None,
        "updated_at":      job["updated_at"].isoformat() if job.get("updated_at") else None,
        "requested_by":    job.get("user_email", ""),
    }


# ─────────────────────────────────────────────────────────────
# GET /reports/jobs
# ─────────────────────────────────────────────────────────────

@report_jobs_bp.route("/jobs", methods=["GET"])
@jwt_required()
def list_report_jobs():
    """
    List report jobs.
    Admin: all jobs (newest first, limit 50).
    Volunteer: only jobs they requested (by user_id from JWT).
    """
    claims  = get_jwt()
    role    = claims.get("role", "volunteer")
    user_id = claims.get("user_id", "")

    query = {}
    if role != "admin":
        query["user_id"] = user_id

    jobs = list(
        db.agent_report_jobs
        .find(query)
        .sort("created_at", -1)
        .limit(50)
    )
    return jsonify([_serialize_job(j) for j in jobs]), 200


# ─────────────────────────────────────────────────────────────
# GET /reports/jobs/<job_id>
# ─────────────────────────────────────────────────────────────

@report_jobs_bp.route("/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_report_job(job_id):
    """
    Poll a specific job's status.
    Returns status, and output_file_url once completed.
    """
    claims  = get_jwt()
    role    = claims.get("role", "volunteer")
    user_id = claims.get("user_id", "")

    try:
        oid = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id"}), 400

    job = db.agent_report_jobs.find_one({"_id": oid})
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Access check: volunteers can only see their own jobs
    if role != "admin" and job.get("user_id") != user_id:
        return jsonify({"error": "Access denied"}), 403

    return jsonify(_serialize_job(job)), 200


# ─────────────────────────────────────────────────────────────
# GET /reports/jobs/<job_id>/download
# ─────────────────────────────────────────────────────────────

@report_jobs_bp.route("/jobs/<job_id>/download", methods=["GET"])
@jwt_required()
def download_report_job(job_id):
    """
    Stream the completed report PDF for download.
    Only works when job status is 'completed'.
    """
    claims  = get_jwt()
    role    = claims.get("role", "volunteer")
    user_id = claims.get("user_id", "")

    try:
        oid = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id"}), 400

    job = db.agent_report_jobs.find_one({"_id": oid})
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if role != "admin" and job.get("user_id") != user_id:
        return jsonify({"error": "Access denied"}), 403

    if job.get("status") != "completed":
        return jsonify({
            "error": f"Report not ready yet. Current status: {job.get('status')}",
            "status": job.get("status"),
        }), 202

    file_url = job.get("output_file_url", "")
    filename  = f"report_{job_id}.pdf"
    file_path = os.path.join(GENERATED_REPORTS_DIR, filename)

    if not os.path.isfile(file_path):
        return jsonify({"error": "Report file not found on server."}), 404

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
