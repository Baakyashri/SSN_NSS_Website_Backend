import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, os.getenv("UPLOAD_FOLDER", "uploads"))

MONGO_URI = os.getenv("MONGO_URI")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")