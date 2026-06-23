from pymongo import MongoClient
from config import Config

client = MongoClient(Config.MONGO_URI)

db = client.get_database()


users_collection = db['users']
albums_collection = db["albums"]
activities_collection = db['activities']
announcements_collection = db['announcements']
registrations_collection = db['registrations']