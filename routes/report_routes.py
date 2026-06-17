from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from db import db
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import Config



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
