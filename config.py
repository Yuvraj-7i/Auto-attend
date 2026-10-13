import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.getenv("SECRET_KEY", "autoattend-secret-key-2026")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")
    PORT = int(os.getenv("PORT", 5000))

    # Database settings
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
    DB_NAME = os.getenv("DB_NAME", "autoattend_db")
    SQLITE_PATH = os.path.join(os.path.dirname(__file__), "database", "autoattend.db")

    # Camera & Face Recognition defaults
    CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", 0))
    FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", 0.65))
    MIN_OBSERVATIONS = int(os.getenv("MIN_OBSERVATIONS", 3))
    FRAME_CAPTURE_INTERVAL = float(os.getenv("FRAME_CAPTURE_INTERVAL", 1.5))
    DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

    # File Uploads & Biometrics
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    FACE_EMBEDDINGS_FOLDER = os.path.join(os.path.dirname(__file__), "database", "embeddings")
