import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    MONGO_URI = os.getenv("MONGO_URI")

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)

    UPLOAD_FOLDER = os.path.join(
        BASE_DIR,
        os.getenv("UPLOAD_FOLDER", "uploads")
    )

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    USE_CLOUDINARY = all([
        CLOUDINARY_CLOUD_NAME,
        CLOUDINARY_API_KEY,
        CLOUDINARY_API_SECRET
    ])

    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

    USE_S3 = all([
        AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY,
        S3_BUCKET_NAME
    ])

    DEBUG = os.getenv("DEBUG","False").lower() == "true"

    CORS_ORIGINS = [
        "https://nss-ssn.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]