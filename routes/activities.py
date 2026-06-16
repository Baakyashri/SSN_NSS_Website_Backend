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

@activities_bp.route('/activities', methods=['GET'])
def get_activities():
    """Get all activities"""
    try:
        activities = list(activities_col.find().sort('date', -1))
        # Convert ObjectId to string for JSON serialization
        activities = convert_objectid_to_str(activities)
        return jsonify(activities), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@activities_bp.route('/activities/latest', methods=['GET'])
def get_latest_activities_endpoint():
    """Get latest 3 activities"""
    try:
        activities = list(activities_col.find().sort('date', -1).limit(3))
        # Convert ObjectId to string for JSON serialization
        activities = convert_objectid_to_str(activities)
        return jsonify(activities), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@activities_bp.route('/activities/<activity_id>', methods=['GET'])
def get_activity(activity_id):
    """Get a specific activity by ID"""
    try:
        activity = activities_col.find_one({'_id': ObjectId(activity_id)})
        if activity:
            activity = convert_objectid_to_str(activity)
            return jsonify(activity), 200
        else:
            return jsonify({'error': 'Activity not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@activities_bp.route('/activities', methods=['POST'])
def create_activity():
    """Create a new activity (admin only)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['title', 'description', 'date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
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
            activity_data['_id'] = str(result.inserted_id)
            return jsonify(activity_data), 201
        else:
            return jsonify({'error': 'Failed to create activity'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
