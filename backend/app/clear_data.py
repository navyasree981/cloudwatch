from datetime import datetime
from app.db import connect_postgresql, connect_mongodb

def clear_database():
    """Completely clears all weather data from both databases"""
    try:
        # Clear ALL data from PostgreSQL
        conn = connect_postgresql()
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE weather RESTART IDENTITY;")
        conn.commit()
        print("✅ PostgreSQL: All weather data deleted")
        
        # Clear ALL data from MongoDB
        collection = connect_mongodb()
        result = collection.delete_many({})
        print(f"✅ MongoDB: Deleted {result.deleted_count} weather records")
        
    except Exception as e:
        print(f"❌ Error clearing database: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            cur.close()
            conn.close()