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
        "attendance_hours" : data.get('attendance_hours','0'),
        "no_of_volunteers" : data.get('no_of_volunteers'),
        "photos": data.get('photos', []),
        "reports": data.get('reports', []),
    }

    # Insert into database
    result = activities_collection.insert_one(activity_data)
    
    if result.inserted_id:
        activity_id_str = str(result.inserted_id)

        # Trigger background report ingestion if reports are present
        reports = activity_data.get("reports", [])
        if reports:
            try:
                from utils.ingestion import run_ingestion_in_background, extract_activity_metadata
                metadata = extract_activity_metadata(activity_data)
                run_ingestion_in_background(activity_id_str, reports, metadata)
            except Exception as e:
                print("Failed to trigger background ingestion in add_activity:", e)

        # Auto-enqueue a single_activity report job if activity is finalized
        try:
            from utils.ingestion import check_and_enqueue_auto_report
            check_and_enqueue_auto_report(activity_id_str, activity_data)
        except Exception as e:
            print("Failed to trigger auto-report in add_activity:", e)

        # Convert ObjectId to string for JSON serialization
        safe_activity_data = convert_objectid_to_str(activity_data)
        return jsonify({
            "message": "Activity added successfully",
            "activity_id": activity_id_str,
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
    if data.get("newAttendanceHours"): update_data["attendance_hours"] = data["newAttendanceHours"]
    if data.get("newNoOfVolunteers"): update_data["no_of_volunteers"] = data["newNoOfVolunteers"]
    if data.get("newPhotos"): update_data["photos"] = data["newPhotos"]
    if data.get("newReports"): update_data["reports"] = data["newReports"]

    updated_activity = None
    message = ""
    status_code = 200

    if old_title:
        result = activities_collection.update_one(
            {"title": old_title},
            {"$set": update_data}
        )
        if result.modified_count:
            target_title = update_data.get("title", old_title)
            updated_activity = activities_collection.find_one({"title": target_title})
            message = "Activity updated successfully"
            status_code = 200
        else:
            return jsonify({"error": "No activity found with that title"}), 404

    else:
        # Fallback to id-based if provided (legacy clients)
        activity_id = data.get("id")
        if activity_id:
            result = activities_collection.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": update_data}
            )
            if result.modified_count:
                updated_activity = activities_collection.find_one({"_id": ObjectId(activity_id)})
                message = "Activity updated"
                status_code = 200
            else:
                return jsonify({"error": "No activity updated. Check ID."}), 404
        else:
            return jsonify({"error": "Provide either oldTitle or id to update activity"}), 400

    if updated_activity:
        activity_id_str = str(updated_activity["_id"])

        # Trigger background report ingestion if reports are present
        reports = updated_activity.get("reports", [])
        if reports:
            try:
                from utils.ingestion import run_ingestion_in_background, extract_activity_metadata
                metadata = extract_activity_metadata(updated_activity)
                run_ingestion_in_background(activity_id_str, reports, metadata)
            except Exception as e:
                print("Failed to trigger background ingestion in update_activity:", e)

        # Auto-enqueue a single_activity report job if activity is finalized
        try:
            from utils.ingestion import check_and_enqueue_auto_report
            check_and_enqueue_auto_report(activity_id_str, updated_activity)
        except Exception as e:
            print("Failed to trigger auto-report in update_activity:", e)

    return jsonify({"message": message}), status_code



@activities_bp.route('/get-activities', methods=['GET'])
def get_activities():
    try:
        activities = list(activities_collection.find())

        for activity in activities:
            activity['_id'] = str(activity['_id'])

        return jsonify(activities), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@activities_bp.route('/get-upcoming-activities', methods=['GET'])
def get_upcoming_activities():
    try:
        activities = list(
            activities_collection.find({"status": "upcoming"})
        )

        for activity in activities:
            activity['_id'] = str(activity['_id'])

        return jsonify(activities), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500