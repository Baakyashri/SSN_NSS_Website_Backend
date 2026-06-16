import os
from pymongo import MongoClient
#from config import MONGO_URI
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "nss_portal")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    db = client[DB_NAME]  #your DB name
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    # Create a mock database object for development
    class MockDB:
        def __getattr__(self, name):
            return MockCollection()
        
        def __getitem__(self, name):
            # Handles db['collection_name'] <--- THIS WAS MISSING
            return MockCollection()
        
    class MockCollection:
        def find_one(self, *args, **kwargs):
            return None
        def find(self, *args, **kwargs):
            return []
        def insert_one(self, *args, **kwargs):
            return type('Result', (), {'inserted_id': 'mock_id'})()
        def update_one(self, *args, **kwargs):
            return type('Result', (), {'modified_count': 1})()
    
    db = MockDB()
    logger.warning("Using mock database - MongoDB connection failed") 
