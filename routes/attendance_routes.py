from flask import Blueprint, jsonify
from bson import ObjectId

from models.mongo import users_collection, activities_collection,registrations_collection

attendance_bp = Blueprint("attendance",__name__,)

# user attendance summary
@attendance_bp.route('/user-summary', methods=['GET'])
def user_summary():
    try:

        users = list(users_collection.find({}, {'password': 0}))
        result = []

        for user in users:
            user_id = str(user['_id'])
            attended_regs = list(
                registrations_collection.find({'user_id': user_id,'status': 'attended'}))

            total_hours = 0
            for reg in attended_regs:
                activity = activities_collection.find_one({'_id': ObjectId(reg['activity_id'])})

                if activity:
                    total_hours += int(
                        activity.get('attendance_hours',0))

            result.append({
                'user_id': user_id,
                'email': user['email'],
                'activities_attended': len(attended_regs),
                'total_hours': total_hours
            })

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    




# user detail
@attendance_bp.route('/user/<user_id>', methods=['GET'])
def user_attendance(user_id):
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        attended_regs = list(
            registrations_collection.find({'user_id': user_id,'status': 'attended'}))

        activities_data = []

        total_hours = 0

        for reg in attended_regs:
            activity = activities_collection.find_one({'_id': ObjectId(reg['activity_id'])})
            if not activity:
                continue
            hours = int(
                activity.get('attendance_hours', 0))
            total_hours += hours
            activities_data.append({
                'activity_id': str(activity['_id']),
                'title': activity['title'],
                'date': activity.get('date'),
                'hours': hours
            })

        return jsonify({
            'user_id': user_id,
            'email': user['email'],
            'activities_attended': len(activities_data),
            'total_hours': total_hours,
            'activities': activities_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


# activity attendance summary
@attendance_bp.route('/activity-summary',methods=['GET'])
def activity_summary():
    try:
        activities = list(activities_collection.find())
        result = []
        for activity in activities:
            activity_id = str(activity['_id'])
            participants = (registrations_collection.count_documents({'activity_id': activity_id,'status': 'attended'}))
            hours = int(activity.get('attendance_hours',0))
            result.append({
                'activity_id': activity_id,
                'title': activity['title'],
                'date': activity.get('date'),
                'participants': participants,
                'attendance_hours': hours,
                'total_hours_generated':
                    participants * hours
            })

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    



# dashboard stats
@attendance_bp.route('/dashboard-stats',methods=['GET'])
def dashboard_stats():
    try:
        total_volunteers = (users_collection.count_documents({'role': 'volunteer'}))
        total_activities = (activities_collection.count_documents({}))
        total_registrations = (registrations_collection.count_documents({}))
        total_attended = (registrations_collection.count_documents({'status': 'attended'}))
        total_hours_generated = 0
        attended_regs = list(registrations_collection.find({'status': 'attended'}))

        for reg in attended_regs:
            activity = (activities_collection.find_one({'_id': ObjectId(reg['activity_id'])}))
            if activity:
                total_hours_generated += int(activity.get('attendance_hours',0))

        return jsonify({
            'total_volunteers':total_volunteers,
            'total_activities':total_activities,
            'total_registrations':total_registrations,
            'total_attended':total_attended,
            'total_hours_generated':total_hours_generated}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500