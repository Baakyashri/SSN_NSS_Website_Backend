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
from utils.validation import validate_email, validate_password, sanitize_input, validate_required_fields



# Load your credentials from environment variables or config file
EMAIL_ADDRESS = os.environ.get("GMAIL_USER")  # Your Gmail address
EMAIL_PASSWORD = os.environ.get("GMAIL_PASS")  # Your Gmail app password

auth_bp = Blueprint('auth', __name__)
if db is not None:
    users_col = db['users']
else:
    users_col = None  # Handle the case where db is not available
@auth_bp.route('/check-user', methods=['GET'])
def check_user():
    email = request.args.get('email')
    if not email:
        return jsonify(msg="Email not provided"), 400

    user = users_col.find_one({'email': email})
    if not user:
        return jsonify(msg="User not found"), 404

    return jsonify(role=user['role'], vertical=user.get('vertical', '')), 200

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify(msg="Invalid request data"), 400
        
        email = data.get('email')
        password = data.get('password')
        vertical = data.get('vertical')

        # Validate email format
        is_valid_email, email_error = validate_email(email)
        if not is_valid_email:
            return jsonify(msg=email_error), 400

        # Validate password
        is_valid_password, password_error = validate_password(password)
        if not is_valid_password:
            return jsonify(msg=password_error), 400

        # Sanitize inputs
        email = sanitize_input(email, 254)
        vertical = sanitize_input(vertical, 50) if vertical else None

        user = users_col.find_one({'email': email})
        if not user or not check_password_hash(user['password'], password):
            return jsonify(msg="Invalid credentials"), 401
    except Exception as e:
        return jsonify(msg="Server error during login"), 500

    if user['role'] == 'admin':
        dashboard = '/admin-dashboard'
    elif user['role'] == 'verticalhead':
        if not vertical or user.get('vertical', '').lower() != vertical.lower():
            return jsonify(msg=f"Invalid vertical. You belong to {user.get('vertical')}"), 403
        
        # Map vertical names to route paths
        vertical_routes = {
            'photography': '/vertical-dashboard/photography',
            'events': '/vertical-dashboard/events',
            'social': '/vertical-dashboard/social',
            # add other verticals here
        }

        dashboard = vertical_routes.get(user.get('vertical').lower())
        if not dashboard:
            return jsonify(msg="No dashboard configured for your vertical"), 403
    else:
        return jsonify(msg="You are not authorized to login"), 403

    token = create_access_token(identity=email, additional_claims={"role": user['role'], "vertical": user.get('vertical', '')})

    return jsonify(
        access_token=token,
        role=user['role'],
        vertical=user.get('vertical', ''),
        dashboard=dashboard
    ), 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    user = users_col.find_one({'email': email})
    if not user:
        return jsonify(msg="User not found"), 404

    reset_token = str(uuid.uuid4())  # generate a unique reset token
    users_col.update_one({'email': email}, {'$set': {'reset_token': reset_token}})

    reset_link  = f"http://localhost:3000/reset-password/{reset_token}"


    # 🔑 Call the email function
    send_reset_email(email, reset_link)

    return jsonify(msg="Password reset link sent to your email"), 200


#  Reset password route (optional, if you want to allow actual password change)
@auth_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    data = request.get_json()
    new_password = data.get('password')

    user = users_col.find_one({'reset_token': token})
    if not user:
        return jsonify(msg="Invalid or expired token"), 400

    users_col.update_one({'reset_token': token}, {
        '$set': {'password': generate_password_hash(new_password)},
        '$unset': {'reset_token': ""}
    })

    return jsonify(msg="Password updated successfully"), 200



def send_reset_email(to_email, reset_link):
    sender_email = EMAIL_ADDRESS
    sender_password = EMAIL_PASSWORD  
    subject = "Password Reset Request"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject

    body = f"Click this link to reset your password: {reset_link}"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
