from datetime import datetime
from app.db import connect_mongodb

def clear_database():
    """Completely clears all weather data from MongoDB"""
    try:
        # Clear ALL data from MongoDB
        collection = connect_mongodb()
        
        if collection is None:
            raise ValueError("MongoDB collection not available")
        
        result = collection.delete_many({})
        print(f"✅ MongoDB: Deleted {result.deleted_count} weather records")
        
        return result.deleted_count
        
    except Exception as e:
        print(f"❌ Error clearing database: {str(e)}")
        raise