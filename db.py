import os
import logging
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

load_dotenv()
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "nss_portal")


class Database:
    _client = None
    _db = None

    @classmethod
    def connect(cls):
        if cls._db:
            return cls._db

        if not MONGO_URI:
            raise ValueError("MONGO_URI environment variable is not set")

        try:
            cls._client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=5,
                retryWrites=True,
            )

            cls._client.admin.command("ping")

            cls._db = cls._client[DB_NAME]

            logger.info("MongoDB connection established")

            return cls._db

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.exception("MongoDB connection failed")
            raise RuntimeError("Database unavailable") from e

    @classmethod
    def get_db(cls):
        if cls._db is None:
            return cls.connect()
        return cls._db

    @classmethod
    def close(cls):
        if cls._client:
            cls._client.close()
            logger.info("MongoDB connection closed")


db = Database.get_db()