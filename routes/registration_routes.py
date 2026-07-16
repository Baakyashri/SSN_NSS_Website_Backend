from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime

from models.mongo import activities_collection,users_collection,registrations_collection

registrations_bp = Blueprint('registrations', __name__)


@registrations_bp.route("/create-registration", methods=["POST"])
def create_registration():
    try:

        data = request.json

        user_id = data.get("user_id")
        activity_id = data.get("activity_id")

        if not user_id or not activity_id:
            return jsonify({"error": "user_id and activity_id required"}), 400

        user = users_collection.find_one({"_id": ObjectId(user_id)})

        activity = activities_collection.find_one({"_id": ObjectId(activity_id)})

        if not user:
            return jsonify({"error": "User not found"}), 404

        if not activity:
            return jsonify({"error": "Activity not found"}), 404

        existing = registrations_collection.find_one({
            "user_id": user_id,
            "activity_id": activity_id
        })

        if existing:
            return jsonify({"error": "Already registered"}), 400

        registration_doc = {
            "user_id": user_id,
            "user_email": user["email"],

            "activity_id": activity_id,
            "activity_title": activity["title"],

            "registered_at": datetime.utcnow(),

            "status": "registered"
        }

        result = registrations_collection.insert_one(
            registration_doc
        )

        # Increment registered_count on the activity
        try:
            activities_collection.update_one(
                {"_id": ObjectId(activity_id)},
                {"$inc": {"registered_count": 1}}
            )
        except Exception as e:
            print("Failed to increment registered_count in create_registration:", e)

        return jsonify({
            "message": "Registration created",
            "registration_id": str(result.inserted_id)
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    



@registrations_bp.route("/get-registrations", methods=["GET"])
def get_registrations():

    registrations = []

    for reg in registrations_collection.find():

        reg["_id"] = str(reg["_id"])

        registrations.append(reg)

    return jsonify(registrations), 200



@registrations_bp.route("/get-registration/<registration_id>",methods=["GET"])
def get_registration(registration_id):

    registration = registrations_collection.find_one({"_id": ObjectId(registration_id)})

    if not registration:
        return jsonify({"error": "Registration not found"}), 404

    registration["_id"] = str(registration["_id"])

    return jsonify(registration), 200




@registrations_bp.route("/update-registration/<registration_id>",methods=["PUT"])
def update_registration(registration_id):

    data = request.json

    update_data = {}

    if "status" in data:
        update_data["status"] = data["status"]

    result = registrations_collection.update_one(
        {
            "_id": ObjectId(registration_id)
        },
        {
            "$set": update_data
        }
    )

    if result.matched_count == 0:
        return jsonify({"error": "Registration not found"}), 404

    return jsonify({"message": "Registration updated"}), 200




@registrations_bp.route("/delete-registration/<registration_id>",methods=["DELETE"])
def delete_registration(registration_id):
    try:
        reg = registrations_collection.find_one({"_id": ObjectId(registration_id)})
        if not reg:
            return jsonify({"error": "Registration not found"}), 404

        activity_id = reg.get("activity_id")

        result = registrations_collection.delete_one({"_id": ObjectId(registration_id)})

        if result.deleted_count == 0:
            return jsonify({"error": "Registration not found"}), 404

        # Decrement registered_count on the activity
        if activity_id:
            try:
                activities_collection.update_one(
                    {"_id": ObjectId(activity_id) if isinstance(activity_id, str) else activity_id},
                    {"$inc": {"registered_count": -1}}
                )
            except Exception as e:
                print("Failed to decrement registered_count in delete_registration:", e)

        return jsonify({"message": "Registration deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@registrations_bp.route("/user/<user_id>",methods=["GET"])
def get_user_registrations(user_id):
    """get registrations for a user"""

    registrations = []

    cursor = registrations_collection.find({"user_id": user_id})

    for reg in cursor:
        reg["_id"] = str(reg["_id"])
        registrations.append(reg)

    return jsonify(registrations), 200



@registrations_bp.route("/activity/<activity_id>",methods=["GET"])
def get_activity_registrations(activity_id):
    """get registrations for an activity"""

    registrations = []

    cursor = registrations_collection.find({"activity_id": activity_id})

    for reg in cursor:
        reg["_id"] = str(reg["_id"])
        registrations.append(reg)

    return jsonify(registrations), 200



