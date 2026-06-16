from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
from config import JWT_SECRET_KEY

from routes.auth import auth_bp
from admin_register_user import admin_bp
import os
from config import UPLOAD_FOLDER
from routes.album import albums_bp
from routes.contact import contact_bp
from routes.activities import activities_bp
from routes.photos import photos_bp
from flask import send_from_directory, jsonify

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure CORS with specific origins for security
CORS(app, origins=[
    "https://nss-ssn.vercel.app",  # Production frontend
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",  # Alternative localhost
    "http://localhost:3001",  # Alternative React port
    "http://127.0.0.1:3001",  # Alternative React port
    # Add production domains here when deploying
], supports_credentials=True)
jwt = JWTManager(app)

# Explicitly load the .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
try:
    load_dotenv(dotenv_path)
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")
    # Continue without .env file

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Add error handling for database connection
@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error. Please check if MongoDB is running.'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'error': f'Server error: {str(e)}'}), 500

#login route
app.register_blueprint(auth_bp, url_prefix='/auth')
#admin route
app.register_blueprint(admin_bp, url_prefix='/admin')


# Register album routes
app.register_blueprint(albums_bp)


@app.route('/')
def home():
    return jsonify({
        'message': 'NSS Portal API Server',
        'status': 'running',
        'version': '1.0.0',
        'endpoints': {
            'admin': '/admin/*',
            'api': '/api/*',
            'auth': '/auth/*',
            'uploads': '/uploads/*'
        }
    })

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No content response for favicon

import logging
from flask import abort

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        logging.error(f"Error serving file {filename}: {e}")
        abort(500, description="Error serving file")

app.register_blueprint(contact_bp, url_prefix='/api')
app.register_blueprint(activities_bp, url_prefix='/api')
app.register_blueprint(photos_bp)


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
