from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask import send_from_directory
import os
import logging
from config import Config
from routes.auth_routes import auth_bp
from routes.user_routes import user_bp
from routes.activities_routes import activities_bp
from routes.album_routes import albums_bp
from routes.photos_routes import photos_bp
from routes.report_routes import reports_bp
from routes.contact_routes import contact_bp
from routes.chat_routes import chat_bp


# --------------------------------------------------
# App Initialization
# --------------------------------------------------

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = Config.JWT_SECRET_KEY
app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER

# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# CORS
# --------------------------------------------------

CORS(
    app,
    origins=Config.CORS_ORIGINS,
    supports_credentials=True
)

# --------------------------------------------------
# JWT
# --------------------------------------------------

jwt = JWTManager(app)

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "service": "NSS Portal API",
        "status": "running",
        "version": "1.0.0"
    })



# --------------------------------------------------
# Error Handlers
# --------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Resource not found"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    logger.exception(error)

    return jsonify({
        "error": "Internal server error"
    }), 500



@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(
        Config.UPLOAD_FOLDER,
        filename
    )

# --------------------------------------------------
# Register Blueprints
# --------------------------------------------------

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(user_bp, url_prefix="/user")
app.register_blueprint(activities_bp,url_prefix="/activities")
app.register_blueprint(albums_bp,url_prefix="/albums")
app.register_blueprint(photos_bp,url_prefix="/photos")
app.register_blueprint(reports_bp,url_prefix="/reports")
app.register_blueprint(contact_bp,url_prefix="/contact")
app.register_blueprint(chat_bp)


# --------------------------------------------------
# Application Entry Point
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=Config.DEBUG
    )