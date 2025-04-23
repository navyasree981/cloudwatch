import psycopg2
from pymongo import MongoClient
from backend.app.config import POSTGRES_URI, MONGODB_URI, MONGODB_DB

# Connect to PostgreSQL with PostGIS
def connect_postgresql():
    try:
        conn = psycopg2.connect(POSTGRES_URI)
        return conn
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

# Connect to MongoDB
def connect_mongodb():
    try:
        client = MongoClient(MONGODB_URI)  # Make sure this is correct
        db = client[MONGODB_DB]  # Access the database
        return db["weather"]  # Return the 'weather' collection
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None