import requests
from datetime import datetime, timezone, timedelta
from app.store_data import store_weather_mongodb

API_KEY = "fb23af25eda4f16a60eb16a48f7ca7e8"

def get_user_location():
    """
    Get user's location using IP-based geolocation
    Returns tuple (latitude, longitude) or None if failed
    """
    try:
        # Using ipapi.co for IP-based geolocation (free service)
        response = requests.get("https://ipapi.co/json/", timeout=10)
        
        if response.status_code == 200:
            location_data = response.json()
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")
            
            if latitude is not None and longitude is not None:
                print(f"📍 Detected location: {location_data.get('city', 'Unknown')}, {location_data.get('country_name', 'Unknown')}")
                return float(latitude), float(longitude)
        
        print("⚠️ Could not detect location from IP")
        return None
        
    except Exception as e:
        print(f"❗ Error getting user location: {str(e)}")
        return None

def fetch_weather_data(latitude: float = None, longitude: float = None, use_user_location: bool = False):
    """
    Fetch weather data for given coordinates or user's current location
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate  
        use_user_location: If True, automatically detect user's location
    
    Returns:
        dict: Weather data or None if failed
    """
    
    # Get user location if requested
    if use_user_location or (latitude is None or longitude is None):
        location = get_user_location()
        if location:
            latitude, longitude = location
        elif latitude is None or longitude is None:
            print("❗ No coordinates provided and couldn't detect user location")
            return None
    
    # Validate coordinates
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValueError(f"Invalid coordinates: {latitude}, {longitude}")
    
    try:
        # Get weather data
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
        weather_response = requests.get(weather_url, timeout=10)

        if weather_response.status_code != 200:
            print(f"Error fetching weather data: {weather_response.status_code}")
            return None

        weather = weather_response.json()

        # Extract timezone offset (seconds)
        timezone_offset = weather.get("timezone", 0)

        # Base weather data
        weather_info = {
            "latitude": weather.get("coord", {}).get("lat"),
            "longitude": weather.get("coord", {}).get("lon"),
            "city": weather.get("name", "Unknown"),
            "country": weather.get("sys", {}).get("country", "Unknown"),
            "condition": weather.get("weather", [{}])[0].get("main", "Unknown"),
            "description": weather.get("weather", [{}])[0].get("description", ""),
            "temperature": weather.get("main", {}).get("temp"),
            "feels_like": weather.get("main", {}).get("feels_like"),
            "humidity": weather.get("main", {}).get("humidity"),
            "pressure": weather.get("main", {}).get("pressure"),
            "wind_speed": weather.get("wind", {}).get("speed"),
            "wind_direction": weather.get("wind", {}).get("deg"),
            "timestamp": datetime.fromtimestamp(weather.get("dt", 0), tz=timezone.utc),
            "timezone_offset": timezone_offset,
        }

        # Get AQI data
        aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={latitude}&lon={longitude}&appid={API_KEY}"
        aqi_response = requests.get(aqi_url, timeout=10)
        
        if aqi_response.status_code == 200:
            aqi_data = aqi_response.json()
            weather_info["aqi"] = aqi_data.get("list", [{}])[0].get("main", {}).get("aqi")
        else:
            print(f"AQI API error: {aqi_response.status_code}")
            weather_info["aqi"] = None

        return weather_info

    except Exception as e:
        print(f"Fetch error: {str(e)}")
        return None

def insert_weather_data(data):
    """
    Store weather data in MongoDB (updated from PostgreSQL)
    Maintains the same function name for backward compatibility
    """
    return store_weather_mongodb(data)

def fetch_weather_postgresql():
    """
    Fetch latest weather data from MongoDB (updated from PostgreSQL)
    Maintains the same function name for backward compatibility
    """
    try:
        from app.db import connect_mongodb
        
        collection = connect_mongodb()
        if collection is None:
            print("❗ Could not connect to MongoDB")
            return None
        
        # Get latest weather record
        latest = collection.find().sort("timestamp", -1).limit(1)
        latest_record = next(latest, None)
        
        if latest_record:
            # Convert timezone offset to proper timezone for display
            local_time = latest_record["timestamp"].astimezone(
                timezone(timedelta(seconds=latest_record.get("timezone_offset", 0)))
            )
            
            print(f"🌤️ Latest weather in {latest_record['city']}, {latest_record['country']}:")
            print(f"  Temperature: {latest_record['temperature']}°C")
            print(f"  Condition: {latest_record['condition']} ({latest_record['description']})")
            print(f"  Recorded at: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            return latest_record
        else:
            print("📭 No weather records found in database")
            return None
            
    except Exception as e:
        print(f"❗ Database read error: {str(e)}")
        return None