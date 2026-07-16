"""
routes/auth_routes.py
----------------------
Single /login endpoint handles both admin and volunteer login.

Admin    → redirects to /admin-dashboard
Volunteer → redirects to /home  (frontend uses this to route correctly)

JWT payload shape (flask_jwt_extended):
    identity = email                  ← access via get_jwt_identity()
    additional_claims = {
        "role"      : "admin" | "volunteer",
        "user_id"   : str(user["_id"]),
        "email"     : email            ← redundant with identity but
    }                                    makes it easy for agent route
                                         to extract without a DB call

In chat_langgraph_routes.py _decode_jwt():
    payload.get("sub")       → gives email  (flask_jwt_extended sets identity as "sub")
    payload.get("user_id")   → gives mongo _id as string
    payload.get("email")     → gives email
    payload.get("role")      → gives role
"""

import os
import sys
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db
from utils.validation import validate_email, sanitize_input, validate_password

EMAIL_ADDRESS = os.environ.get("GMAIL_SENDER_EMAIL")
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

auth_bp = Blueprint("auth", __name__)

if db is not None:
    users_col = db["users"]
else:
    users_col = None


# ─────────────────────────────────────────────────────────────
# LOGIN — handles admin and volunteer in one endpoint
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify(msg="Invalid request data"), 400

        email    = sanitize_input(data.get("email"), 254)
        password = data.get("password")

        if not password:
            return jsonify(msg="Password is required"), 400

        valid, error = validate_email(email)
        if not valid:
            return jsonify(msg=error), 400

        user = users_col.find_one({"email": email})

        if not user or not check_password_hash(user["password"], password):
            return jsonify(msg="Invalid credentials"), 401

        role = user.get("role", "volunteer")

        # ── Build JWT with user context ───────────────────────
        # user_id and email are included as additional claims so
        # the agent route can extract them without a DB lookup.
        token = create_access_token(
            identity=email,
            additional_claims={
                "role"   : role,
                "user_id": str(user["_id"]),
                "email"  : email,
            },
        )

        # ── Route admin vs volunteer ──────────────────────────
        if role == "admin":
            return jsonify(
                access_token = token,
                dashboard    = "/admin-dashboard",
                role         = role,
            ), 200

        else:
            # volunteer, coordinator, or any other non-admin role
            return jsonify(
                access_token = token,
                dashboard    = "/",
                role         = role,
                name         = user.get("name", ""),
            ), 200

    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify(msg="Server error during login"), 500