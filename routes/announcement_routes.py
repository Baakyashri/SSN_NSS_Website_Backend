from flask import Blueprint, request, jsonify
from datetime import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models.mongo import announcements_collection
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import Config


announcements_bp = Blueprint("announcements", __name__)


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



# ------------------------ Announcement APIs ------------------------

@announcements_bp.route('/add-announcement', methods=['POST'])
@admin_required
def add_announcement():
    data = request.json
    name = data.get('ActivityName')
    text = data.get('ActivityDescription')
    expire_at_str = data.get('expireAt')
    
    announcement_doc = {
        'activityName': name, 
        'activityDescription': text
    }
    
    if expire_at_str:
        try:
            # Parse YYYY-MM-DD from HTML date input
            announcement_doc['expireAt'] = datetime.strptime(expire_at_str, '%Y-%m-%d')
        except ValueError:
            pass # Ignore invalid date format
            
    announcements_collection.insert_one(announcement_doc)
    return jsonify({"message": "Announcement added"}), 201


@announcements_bp.route('/update-announcement', methods=['PUT'])
@admin_required
def update_announcement():
    data = request.json
    old_name = data.get('oldName')
    new_name = data.get('newName')
    new_text = data.get('newText')

    result = announcements_collection.update_one(
        {'activityName': old_name},
        {'$set': {'activityName': new_name, 'activityDescription': new_text}}
    )
    if result.modified_count:
        return jsonify({"message": "Announcement updated"}), 200
    else:
        return jsonify({"error": "No announcement updated. Check name."}), 404


@announcements_bp.route('/delete-announcement', methods=['DELETE'])
@admin_required
def delete_announcement():
    data = request.json
    name = data.get('Activity')

    result = announcements_collection.delete_one({'activityName': name})
    if result.deleted_count:
        return jsonify({"message": "Announcement deleted"}), 200
    else:
        return jsonify({"error": "No announcement deleted. Check name."}), 404


@announcements_bp.route('/get-announcements', methods=['GET'])
def get_announcements():
    anns = list(announcements_collection.find())
    for ann in anns:
        ann['_id'] = str(ann['_id'])
    return jsonify(anns), 200


