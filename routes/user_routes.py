from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import Config
import utils.validation as val 


users_col = db['users']
user_bp = Blueprint('user', __name__)

# Helper function to check admin role
def admin_required(f):
    from functools import wraps
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        claims = get_jwt()
        print("JWT Claims:", claims)
        if claims.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function



# ------------------------ User APIs ------------------------

@user_bp.route('/add-user', methods=['POST'])
@admin_required
def add_user():
    data = request.get_json()
    email = val.sanitize_input(data.get('email'), 254)
    password = data.get('password')  # Don't sanitize passwords
    role = val.sanitize_input(data.get('role'), 50)

    # Required fields
    valid, error = val.validate_required_fields(data,['email', 'password', 'role'])
    if not valid:
        return jsonify(msg=error), 400

    # Email validation
    valid, error = val.validate_email(email)
    if not valid:
        return jsonify(msg=error), 400

    # Password validation
    valid, error = val.validate_password(password)
    if not valid:
        return jsonify(msg=error), 400

    # Existing user check
    if users_col.find_one({'email': email}):
        return jsonify(msg="User already exists"), 400

    hashed_pw = generate_password_hash(password)

    user_doc = {
        'email': email,
        'password': hashed_pw,
        'role': role
    }

    users_col.insert_one(user_doc)

    return jsonify(msg=f"User {email} added successfully"), 201


@user_bp.route('/update-user', methods=['PUT'])
@admin_required
def update_user():
    data = request.get_json()
    existing_email = val.sanitize_input(data.get('existingEmail'),254)
    new_email = data.get('newEmail')
    new_password = data.get('newPassword')
    new_role = data.get('newRole')

    # Existing email is required
    if not existing_email:
        return jsonify(msg="Existing email is required"), 400

    user = users_col.find_one({'email': existing_email})
    if not user:
        return jsonify(msg="User not found"), 404

    update_data = {}

    # Update email
    if new_email:
        new_email = val.sanitize_input(new_email,254)
        valid, error = val.validate_email(new_email)
        if not valid:
            return jsonify(msg=error), 400
        existing_user = users_col.find_one({'email': new_email})
        if existing_user and new_email != existing_email:
            return jsonify(msg="Email already exists"), 400
        update_data['email'] = new_email

    # Update password
    if new_password:
        valid, error = val.validate_password(new_password)
        if not valid:
            return jsonify(msg=error), 400
        update_data['password'] = (generate_password_hash(new_password))

    # Update role
    if new_role:
        new_role = val.sanitize_input(new_role,50)
        update_data['role'] = new_role

    # Nothing to update
    if not update_data:
        return jsonify(msg="No fields provided to update"), 400

    users_col.update_one({'email': existing_email},{'$set': update_data})

    return jsonify(msg="User updated successfully"), 200

@user_bp.route('/delete-user', methods=['DELETE'])
@admin_required
def delete_user():
    data = request.get_json()
    email = val.sanitize_input(data.get('email'),254)

    if not email:
        return jsonify(msg="Email is required"), 400
    valid, error = val.validate_email(email)
    if not valid:
        return jsonify(msg=error), 400

    result = users_col.delete_one({'email': email})

    if result.deleted_count == 0:
        return jsonify(msg="User not found"), 404

    return jsonify(msg="User deleted successfully"), 200


@user_bp.route('/get-users', methods=['GET'])
@admin_required
def get_users():
    users = list(users_col.find({}, {'password': 0}))  # hide password
    for user in users:
        user['_id'] = str(user['_id'])
    return jsonify(users), 200
