from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config

from routes.auth_routes import auth_bp
from routes.user_routes import user_bp





import os
import logging

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


# --------------------------------------------------
# Register Blueprints
# --------------------------------------------------

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(user_bp, url_prefix="/user")




# --------------------------------------------------
# Application Entry Point
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=Config.DEBUG
    )