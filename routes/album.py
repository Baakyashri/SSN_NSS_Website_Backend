from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from models.mongo import albums_collection
from config import UPLOAD_FOLDER
import os
from utils.cloudinary import cloudinary
import cloudinary
import cloudinary.uploader
import uuid

albums_bp = Blueprint('albums', __name__)

# ==============================
# GET ALL ALBUMS WITH PHOTOS
# ==============================
@albums_bp.route('/api/albums', methods=['GET'])
def get_albums():
    albums = list(albums_collection.find())

    for album in albums:
        album["_id"] = str(album["_id"])
        album["photos"] = album.get("photos", [])
        for photo in album["photos"]:
            if photo.get("url") and not photo["url"].startswith("http"):
                try:
                    host = request.host_url.rstrip('/')
                except Exception:
                    host = "http://localhost:5000"
                photo["url"] = f"{host}/uploads/{photo['filename']}"

    return jsonify(albums)

# ==============================
# CREATE ALBUM
# ==============================
@albums_bp.route('/api/albums', methods=['POST'])
def create_album():
    data = request.json
    name = data.get("name")

    if not name:
        return jsonify({"error": "Album name required"}), 400

    if albums_collection.find_one({"name": name}):
        return jsonify({"error": "Album already exists"}), 400

    albums_collection.insert_one({
        "name": name,
        "photos": []
    })

    return jsonify({"message": "Album created successfully"})

# ==============================
# DELETE ALBUM
# ==============================
@albums_bp.route('/api/albums/<album_name>', methods=['DELETE'])
def delete_album(album_name):
    album = albums_collection.find_one({"name": album_name})
    if not album:
        return jsonify({"error": "Album not found"}), 404

    for photo in album.get("photos", []):
        path = os.path.join(UPLOAD_FOLDER, photo["filename"])
        if os.path.exists(path):
            os.remove(path)

    albums_collection.delete_one({"name": album_name})
    return jsonify({"message": "Album deleted successfully"})

# ==============================
# UPLOAD / ASSOCIATE PHOTOS
# ==============================
'''
@albums_bp.route('/api/albums/<album_name>/photos', methods=['POST'])
def upload_photos(album_name):
    album = albums_collection.find_one({"name": album_name})
    if not album:
        return jsonify({"error": "Album not found"}), 404

    photo_list = []

    # ------------------------------
    # JSON association mode
    # ------------------------------
    if request.is_json and request.json.get("photos"):
        incoming = request.json.get("photos")
        if not isinstance(incoming, list):
            return jsonify({"error": "Invalid photos payload"}), 400

        try:
            host = request.host_url.rstrip('/')
        except Exception:
            host = "http://localhost:5000"

        for p in incoming:
            if not isinstance(p, dict):
                continue

            filename = p.get("filename")
            if not filename:
                continue

            photo_list.append({
                "filename": filename,
                "url": p.get("url") or f"{host}/uploads/{filename}"
            })

    # ------------------------------
    # Multipart upload mode
    # ------------------------------
    else:
        if 'photos' not in request.files:
            return jsonify({"error": "No photos uploaded"}), 400

        uploaded_photos = request.files.getlist('photos')

        for file in uploaded_photos:
            if not file or not file.filename:
                continue

            filename = secure_filename(file.filename)
            if not filename:
                continue

            ext = filename.rsplit('.', 1)[-1].lower()
            if ext not in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
                continue

            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

            if not os.path.abspath(file_path).startswith(os.path.abspath(UPLOAD_FOLDER)):
                continue

            file.save(file_path)

            try:
                host = request.host_url.rstrip('/')
            except Exception:
                host = "http://localhost:5000"

            photo_list.append({
                "filename": unique_filename,
                "url": f"{host}/uploads/{unique_filename}"
            })

    if not photo_list:
        return jsonify({"error": "No valid photos provided"}), 400

    albums_collection.update_one(
        {"name": album_name},
        {"$push": {"photos": {"$each": photo_list}}}
    )

    return jsonify({
        "message": "Photos added to album successfully",
        "photos": photo_list
    })
'''
# In album.py

# In album.py

@albums_bp.route('/api/albums/<album_name>/photos', methods=['POST'])
def upload_photos(album_name):
    # 1. Verify Album Exists
    album = albums_collection.find_one({"name": album_name})
    if not album:
        return jsonify({"error": f"Album '{album_name}' not found"}), 404

    if request.is_json and request.json.get("photos"):
        photos = request.json.get("photos")

        if not isinstance(photos, list):
            return jsonify({"error": "Invalid photos payload"}), 400

        albums_collection.update_one(
            {"name": album_name},
            {"$push": {"photos": {"$each": photos}}}
        )

        return jsonify({
            "message": "Photos added via JSON",
            "photos": photos
        }), 200

    uploaded_files_log = []
    
    # 2. DEBUG: Print all keys received from Frontend
    print(f"DEBUG: Received file keys: {list(request.files.keys())}")

    # 3. Smart Key Detection (Handle 'photos', 'file', 'image', etc.)
    # We collect files from ALL recognized keys
    all_files = []
    for key in ['photos', 'file', 'image', 'images']:
        if key in request.files:
            files = request.files.getlist(key)
            all_files.extend(files)
            print(f"Found {len(files)} files under key '{key}'")

    if not all_files:
        return jsonify({"error": f"No photos found. Keys received: {list(request.files.keys())}"}), 400

    # 4. Process all found files
    for file in all_files:
        if not file or not file.filename:
            continue

        try:
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file,
                folder="nss/gallery",
                resource_type="image"
            )
            
            new_photo = {
                "filename": upload_result.get("public_id"),
                "url": upload_result.get("secure_url"),
                "original_name": file.filename
            }

            # Update MongoDB IMMEDIATELY
            albums_collection.update_one(
                {"name": album_name},
                {"$push": {"photos": new_photo}}
            )
            
            uploaded_files_log.append(new_photo)

        except Exception as e:
            print(f"CRITICAL ERROR processing {file.filename}: {str(e)}")
            return jsonify({"error": f"Server Crash: {str(e)}"}), 500

    if not uploaded_files_log:
        return jsonify({"error": "No valid photos uploaded (Check logs for details)"}), 400

    return jsonify({"message": "Photos added", "photos": uploaded_files_log})
    
# ==============================
# DELETE PHOTO FROM ALBUM
# ==============================
@albums_bp.route('/api/albums/<album_name>/photos/<int:index>', methods=['DELETE'])
def delete_photo(album_name, index):
    album = albums_collection.find_one({"name": album_name})

    if not album or index >= len(album.get("photos", [])):
        return jsonify({"error": "Photo not found"}), 404

    photo = album["photos"][index]
    path = os.path.join(UPLOAD_FOLDER, photo["filename"])

    if os.path.exists(path):
        os.remove(path)

    album["photos"].pop(index)
    albums_collection.update_one(
        {"name": album_name},
        {"$set": {"photos": album["photos"]}}
    )

    return jsonify({"message": "Photo deleted successfully"})

# ==============================
# SERVE UPLOADED FILES
# ==============================
@albums_bp.route('/uploads/<filename>')
def serve_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
