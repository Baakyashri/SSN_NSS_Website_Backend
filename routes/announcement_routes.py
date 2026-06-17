from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import Config



announcements_col = db['announcements']



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


