import requests
from datetime import datetime, timezone, timedelta
import psycopg2

API_KEY = "fb23af25eda4f16a60eb16a48f7ca7e8"

def fetch_weather_data(latitude: float, longitude: float):
    
    # Validate coordinates first
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValueError(f"Invalid coordinates: {latitude}, {longitude}")
    # Rest of your function...
    try:
        # Get weather data
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
        weather_response = requests.get(weather_url)

        if weather_response.status_code != 200:
            print(f"Error fetching weather data: {weather_response.status_code}")
            return None

        weather = weather_response.json()

        # Extract timezone offset (seconds)
        timezone_offset = weather.get("timezone", 0)  # Critical addition

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
            "timezone_offset": timezone_offset,  # Added here
        }

        # Get AQI data
        aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={latitude}&lon={longitude}&appid={API_KEY}"
        aqi_response = requests.get(aqi_url)
        
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
    try:
        conn = psycopg2.connect("postgresql://postgres:Jungkook1!@localhost:5432/cloudwatch")
        cur = conn.cursor()

        # Updated query with timezone_offset
        query = """
        INSERT INTO weather (
            city, country, latitude, longitude, condition, description,
            temperature, feels_like, humidity, pressure, wind_speed, wind_direction,
            aqi, timezone_offset, timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values = (
            data["city"],
            data["country"],
            data["latitude"],
            data["longitude"],
            data["condition"],
            data["description"],
            data["temperature"],
            data["feels_like"],
            data["humidity"],
            data["pressure"],
            data["wind_speed"],
            data["wind_direction"],
            data["aqi"],
            data["timezone_offset"],  # New field
            data["timestamp"]
        )

        cur.execute(query, values)
        conn.commit()
        print("✅ Weather data inserted successfully")

    except psycopg2.Error as e:
        print(f"❗ Database error: {str(e)}")
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

def fetch_weather_postgresql():
    try:
        conn = psycopg2.connect("postgresql://postgres:Jungkook1!@localhost:5432/cloudwatch")
        cur = conn.cursor()
        cur.execute("""
            SELECT city, country, temperature, timestamp, timezone_offset 
            FROM weather ORDER BY timestamp DESC LIMIT 1
        """)
        
        latest = cur.fetchone()
        if latest:
            print(f"🌤️ Latest weather in {latest[0]}, {latest[1]}:")
            print(f"  Temperature: {latest[2]}°C")
            print(f"  Recorded at: {latest[3].astimezone(timezone.utc + timedelta(seconds=latest[4]))}")
        
    except psycopg2.Error as e:
        print(f"❗ Database read error: {str(e)}")
    finally:
        if conn:
            cur.close()
            conn.close()