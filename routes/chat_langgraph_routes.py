"""
routes/chat_langgraph_routes.py
--------------------------------
Fresh LangGraph chat route — replaces the old LangChain route entirely.

Changes from the old route:
    1. Calls chatbot_langraph.chat_with_ai() instead of chatbot_langchain
    2. Decodes JWT to extract user_id and user_email — passed to the agent
       so tools can personalise responses and write audit logs correctly
    3. Accepts a single "message" string (what user typed) instead of
       a full messages list — the graph manages conversation history itself
    4. Returns {"response": "..."} — same shape as before, frontend unchanged

Register in app.py:
    from routes.chat_langgraph_routes import chat_langgraph_bp
    app.register_blueprint(chat_langgraph_bp, url_prefix="/api/agent")

Endpoint:
    POST /api/agent/chat
    Headers : Authorization: Bearer <jwt_token>
    Body    : { "message": "Which upcoming activities suit me?" }
    Response: { "response": "Here are the activities..." }
"""
"""
routes/chat_langgraph_routes.py
--------------------------------
Updated _decode_jwt to match flask_jwt_extended's JWT payload shape.

flask_jwt_extended sets:
    "sub"     → the identity you passed (email in your case)
    "role"    → from additional_claims
    "user_id" → from additional_claims
    "email"   → from additional_claims
"""

import os

from flask import Blueprint, request, jsonify
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException

from agent.chatbot_langgraph import chat_with_ai

chat_langgraph_bp = Blueprint("chat_langgraph", __name__)


def _decode_jwt(auth_header: str) -> dict | None:
    """
    Decode flask_jwt_extended token from Authorization header.
    Returns dict with user_id, user_email, role — or None if invalid.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]

    try:
        # flask_jwt_extended's decode_token handles secret + algorithm
        # automatically — reads from your app's JWT config
        payload = decode_token(token)

        return {
            # "sub" is where flask_jwt_extended stores identity (email)
            "user_email": payload.get("sub", ""),
            "user_id"   : payload.get("user_id", ""),
            "role"      : payload.get("role", "volunteer"),
            "session_id": str(payload.get("iat", "")),  # ← login timestamp
        }

    except JWTExtendedException:
        return None
    except Exception:
        return None


@chat_langgraph_bp.route("/chat", methods=["POST"])
def chat():

    # ── 1. Auth ───────────────────────────────────────────────
    user = _decode_jwt(request.headers.get("Authorization", ""))

    if not user:
        return jsonify({"error": "Unauthorised — valid JWT required."}), 401

    # ── 2. Parse body ─────────────────────────────────────────
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "message field is required."}), 400

    # ── 3. Call LangGraph agent ───────────────────────────────
    try:
        response = chat_with_ai(
            message    = message,
            user_id    = user["user_id"],
            user_email = user["user_email"],
            role       = user["role"],
            session_id = user["session_id"], 
        )

        return jsonify({"response": response}), 200

    except Exception as exc:
        print("LANGGRAPH CHAT ERROR:", exc)
        return jsonify({"error": str(exc)}), 500