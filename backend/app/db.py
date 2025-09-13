from pymongo import MongoClient
from app.config import MONGODB_URI, MONGODB_DB

# Connect to MongoDB
def connect_mongodb():
    try:
        client = MongoClient(MONGODB_URI)  # Make sure this is correct
        db = client[MONGODB_DB]  # Access the database
        return db["weather"]  # Return the 'weather' collection
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None