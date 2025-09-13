from datetime import datetime, timezone
from app.db import connect_mongodb

def store_weather_mongodb(weather):
    try:
        # Connect to MongoDB
        collection = connect_mongodb()
        
        if collection is None:
            raise ValueError("MongoDB collection not available")

        # Create document with safety checks and better type handling
        document = {
            "city": weather.get('city', 'Unknown'),
            "country": weather.get('country', 'Unknown'),
            "latitude": float(weather.get('latitude', 0.0)) if weather.get('latitude') is not None else 0.0,
            "longitude": float(weather.get('longitude', 0.0)) if weather.get('longitude') is not None else 0.0,
            "condition": weather.get('condition', 'Unknown'),
            "description": weather.get('description', 'No description'),
            "temperature": float(weather.get('temperature', 0.0)) if weather.get('temperature') is not None else 0.0,
            "feels_like": float(weather.get('feels_like', 0.0)) if weather.get('feels_like') is not None else 0.0,
            "humidity": int(weather.get('humidity', 0)) if weather.get('humidity') is not None else 0,
            "pressure": int(weather.get('pressure', 0)) if weather.get('pressure') is not None else 0,
            "wind_speed": float(weather.get('wind_speed', 0.0)) if weather.get('wind_speed') is not None else 0.0,
            "wind_direction": int(weather.get('wind_direction', 0)) if weather.get('wind_direction') is not None else 0,
            "aqi": int(weather.get('aqi', 0)) if weather.get('aqi') is not None else 0,
            "timezone_offset": int(weather.get('timezone_offset', 0)),  # Critical addition
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