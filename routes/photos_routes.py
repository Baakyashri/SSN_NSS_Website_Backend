import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from utils.cloudinary import cloudinary
from flask_jwt_extended import jwt_required
import cloudinary
import cloudinary.uploader
from config import Config
from db import db
from datetime import datetime


photos_bp = Blueprint('photos', __name__)
UPLOAD_FOLDER = Config.UPLOAD_FOLDER


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



@photos_bp.route('/upload-photos', methods=['POST'])
@jwt_required()
def upload_photos():
    """Upload multiple photos to Cloudinary or local storage"""

    try:
        if 'photos' not in request.files:
            return jsonify({'error': 'No photos provided'}), 400

        files = request.files.getlist('photos')
        uploaded_files = []
        print("USE_CLOUDINARY =", Config.USE_CLOUDINARY)
        for file in files:
            if not file or not file.filename:
                continue
            print("Filename:", file.filename)
            print("Content Type:", file.content_type)
            # Extension validation
            if not allowed_image_file(file.filename):
                print("Invalid extension")
                continue
            print("Extension Valid")
            # MIME validation
            if not validate_mime_type(file, 'image'):
                print("Invalid MIME Type")
                continue
            print("MIME TYPE PASSED")
            # File size validation
            is_valid, error_msg = validate_file_size(file, 'image')
            if not is_valid:
                print(error_msg)
                continue
            try:
                # ==========================
                # CLOUDINARY UPLOAD
                # ==========================
                if Config.USE_CLOUDINARY:
                    upload_result = cloudinary.uploader.upload(file,folder="nss/activities/photos",resource_type="image")
                    photo_data = {
                        'filename': upload_result['public_id'],
                        'original_name': file.filename,
                        'url': upload_result['secure_url'],
                        'uploaded_at': datetime.now().isoformat(),
                        'mime_type': file.content_type,
                        'storage': 'cloudinary'
                    }

                    print("Uploaded to Cloudinary")
                # ==========================
                # LOCAL UPLOAD
                # ==========================
                else:

                    filename = secure_filename(file.filename)
                    file_path = os.path.join(UPLOAD_FOLDER,filename)
                    file.save(file_path)
                    photo_data = {
                        'filename': filename,
                        'original_name': file.filename,
                        'url': f'/uploads/{filename}',
                        'uploaded_at': datetime.now().isoformat(),
                        'mime_type': file.content_type,
                        'storage': 'local'
                    }
                    print(f"Saved locally: {file_path}")

                uploaded_files.append(photo_data)

            except Exception as upload_error:
                print(f"Upload failed: {str(upload_error)}")
                continue

        if not uploaded_files:
            return jsonify({'error': 'No valid photos uploaded'}), 400

        return jsonify({
            'message': f'Successfully uploaded {len(uploaded_files)} photos',
            'photos': uploaded_files
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500







        
@photos_bp.route('/get-photos', methods=['GET'])
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

@photos_bp.route('/delete-photo', methods=['DELETE'])
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


