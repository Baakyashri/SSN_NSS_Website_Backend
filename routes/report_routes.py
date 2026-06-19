from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from flask import send_from_directory
import cloudinary
import cloudinary.uploader
from datetime import datetime
from config import Config
import os 



reports_bp = Blueprint("reports", __name__)
UPLOAD_FOLDER = os.path.join(Config.UPLOAD_FOLDER,"reports")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Allowed file extensions
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'docx', 'doc'}


# File size limits (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB for documents


# MIME type validation
ALLOWED_DOCUMENT_MIME_TYPES = {
    'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
}


def allowed_document_file(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_DOCUMENT_EXTENSIONS


def validate_file_size(file, file_type='image'):
    """Validate file size based on type"""
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_type == 'document' and file_size > MAX_DOCUMENT_SIZE:
        return False, f"Document file too large. Maximum size: {MAX_DOCUMENT_SIZE // (1024*1024)}MB"
    elif file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
    
    return True, "OK"


def validate_mime_type(file, file_type='image'):
    """Validate MIME type"""
    mime_type = file.content_type
    if file_type == 'document':
        return mime_type in ALLOWED_DOCUMENT_MIME_TYPES
    return False


@reports_bp.route('/upload-reports', methods=['POST'])
@jwt_required()
def upload_reports():
    try:
        if 'reports' not in request.files:
            return jsonify({'error': 'No reports provided'}), 400
        files = request.files.getlist('reports')
        uploaded_files = []
        print("USE_CLOUDINARY =", Config.USE_CLOUDINARY)
        for file in files:
            if not file or not file.filename:
                continue
            if not allowed_document_file(file.filename):
                continue
            if not validate_mime_type(file, 'document'):
                continue
            is_valid_size, size_error = validate_file_size(file,'document')
            if not is_valid_size:
                return jsonify({'error': size_error}), 400
            filename = secure_filename(file.filename)
            if not filename:
                continue
            try:
                # =====================
                # CLOUDINARY
                # =====================
                if Config.USE_CLOUDINARY:
                    result = cloudinary.uploader.upload(
                        file,
                        folder="nss/activities/reports",
                        resource_type="raw",
                        use_filename=True,
                        unique_filename=True
                    )
                    report_data = {
                        "url": result["secure_url"],
                        "public_id": result["public_id"],
                        "original_name": file.filename,
                        "uploaded_at": datetime.utcnow().isoformat(),
                        "type": "report",
                        "mime_type": file.content_type,
                        "storage": "cloudinary"
                    }
                    print("Uploaded report to Cloudinary")
                # =====================
                # LOCAL STORAGE
                # =====================
                else:
                    file_path = os.path.join(UPLOAD_FOLDER,filename)
                    file.save(file_path)
                    report_data = {
                        "url": f"/uploads/reports/{filename}",
                        "filename": filename,
                        "original_name": file.filename,
                        "uploaded_at": datetime.utcnow().isoformat(),
                        "type": "report",
                        "mime_type": file.content_type,
                        "storage": "local"
                    }
                    print(f"Saved locally: {file_path}")
                uploaded_files.append(report_data)
            except Exception as upload_error:
                print(f"Report upload failed: {upload_error}")
                continue
        if not uploaded_files:
            return jsonify({'error': 'No valid reports uploaded'}), 400
        return jsonify({
            'message': f'Successfully uploaded {len(uploaded_files)} reports',
            'reports': uploaded_files
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500





@reports_bp.route("/download-report", methods=["GET"])
def download_report():
    url = request.args.get("url")
    filename = request.args.get("filename")
    storage = request.args.get("storage")
    if not url:
        return jsonify({"error": "Invalid request"}), 400
    try:
        # =====================
        # LOCAL FILE
        # =====================
        if storage == "local":
            local_filename = url.split("/")[-1]

            return send_from_directory(
                UPLOAD_FOLDER,
                local_filename,
                as_attachment=True,
                download_name=filename or local_filename
            )
        # =====================
        # CLOUDINARY FILE
        # =====================
        elif storage == "cloudinary":
            r = requests.get(url, stream=True)
            if r.status_code != 200:
                return jsonify({"error": "Unable to fetch file"}), 500
            return Response(
                r.iter_content(chunk_size=4096),
                headers={
                    "Content-Disposition":
                        f'attachment; filename="{filename}"',
                    "Content-Type":
                        r.headers.get("Content-Type","application/octet-stream")
                }
            )
        return jsonify({"error": "Unknown storage type"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500