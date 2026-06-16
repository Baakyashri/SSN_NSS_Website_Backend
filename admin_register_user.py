from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import UPLOAD_FOLDER
import os
import re
import json

admin_bp = Blueprint('admin', __name__)
users_col = db['users']
announcements_col = db['announcements']
highlight_collection = db['highlights']  # or whatever your MongoDB collection name is

def convert_objectid_to_str(obj):
    """Convert ObjectId to string for JSON serialization"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    return obj
activities_col = db['activities']

# Helper function to check admin role
def admin_required(f):
    from functools import wraps
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ------------------------ User APIs ------------------------

@admin_bp.route('/add-user', methods=['POST'])
@admin_required
def add_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    vertical = data.get('vertical') if role == 'verticalhead' else None

    if not email or not password or not role:
        return jsonify({"success": False, "message": "Missing required fields."}), 400

    if role == 'verticalhead' and not vertical:
        return jsonify({"success": False, "message": "Vertical name is required for vertical head."}), 400

    if users_col.find_one({'email': email}):
        return jsonify({"error": "User already exists"}), 400

    hashed_pw = generate_password_hash(password)

    # Build user object
    user_doc = {
        'email': email,
        'password': hashed_pw,
        'role': role
    }

    if vertical:
        user_doc['vertical'] = vertical

    users_col.insert_one(user_doc)
    return jsonify({"message": f"User {email} added"}), 201


@admin_bp.route('/update-user', methods=['PUT'])
@admin_required
def update_user():
    data = request.json
    existing_email = data.get('existingEmail')
    new_email = data.get('newEmail')
    new_password = data.get('newPassword')
    new_role = data.get('newRole')
    new_vertical = data.get('newVertical')

    user = users_col.find_one({'email': existing_email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    update_data = {}
    if new_email:
        update_data['email'] = new_email
    if new_password:
        update_data['password'] = generate_password_hash(new_password)
    if new_role:
        update_data['role'] = new_role
        # If new role is verticalhead, vertical name must be provided
        if new_role == 'verticalhead':
            if not new_vertical:
                return jsonify({"error": "Vertical name is required for vertical head."}), 400
            update_data['vertical'] = new_vertical
        else:
            # Remove vertical field if the user is no longer a vertical head
            update_data['vertical'] = None


    users_col.update_one({'email': existing_email}, {'$set': update_data})
    return jsonify({"message": "User updated"}), 200


@admin_bp.route('/delete-user', methods=['DELETE'])
@admin_required
def delete_user():
    data = request.json
    email = data.get('email')

    result = users_col.delete_one({'email': email})
    if result.deleted_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "User deleted"}), 200


@admin_bp.route('/get-users', methods=['GET'])
@admin_required
def get_users():
    users = list(users_col.find({}, {'password': 0}))  # hide password
    for user in users:
        user['_id'] = str(user['_id'])
    return jsonify(users), 200

# ------------------------ Announcement APIs ------------------------

@admin_bp.route('/add-announcement', methods=['POST'])
@admin_required
def add_announcement():
    data = request.json
    name = data.get('ActivityName')
    text = data.get('ActivityDescription')
    announcements_col.insert_one({'activityName': name, 'activityDescription': text})
    return jsonify({"message": "Announcement added"}), 201


@admin_bp.route('/update-announcement', methods=['PUT'])
@admin_required
def update_announcement():
    data = request.json
    old_name = data.get('oldName')
    new_name = data.get('newName')
    new_text = data.get('newText')

    result = announcements_col.update_one(
        {'activityName': old_name},
        {'$set': {'activityName': new_name, 'activityDescription': new_text}}
    )
    if result.modified_count:
        return jsonify({"message": "Announcement updated"}), 200
    else:
        return jsonify({"error": "No announcement updated. Check name."}), 404


@admin_bp.route('/delete-announcement', methods=['DELETE'])
@admin_required
def delete_announcement():
    data = request.json
    name = data.get('Activity')

    result = announcements_col.delete_one({'activityName': name})
    if result.deleted_count:
        return jsonify({"message": "Announcement deleted"}), 200
    else:
        return jsonify({"error": "No announcement deleted. Check name."}), 404


@admin_bp.route('/get-announcements', methods=['GET'])
@admin_required
def get_announcements():
    anns = list(announcements_col.find())
    for ann in anns:
        ann['_id'] = str(ann['_id'])
    return jsonify(anns), 200



#-------------------------Highlights/Trending-------------------------------
@admin_bp.route('/get-trending', methods=['GET'])
def get_highlights():
    highlights = list(highlight_collection.find())
    for h in highlights:
        h['_id'] = str(h['_id'])  # Convert ObjectId to string
    return jsonify(highlights)

@admin_bp.route('/add-trending', methods=['POST'])
@admin_required
def add_highlight():
    data = request.get_json()
    title= data.get('title')
    description = data.get('description')
    highlight_collection.insert_one({'title':title,'description':description})
    return jsonify({"message": "Highlight added"}), 200

@admin_bp.route('/update-trending', methods=['PUT'])
@admin_required
def update_highlight():
    data = request.get_json()
    name = data.get('oldTitle')
    Title = data.get('newTitle')
    desc = data.get('newDescription')
    # Try exact match first
    result = highlight_collection.update_one({"title": name}, {"$set":{'title' : Title , 'description' : desc}})
    # Fallback to case-insensitive exact (ignoring casing/whitespace differences)
    if result.modified_count == 0 and name:
        ci_query = {"title": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}}
        result = highlight_collection.update_one(ci_query, {"$set":{'title' : Title , 'description' : desc}})
    if result.modified_count:
        return jsonify({"message": "Highlight updated"}), 200
    else:
        return jsonify({"error": "No highlight updated. Check old title ."}), 404


@admin_bp.route('/delete-trending', methods=['DELETE'])
@admin_required
def delete_highlight():
    data = request.json
    # Support deletion by Mongo _id if provided
    highlight_id = data.get('id')
    if highlight_id:
        try:
            result = highlight_collection.delete_one({"_id": ObjectId(highlight_id)})
            if result.deleted_count:
                return jsonify({"message": "Highlight deleted"}), 200
            else:
                return jsonify({"error": "No highlight deleted. Check id."}), 404
        except Exception:
            return jsonify({"error": "Invalid id format"}), 400

    name = data.get('title')
    # Try exact match first
    result = highlight_collection.delete_one({"title": name})
    # Fallback to case-insensitive exact match
    if result.deleted_count == 0 and name:
        ci_query = {"title": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}}
        result = highlight_collection.delete_one(ci_query)
    if result.deleted_count:
        return jsonify({"message": "Highlight deleted"}), 200
    else:
        return jsonify({"error": "No highlight deleted. Check title ."}), 404

# Direct deletion by id (explicit endpoint)
@admin_bp.route('/delete-trending-by-id', methods=['DELETE'])
@admin_required
def delete_highlight_by_id():
    data = request.json or {}
    highlight_id = data.get('id')
    if not highlight_id:
        return jsonify({"error": "id is required"}), 400
    try:
        result = highlight_collection.delete_one({"_id": ObjectId(highlight_id)})
        if result.deleted_count:
            return jsonify({"message": "Highlight deleted"}), 200
        else:
            return jsonify({"error": "No highlight deleted. Check id."}), 404
    except Exception:
        return jsonify({"error": "Invalid id format"}), 400
    

# ------------------------ Activity APIs ------------------------
@admin_bp.route('/add-activity', methods=['POST'])
@admin_required
def add_activity():
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['title', 'description', 'date']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"error": f"{field} is required"}), 400

    # Prepare activity data for database
    activity_data = {
        "title": data['title'],
        "description": data['description'],
        "date": data['date'],
        "photos": data.get('photos', []),
        "reports": data.get('reports', []),
        "location": data.get('location', 'SSN Campus'),
        "status": data.get('status', 'upcoming')
    }

    # Insert into database
    result = activities_col.insert_one(activity_data)
    
    if result.inserted_id:
        # Convert ObjectId to string for JSON serialization
        safe_activity_data = convert_objectid_to_str(activity_data)
        return jsonify({
            "message": "Activity added successfully",
            "activity_id": str(result.inserted_id),
            "activity": safe_activity_data
        }), 201
    else:
        return jsonify({"error": "Failed to add activity"}), 500

@admin_bp.route('/get-photos', methods=['GET'])
def get_photos():
    try:
        photos = []
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    photos.append({
                        "name": filename,
                        "url": request.host_url.rstrip('/') + '/uploads/' + filename
                    })
        return jsonify(photos)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/get-gallery', methods=['GET'])
def get_gallery():
    photos = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            photos.append({
                'name': filename,
                'url': f"http://localhost:5000/uploads/{filename}"
            })
    return jsonify(photos)

@admin_bp.route('/update-activity', methods=['PUT'])
@admin_required
def update_activity():
    data = request.json

    # Support both title-based and id-based updates, prefer title-based to match frontend
    old_title = data.get("oldTitle")
    update_data = {}
    if data.get("newTitle"): update_data["title"] = data["newTitle"]
    if data.get("newDescription"): update_data["description"] = data["newDescription"]
    if data.get("newDate"): update_data["date"] = data["newDate"]
    if data.get("newImageUrl"): update_data["imageUrl"] = data["newImageUrl"]

    if old_title:
        result = activities_col.update_one(
            {"title": old_title},
            {"$set": update_data}
        )
        if result.modified_count:
            return jsonify({"message": "Activity updated successfully"}), 200
        else:
            return jsonify({"error": "No activity found with that title"}), 404

    # Fallback to id-based if provided (legacy clients)
    activity_id = data.get("id")
    if activity_id:
        result = activities_col.update_one(
            {"_id": ObjectId(activity_id)},
            {"$set": update_data}
        )
        if result.modified_count:
            return jsonify({"message": "Activity updated"}), 200
        else:
            return jsonify({"error": "No activity updated. Check ID."}), 404

    return jsonify({"error": "Provide either oldTitle or id to update activity"}), 400


@admin_bp.route('/delete-activity', methods=['DELETE'])
@admin_required
def delete_activity():
    data = request.json

    # Prefer title-based deletion to match frontend
    title = data.get("title")
    if title:
        result = activities_col.delete_one({"title": title})
        if result.deleted_count:
            return jsonify({"message": "Activity deleted successfully"}), 200
        else:
            return jsonify({"error": "No activity found with that title"}), 404

    # Fallback to id-based deletion (legacy)
    activity_id = data.get("id")
    if activity_id:
        result = activities_col.delete_one({"_id": ObjectId(activity_id)})
        if result.deleted_count:
            return jsonify({"message": "Activity deleted"}), 200
        else:
            return jsonify({"error": "No activity deleted. Check ID."}), 404

    return jsonify({"error": "Provide either title or id to delete activity"}), 400


# Maintenance: delete all activities (admin only)
@admin_bp.route('/clear-activities', methods=['DELETE'])
@admin_required
def clear_activities():
    result = activities_col.delete_many({})
    return jsonify({
        "message": "All activities deleted",
        "deletedCount": result.deleted_count
    }), 200



# ------------------------ Run Server ------------------------

if __name__ == '__main__':
    app.run(debug=True, port=5000)
