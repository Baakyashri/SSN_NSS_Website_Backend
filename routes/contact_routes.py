from flask import Blueprint, request, jsonify
import smtplib
from email.message import EmailMessage
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.validation import validate_contact_data, sanitize_input

contact_bp = Blueprint('contact', __name__)

# Load your credentials from environment variables or config file
EMAIL_ADDRESS = os.environ.get("GMAIL_USER")  # Your Gmail address
EMAIL_PASSWORD = os.environ.get("GMAIL_PASS")  # Your Gmail app password

#debug print
#print("EMAIL:", EMAIL_ADDRESS)
#print("PASS:", EMAIL_PASSWORD)


@contact_bp.route('/contact', methods=['POST'])
def send_contact_message():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight request success'}), 200

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400

        # Validate contact data
        is_valid, error = validate_contact_data(data)
        if not is_valid:
            return jsonify({'error': error}), 400

        # Sanitize inputs
        name = sanitize_input(data['name'], 100)
        email = sanitize_input(data['email'], 254)
        message_content = sanitize_input(data['message'], 2000)

        # Check if email credentials are configured
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            return jsonify({'error': 'Email service not configured'}), 500

        msg = EmailMessage()
        msg['Subject'] = 'New Contact Form Submission'
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = EMAIL_ADDRESS  # You can change this to the tech team's email
        msg.set_content(f"From: {name} <{email}>\n\nMessage:\n{message_content}")

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        return jsonify({'success': 'Message sent successfully!'}), 200
    except smtplib.SMTPException as e:
        return jsonify({'error': 'Failed to send email. Please try again later.'}), 500
    except Exception as e:
        return jsonify({'error': 'Server error. Please try again later.'}), 500
