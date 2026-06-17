from flask import Blueprint, request, jsonify, send_from_directory
from bson import ObjectId
from uuid import uuid4
from werkzeug.utils import secure_filename

from models.mongo import albums_collection
from config import Config

import os
import cloudinary.uploader

albums_bp = Blueprint("albums", __name__)


# ==================================================
# HELPERS
# ==================================================

def serialize_album(album):
    album["_id"] = str(album["_id"])
    return album


def get_album_by_id(album_id):
    try:
        return albums_collection.find_one(
            {"_id": ObjectId(album_id)}
        )
    except Exception:
        return None


def delete_photo_from_storage(photo):
    """
    Automatically deletes from the correct storage backend.
    """

    try:
        if photo.get("storage") == "cloudinary":
            cloudinary.uploader.destroy(
                photo["filename"]
            )

        elif photo.get("storage") == "local":
            path = os.path.join(
                Config.UPLOAD_FOLDER,
                photo["filename"]
            )

            if os.path.exists(path):
                os.remove(path)

    except Exception as e:
        print(f"Storage deletion error: {str(e)}")


# ==================================================
# GET ALL ALBUMS
# ==================================================

@albums_bp.route("/api/albums", methods=["GET"])
def get_albums():
    albums = list(albums_collection.find())

    for album in albums:
        album["_id"] = str(album["_id"])

    return jsonify(albums), 200


# ==================================================
# GET SINGLE ALBUM
# ==================================================

@albums_bp.route("/api/albums/<album_id>", methods=["GET"])
def get_album(album_id):

    album = get_album_by_id(album_id)

    if not album:
        return jsonify({
            "error": "Album not found"
        }), 404

    return jsonify(serialize_album(album)), 200


# ==================================================
# CREATE ALBUM
# ==================================================

@albums_bp.route("/api/albums", methods=["POST"])
def create_album():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Invalid request body"
        }), 400

    name = data.get("name", "").strip()

    if not name:
        return jsonify({
            "error": "Album name required"
        }), 400

    existing = albums_collection.find_one({
        "name": name
    })

    if existing:
        return jsonify({
            "error": "Album already exists"
        }), 400

    result = albums_collection.insert_one({
        "name": name,
        "photos": []
    })

    return jsonify({
        "message": "Album created successfully",
        "album_id": str(result.inserted_id)
    }), 201


# ==================================================
# DELETE ALBUM
# ==================================================

@albums_bp.route("/api/albums/<album_id>", methods=["DELETE"])
def delete_album(album_id):

    album = get_album_by_id(album_id)

    if not album:
        return jsonify({
            "error": "Album not found"
        }), 404

    for photo in album.get("photos", []):
        delete_photo_from_storage(photo)

    albums_collection.delete_one({
        "_id": ObjectId(album_id)
    })

    return jsonify({
        "message": "Album deleted successfully"
    }), 200


# ==================================================
# UPLOAD PHOTOS
# ==================================================

@albums_bp.route(
    "/api/albums/<album_id>/photos",
    methods=["POST"]
)
def upload_photos(album_id):

    album = get_album_by_id(album_id)

    if not album:
        return jsonify({
            "error": "Album not found"
        }), 404

    all_files = []

    for key in ["photos", "file", "image", "images"]:
        if key in request.files:
            all_files.extend(
                request.files.getlist(key)
            )

    if not all_files:
        return jsonify({
            "error": "No photos uploaded"
        }), 400

    uploaded_photos = []

    for file in all_files:

        if not file or not file.filename:
            continue

        try:

            photo_id = str(uuid4())

            # =====================================
            # CLOUDINARY MODE
            # =====================================

            if Config.USE_CLOUDINARY:

                upload_result = (
                    cloudinary.uploader.upload(
                        file,
                        folder="nss/gallery",
                        resource_type="image"
                    )
                )

                photo = {
                    "_id": photo_id,
                    "filename": upload_result[
                        "public_id"
                    ],
                    "url": upload_result[
                        "secure_url"
                    ],
                    "storage": "cloudinary",
                    "original_name": file.filename
                }

            # =====================================
            # LOCAL MODE
            # =====================================

            else:

                filename = (
                    f"{uuid4()}_"
                    f"{secure_filename(file.filename)}"
                )

                save_path = os.path.join(
                    Config.UPLOAD_FOLDER,
                    filename
                )

                file.save(save_path)

                photo = {
                    "_id": photo_id,
                    "filename": filename,
                    "url": f"/uploads/{filename}",
                    "storage": "local",
                    "original_name": file.filename
                }

            albums_collection.update_one(
                {
                    "_id": ObjectId(album_id)
                },
                {
                    "$push": {
                        "photos": photo
                    }
                }
            )

            uploaded_photos.append(photo)

        except Exception as e:

            print(
                f"Upload error: {str(e)}"
            )

            return jsonify({
                "error": str(e)
            }), 500

    return jsonify({
        "message": "Photos uploaded successfully",
        "photos": uploaded_photos
    }), 200


# ==================================================
# DELETE PHOTO
# ==================================================

@albums_bp.route(
    "/api/albums/<album_id>/photos/<photo_id>",
    methods=["DELETE"]
)
def delete_photo(album_id, photo_id):

    album = get_album_by_id(album_id)

    if not album:
        return jsonify({
            "error": "Album not found"
        }), 404

    photo = next(
        (
            p
            for p in album.get("photos", [])
            if p.get("_id") == photo_id
        ),
        None
    )

    if not photo:
        return jsonify({
            "error": "Photo not found"
        }), 404

    delete_photo_from_storage(photo)

    updated_photos = [
        p
        for p in album["photos"]
        if p.get("_id") != photo_id
    ]

    albums_collection.update_one(
        {
            "_id": ObjectId(album_id)
        },
        {
            "$set": {
                "photos": updated_photos
            }
        }
    )

    return jsonify({
        "message": "Photo deleted successfully"
    }), 200


# ==================================================
# LOCAL FILE SERVING
# ==================================================

@albums_bp.route(
    "/uploads/<path:filename>",
    methods=["GET"]
)
def serve_photo(filename):

    return send_from_directory(
        Config.UPLOAD_FOLDER,
        filename
    )
