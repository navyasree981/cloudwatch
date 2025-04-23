from datetime import datetime, timezone
from backend.app.db import connect_postgresql, connect_mongodb


def store_weather_postgresql(weather):

    # Connect to PostgreSQL database
    conn = connect_postgresql()
    cur = conn.cursor()
    
    # SQL query to insert weather data
    query = """
    INSERT INTO weather (
        city, country, latitude, longitude, condition, description,
        temperature, feels_like, humidity, pressure, wind_speed, wind_direction,
        aqi, timezone_offset, timestamp
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    # Data to be inserted into the table
    data = (
        weather.get('city'),
        weather.get('country'),
        weather.get('latitude'),
        weather.get('longitude'),
        weather.get('condition'),
        weather.get('description'),
        weather.get('temperature'),
        weather.get('feels_like'),
        weather.get('humidity'),
        weather.get('pressure'),
        weather.get('wind_speed'),
        weather.get('wind_direction'),
        weather.get('aqi'),
        weather.get('timezone_offset', 0),  # Default to 0 if missing
        weather.get('timestamp', datetime.utcnow())  # Ensure UTC timestamp
    )
    
    try:
        # Execute the insert query
        cur.execute(query, data)
        conn.commit()
        print("✅ Stored into PostgreSQL successfully")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error storing in PostgreSQL: {str(e)}")
    finally:
        cur.close()
        conn.close()

def store_weather_mongodb(weather):
    try:
        # Connect to MongoDB
        collection = connect_mongodb()
        
        if collection is None:
            raise ValueError("MongoDB collection not available")

        # Create document with safety checks
        document = {
            "city": weather.get('city', 'Unknown'),
            "country": weather.get('country', 'Unknown'),
            "latitude": weather.get('latitude', 0.0),
            "longitude": weather.get('longitude', 0.0),
            "condition": weather.get('condition', 'Unknown'),
            "description": weather.get('description', 'No description'),
            "temperature": weather.get('temperature', 0.0),
            "feels_like": weather.get('feels_like', 0.0),
            "humidity": weather.get('humidity', 0),
            "pressure": weather.get('pressure', 0),
            "wind_speed": weather.get('wind_speed', 0.0),
            "wind_direction": weather.get('wind_direction', 0),
            "aqi": weather.get('aqi', 0),
            "timezone_offset": weather.get('timezone_offset', 0),  # Critical addition
            "timestamp": weather.get('timestamp', datetime.now(timezone.utc))
        }

        # Insert with acknowledgement
        result = collection.insert_one(document)
        
        if result.acknowledged:
            print(f"✅ Stored into MongoDB successfully (ID: {result.inserted_id})")
            return True
            
        print("❌ MongoDB insertion not acknowledged")
        return False

    except Exception as e:
        print(f"🔥 Error storing in MongoDB: {str(e)}")
        return False