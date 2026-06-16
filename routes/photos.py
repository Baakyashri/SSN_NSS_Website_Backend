import requests
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.utils import secure_filename
import os
from utils.cloudinary import cloudinary
import cloudinary
import cloudinary.uploader
from config import UPLOAD_FOLDER
from db import db
import uuid
from datetime import datetime

photos_bp = Blueprint('photos', __name__)

# Allowed file extensions
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'docx', 'doc'}

# File size limits (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_SIZE = 50 * 1024 * 1024   # 50MB for images
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB for documents

# MIME type validation
ALLOWED_IMAGE_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'
}
ALLOWED_DOCUMENT_MIME_TYPES = {
    'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
}

def allowed_image_file(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS

def allowed_document_file(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_DOCUMENT_EXTENSIONS

def allowed_file(filename):
    return allowed_image_file(filename) or allowed_document_file(filename)

def validate_file_size(file, file_type='image'):
    """Validate file size based on type"""
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_type == 'image' and file_size > MAX_IMAGE_SIZE:
        return False, f"Image file too large. Maximum size: {MAX_IMAGE_SIZE // (1024*1024)}MB"
    elif file_type == 'document' and file_size > MAX_DOCUMENT_SIZE:
        return False, f"Document file too large. Maximum size: {MAX_DOCUMENT_SIZE // (1024*1024)}MB"
    elif file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
    
    return True, "OK"

def validate_mime_type(file, file_type='image'):
    """Validate MIME type"""
    mime_type = file.content_type
    if file_type == 'image':
        return mime_type in ALLOWED_IMAGE_MIME_TYPES
    elif file_type == 'document':
        return mime_type in ALLOWED_DOCUMENT_MIME_TYPES
    return False

@photos_bp.route('/admin/upload-photos', methods=['POST'])
@jwt_required()
def upload_photos():
    """Upload multiple photos to Cloudinary"""
    try:
        if 'photos' not in request.files:
            return jsonify({'error': 'No photos provided'}), 400
        
        files = request.files.getlist('photos')
        uploaded_files = []
        
        for file in files:
            # Basic validation
            if file and file.filename and allowed_image_file(file.filename):
                if not validate_mime_type(file, 'image'):
                    continue
                
                # Upload to Cloudinary (Permanent Storage)
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="nss/activities/photos", # distinct folder for organization
                        resource_type="image"
                    )
                    
                    # Store the Cloudinary URL (starts with http/https)
                    photo_data = {
                        'filename': upload_result['public_id'], # Use public_id for reference
                        'original_name': file.filename,
                        'url': upload_result['secure_url'],     # ✅ This is the permanent link
                        'uploaded_at': datetime.now().isoformat(),
                        'mime_type': file.content_type
                    }
                    uploaded_files.append(photo_data)
                    
                except Exception as upload_error:
                    print(f"Cloudinary upload failed: {str(upload_error)}")
                    continue

        if not uploaded_files:
            return jsonify({'error': 'No valid photos uploaded'}), 400
        
        return jsonify({
            'message': f'Successfully uploaded {len(uploaded_files)} photos',
            'photos': uploaded_files
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
@photos_bp.route('/admin/get-photos', methods=['GET'])
@jwt_required()
def get_photos():
    """Get all photos from the gallery"""
    try:
        photos = []
        
        # Get all files from uploads directory
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if allowed_file(filename):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    if os.path.isfile(file_path):
                        photos.append({
                            'filename': filename,
                            'url': f'/uploads/{filename}',
                            'name': filename,
                            'size': os.path.getsize(file_path)
                        })
        
        return jsonify(photos), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@photos_bp.route('/admin/delete-photo', methods=['DELETE'])
@jwt_required()
def delete_photo():
    """Delete a photo from the gallery"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'error': 'Filename required'}), 400
        
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'message': 'Photo deleted successfully'}), 200
        else:
            return jsonify({'error': 'Photo not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@photos_bp.route('/admin/get-activities', methods=['GET'])
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

@photos_bp.route('/admin/upload-reports', methods=['POST'])
@jwt_required()
def upload_reports():
    """Upload report documents for activities"""
    try:
        if 'reports' not in request.files:
            return jsonify({'error': 'No reports provided'}), 400
        
        files = request.files.getlist('reports')
        uploaded_files = []
        
        for file in files:
            if file and file.filename and allowed_document_file(file.filename):
                # Validate MIME type
                if not validate_mime_type(file, 'document'):
                    continue
                
                # Validate file size
                is_valid_size, size_error = validate_file_size(file, 'document')
                if not is_valid_size:
                    return jsonify({'error': size_error}), 400
                
                # Generate unique filename with path traversal protection
                filename = secure_filename(file.filename)
                if not filename:  # Additional security check
                    continue
                
                result = cloudinary.uploader.upload(
                    file,
                    folder="nss/activities/reports",
                    resource_type="raw",
                    use_filename=True,
                    unique_filename=True
                )
                # unique_filename = f"report_{uuid.uuid4()}_{filename}"
                # file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                
                # Ensure the file is saved within the upload directory
                # if not os.path.abspath(file_path).startswith(os.path.abspath(UPLOAD_FOLDER)):
                #     return jsonify({'error': 'Invalid file path'}), 400
                
                # Save file
                # file.save(file_path)
                
                # Store report info
                # report_data = {
                #     'filename': unique_filename,
                #     'original_name': filename,
                #     'url': f'/uploads/{unique_filename}',
                #     'uploaded_at': datetime.now().isoformat(),
                #     'size': os.path.getsize(file_path),
                #     'type': 'report',
                #     'mime_type': file.content_type
                # }
                report_data = {
                    "url": result["secure_url"],          # ✅ permanent link
                    "public_id": result["public_id"],     # needed for delete
                    "original_name": file.filename,
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "type": "report",
                    "mime_type": file.content_type
                }
                uploaded_files.append(report_data)
        
        if not uploaded_files:
            return jsonify({'error': 'No valid reports uploaded'}), 400
        
        return jsonify({
            'message': f'Successfully uploaded {len(uploaded_files)} reports',
            'reports': uploaded_files
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@photos_bp.route('/admin/add-activity', methods=['POST'])
@jwt_required()
def add_activity():
    """Add a new activity (stored in MongoDB)"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['title', 'description', 'date']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400

        # Prepare activity document
        activity_doc = {
            'title': data['title'],
            'description': data['description'],
            'date': data['date'],
            'photos': data.get('photos', []),
            'reports': data.get('reports', []),
            'location': data.get('location', 'SSN Campus'),
            'status': data.get('status', 'upcoming')
        }

        # Insert into MongoDB
        from db import db
        activities_col = db['activities']
        result = activities_col.insert_one(activity_doc)

        if not result.inserted_id:
            return jsonify({'error': 'Failed to create activity'}), 500

        # Return created activity without exposing ObjectId in admin list (consistent with get-activities)
        return jsonify({
            'message': 'Activity added successfully',
            'activity': activity_doc,
            'activity_id': str(result.inserted_id)
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@photos_bp.route('/admin/update-activity', methods=['PUT'])
@jwt_required()
def update_activity():
    """Update an existing activity"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if 'oldTitle' not in data:
            return jsonify({'error': 'oldTitle is required'}), 400
        
        # Update in MongoDB
        from db import activities_col
        from bson import ObjectId
        
        update_data = {}
        if data.get("newTitle"): update_data["title"] = data["newTitle"]
        if data.get("newDescription"): update_data["description"] = data["newDescription"]
        if data.get("newDate"): update_data["date"] = data["newDate"]
        if data.get("newImageUrl"): update_data["imageUrl"] = data["newImageUrl"]
        
        result = activities_col.update_one(
            {"title": data["oldTitle"]},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return jsonify({'message': 'Activity updated successfully'}), 200
        else:
            return jsonify({'error': 'No activity found with that title'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@photos_bp.route('/admin/delete-activity', methods=['DELETE'])
@jwt_required()
def delete_activity():
    """Delete an activity"""
    try:
        data = request.get_json()
        
        if 'title' not in data:
            return jsonify({'error': 'title is required'}), 400
        
        # Delete from MongoDB
        from db import activities_col
        
        result = activities_col.delete_one({"title": data["title"]})
        
        if result.deleted_count:
            return jsonify({'message': 'Activity deleted successfully'}), 200
        else:
            return jsonify({'error': 'No activity found with that title'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@photos_bp.route("/download-report", methods=["GET"])
def download_report():
    url = request.args.get("url")
    filename = request.args.get("filename")

    if not url or not filename:
        return jsonify({"error": "Invalid request"}), 400

    try:
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            return jsonify({"error": "Unable to fetch file"}), 500

        return Response(
            r.iter_content(chunk_size=4096),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": r.headers.get("Content-Type", "application/pdf")
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
