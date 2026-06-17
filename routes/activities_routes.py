from flask import Blueprint, request, jsonify
from db import db
from datetime import datetime
from bson.objectid import ObjectId

activities_bp = Blueprint('activities', __name__)

# Get activities collection
activities_col = db['activities']

def convert_objectid_to_str(obj):
    """Convert ObjectId to string for JSON serialization"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    return obj


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




@admin_bp.route('/get-activities', methods=['GET'])
@jwt_required()
def get_activities():
    """Get all activities for admin view"""
    try:
        # Use the shared DB handle to access the activities collection
        from db import db
        activities_col = db['activities']
        activities = list(activities_col.find({}, {'_id': 0}))
        return jsonify(activities), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500