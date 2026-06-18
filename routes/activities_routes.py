from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from db import db
from models.mongo import activities_collection
from datetime import datetime
from bson.objectid import ObjectId

activities_bp = Blueprint('activities', __name__)


def convert_objectid_to_str(obj):
    """Convert ObjectId to string for JSON serialization"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    return obj


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



# ------------------------ Activity APIs ------------------------
@activities_bp.route('/add-activity', methods=['POST'])
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
        "location": data.get('location'),
        "status": data.get('status'),
        "photos": data.get('photos', []),
        "reports": data.get('reports', []),
    }

    # Insert into database
    result = activities_collection.insert_one(activity_data)
    
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
    



@activities_bp.route('/delete-activity', methods=['DELETE'])
@admin_required
def delete_activity():
    data = request.json

    # Prefer title-based deletion to match frontend
    title = data.get("title")
    if title:
        result = activities_collection.delete_one({"title": title})
        if result.deleted_count:
            return jsonify({"message": "Activity deleted successfully"}), 200
        else:
            return jsonify({"error": "No activity found with that title"}), 404

    # Fallback to id-based deletion (legacy)
    activity_id = data.get("id")
    if activity_id:
        result = activities_collection.delete_one({"_id": ObjectId(activity_id)})
        if result.deleted_count:
            return jsonify({"message": "Activity deleted"}), 200
        else:
            return jsonify({"error": "No activity deleted. Check ID."}), 404

    return jsonify({"error": "Provide either title or id to delete activity"}), 400




@activities_bp.route('/update-activity', methods=['PUT'])
@admin_required
def update_activity():
    data = request.json

    # Support both title-based and id-based updates, prefer title-based to match frontend
    old_title = data.get("oldTitle")
    update_data = {}
    if data.get("newTitle"): update_data["title"] = data["newTitle"]
    if data.get("newDescription"): update_data["description"] = data["newDescription"]
    if data.get("newDate"): update_data["date"] = data["newDate"]
    if data.get("newLocation"): update_data["location"] = data["newLocation"]
    if data.get("newStatus"): update_data["status"] = data["newStatus"]
    if data.get("newPhotos"): update_data["photos"] = data["newPhotos"]
    if data.get("newReports"): update_data["reports"] = data["newReports"]

    if old_title:
        result = activities_collection.update_one(
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
        result = activities_collection.update_one(
            {"_id": ObjectId(activity_id)},
            {"$set": update_data}
        )
        if result.modified_count:
            return jsonify({"message": "Activity updated"}), 200
        else:
            return jsonify({"error": "No activity updated. Check ID."}), 404

    return jsonify({"error": "Provide either oldTitle or id to update activity"}), 400




@activities_bp.route('/get-activities', methods=['GET'])
def get_activities():
    """Get all activities for admin view"""
    try:
        activities = list(activities_collection.find({}, {'_id': 0}))
        return jsonify(activities), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500