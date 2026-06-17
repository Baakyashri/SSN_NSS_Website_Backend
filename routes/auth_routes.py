from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash,generate_password_hash
from db import db
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.validation import validate_email, validate_password, sanitize_input


# Load your credentials from environment variables or config file
EMAIL_ADDRESS = os.environ.get("GMAIL_USER")  # Your Gmail address
EMAIL_PASSWORD = os.environ.get("GMAIL_PASS")  # Your Gmail app password

auth_bp = Blueprint('auth', __name__)
if db is not None:
    users_col = db['users']
else:
    users_col = None  # Handle the case where db is not available



@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify(msg="Invalid request data"), 400

        email = sanitize_input(data.get('email'),254)
        password = data.get('password')

        if not password:
            return jsonify(msg="Password is required"), 400
        valid, error = validate_email(email)
        if not valid:
            return jsonify(msg=error), 400

        user = users_col.find_one({'email': email})

        if not user or not check_password_hash(user['password'],password):
            return jsonify(msg="Invalid credentials"), 401
        if user['role'] != 'admin':
            return jsonify(msg="You are not authorized to login"), 403

        token = create_access_token(identity=email,additional_claims={"role": user["role"]})

        return jsonify(access_token=token,dashboard='/admin-dashboard'), 200

    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify(msg="Server error during login"), 500

