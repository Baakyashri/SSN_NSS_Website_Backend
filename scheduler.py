"""
scheduler.py
------------
Runs as a background thread inside your existing Flask server.
Handles two jobs every minute:
    1. Fire due reminders from agent_scheduled_jobs
    2. Check new activity subscriptions (called externally on activity post)

HOW TO START:
    Import and call start_scheduler() once when your Flask app boots.

    In your app.py / main Flask file:

        from scheduler import start_scheduler
        start_scheduler()

    That's it. No separate process needed.

EMAIL SETUP (one-time):
    Add to your .env file:
        GMAIL_SENDER_EMAIL=your_nss_email@gmail.com
        GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

    Generate App Password at:
        myaccount.google.com → Security → 2-Step Verification → App Passwords
    Do NOT use your Gmail login password here.

DEPLOYMENT ON RENDER:
    Render free tier spins down after 15 min inactivity.
    Use Render Starter plan ($7/month) OR set up cron-job.org as a backup ping:
        URL  : https://your-render-app.onrender.com/internal/ping
        Every: 10 minutes
    This keeps the server alive and APScheduler running continuously.
"""

import logging
import os
import smtplib

from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db import db   

logger    = logging.getLogger(__name__)
_scheduler = None   # module-level singleton


# ─────────────────────────────────────────────────────────────
# EMAIL HELPER
# ─────────────────────────────────────────────────────────────

def _send_email(to_email: str, subject: str, message: str) -> bool:
    sender  = os.getenv("GMAIL_SENDER_EMAIL")
    app_pwd = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not app_pwd:
        logger.error("Gmail credentials missing in .env")
        return False

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = to_email
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_pwd)
            server.sendmail(sender, to_email, msg.as_string())

        logger.info(f"Reminder sent → {to_email}")
        return True

    except Exception as exc:
        logger.error(f"Email failed → {to_email} : {exc}")
        return False


# ─────────────────────────────────────────────────────────────
# JOB 1 — Fire due reminders
# Runs every 1 minute via APScheduler
# ─────────────────────────────────────────────────────────────

def check_and_send_reminders():
    """
    Find all unsent reminder jobs whose trigger_at <= now and send them.
    Marks each job sent=True immediately to prevent duplicate sends.
    """
    now = datetime.now(timezone.utc)

    try:
        due_jobs = list(db.agent_scheduled_jobs.find({
            "trigger_at": {"$lte": now},
            "sent"       : False,
            "job_type"   : "reminder",
        }))

        if not due_jobs:
            return

        logger.info(f"Scheduler: {len(due_jobs)} reminder(s) due")

        for job in due_jobs:
            # Mark sent FIRST — prevents re-send if email takes time
            db.agent_scheduled_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"sent": True, "sent_at": now}}
            )
            _send_email(job["user_email"], job["subject"], job["message"])

    except Exception as exc:
        logger.error(f"check_and_send_reminders error: {exc}")


# ─────────────────────────────────────────────────────────────
# JOB 2 — Check subscriptions on new activity post
# Called directly from your create_activity Flask route
# NOT a scheduled job — triggered by admin action
# ─────────────────────────────────────────────────────────────

def notify_subscribed_users(new_activity: dict):
    """
    Called from your existing create_activity API endpoint after
    a new activity is saved to MongoDB.

    Checks every active subscription and notifies users whose
    trigger_condition matches the new activity.

    Usage in your activity creation route:
        from scheduler import notify_subscribed_users

        @app.route("/api/activities", methods=["POST"])
        def create_activity():
            # ... your existing save logic ...
            activity_doc = { ...saved doc... }
            notify_subscribed_users(activity_doc)   # add this line
            return jsonify({"message": "Activity created"}), 201

    Args:
        new_activity: The activity document just saved to MongoDB.
    """
    try:
        active_subs = list(db.agent_subscriptions.find({"active": True}))

        if not active_subs:
            return

        for sub in active_subs:
            condition = sub.get("trigger_condition", {})

            if _activity_matches(new_activity, condition):
                subject = f"[NSS] New activity: {new_activity.get('title', '')}"
                message = (
                    f"Hi,\n\n"
                    f"A new NSS activity matching your interests has been posted!\n\n"
                    f"Title    : {new_activity.get('title')}\n"
                    f"Date     : {new_activity.get('date')}\n"
                    f"Location : {new_activity.get('location', 'TBD')}\n"
                    f"Hours    : {new_activity.get('attendance_hours', 'N/A')}\n\n"
                    f"Log in to the NSS portal to register.\n\n"
                    f"— NSS SSN Agent"
                )
                _send_email(sub["user_email"], subject, message)
                logger.info(f"Subscription match notified → {sub['user_email']}")

    except Exception as exc:
        logger.error(f"notify_subscribed_users error: {exc}")


def _activity_matches(activity: dict, condition: dict) -> bool:
    """
    Check whether a new activity satisfies a subscription condition.
    Supports exact match and MongoDB-style operators: $in, $gte, $lte, $ne.
    """
    for field, expected in condition.items():
        actual = activity.get(field)

        if isinstance(expected, dict):
            op  = list(expected.keys())[0]
            val = list(expected.values())[0]

            if op == "$in"  and actual not in val:
                return False
            if op == "$gte" and (actual is None or actual < val):
                return False
            if op == "$lte" and (actual is None or actual > val):
                return False
            if op == "$ne"  and actual == val:
                return False
        else:
            if actual != expected:
                return False

    return True

# ─────────────────────────────────────────────────────────────
# JOB 3 — Process ONE pending report job per cycle
# Runs every 60 seconds via APScheduler.
# Processes jobs serially (one per tick) to avoid LLM quota bursting
# when a backlog of auto-triggered jobs builds up.
# ─────────────────────────────────────────────────────────────

def check_and_process_report_jobs():
    """
    Pick the oldest pending report job and process it synchronously.
    One job per scheduler tick — deliberate serial design to prevent
    concurrent LLM calls exhausting free-tier Groq/Gemini quota.
    """
    try:
        job = db.agent_report_jobs.find_one(
            {"status": "pending"},
            sort=[("created_at", 1)]   # oldest first
        )
        if not job:
            return

        logger.info(f"Scheduler: picking up report job {job['_id']}")
        from utils.report_worker import process_report_job
        process_report_job(job)

    except Exception as exc:
        logger.error(f"check_and_process_report_jobs error: {exc}")


# ─────────────────────────────────────────────────────────────
# START SCHEDULER — call once at Flask app boot
# ─────────────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running — skipped.")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        func    = check_and_send_reminders,
        trigger = IntervalTrigger(minutes=1),
        id      = "reminder_check",
        name    = "Check and send due reminders",
        replace_existing=True,
    )
    _scheduler.add_job(
        func    = check_and_process_report_jobs,
        trigger = IntervalTrigger(seconds=60),
        id      = "report_job_check",
        name    = "Process pending report jobs (one per tick)",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "APScheduler started — reminders every 1 min, "
        "report jobs every 60 s (serial, one per tick)."
    )