from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from pathlib import Path
import os

# Commented out scheduler imports - only reload when user presses reload
# import schedule
# import time
# import threading
import logging
# import psycopg2  # Removed PostgreSQL dependency
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.fetch_weather import fetch_weather_data
# from app.store_data import store_weather_postgresql, store_weather_mongodb  # Modified below
from app.store_data import store_weather_mongodb
from app.clear_data import clear_database

# from urllib.parse import urlparse  # Removed PostgreSQL URL parsing

# POSTGRES_URI = os.getenv("POSTGRES_URI")  # Removed PostgreSQL URI
# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static Files Mounting ---
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

# --- MongoDB Setup ---
mongo_client = MongoClient(os.getenv("MONGODB_URI"))  # Change with your MongoDB URI
mongo_db = mongo_client["cloudwatch"]  # Replace with your database name
mongo_collection = mongo_db["weather"]  # Replace with your collection name
users_collection = mongo_db["users"]  # Collection for user data
reports_collection = mongo_db["reports"]  # Collection for user reports

# --- JWT Settings ---
SECRET_KEY = "key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

# --- Global Variable to Store Latest Location (Commented - no cache) ---
# latest_location = None

# --- Models ---
class Location(BaseModel):
    latitude: float
    longitude: float
    name: Optional[str] = None

class UserLocation(BaseModel):
    id: str
    latitude: float
    longitude: float
    name: Optional[str] = None

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class User(BaseModel):
    id: str
    name: str
    email: str
    locations: List[UserLocation] = []

class UserInDB(BaseModel):
    id: str
    name: str
    email: str
    hashed_password: str
    locations: List[UserLocation] = []

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ReportBase(BaseModel):
    report_type: str
    description: str
    email: Optional[str] = None
    location: Optional[str] = None
    
class WeatherReport(ReportBase):
    weather_condition: Optional[str] = None
    actual_weather: Optional[str] = None
    predicted_weather: Optional[str] = None
    date_of_issue: Optional[str] = None

class AppReport(ReportBase):
    device_type: Optional[str] = None
    operating_system: Optional[str] = None
    app_version: Optional[str] = None
    steps_to_reproduce: Optional[str] = None

class OtherReport(ReportBase):
    report_category: Optional[str] = None
    subject: Optional[str] = None

# --- Helper Functions ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_user_by_email(email: str):
    user = users_collection.find_one({"email": email})
    if user:
        return UserInDB(**user)
    return None

async def authenticate_user(email: str, password: str):
    user = await get_user_by_email(email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = await get_user_by_email(email=token_data.email)
    if user is None:
        raise credentials_exception
    return user

# --- Location Endpoint (Commented - no global cache) ---
@app.post("/api/send-location")
async def send_location(location: Location):
    # global latest_location  # Commented out global cache
    try:
        # latest_location = (location.latitude, location.longitude)  # Commented out cache
        logger.info(f"📍 Received location: ({location.latitude}, {location.longitude})")
        
        # Fetch and store weather data immediately without caching
        try:
            weather_data = fetch_weather_data(location.latitude, location.longitude)
            if weather_data:
                store_weather_mongodb(weather_data)  # Only MongoDB now
                logger.info(f"🌦️ Weather data stored for location: ({location.latitude}, {location.longitude})")
            else:
                logger.warning(f"⚠️ Failed to fetch weather for location: ({location.latitude}, {location.longitude})")
        except Exception as e:
            logger.error(f"❌ Error fetching weather: {e}")
        
        return {"status": "success", "message": "Location received and weather data fetched."}
    except Exception as e:
        logger.error(f"❌ Error processing location: {e}")
        return {"status": "error", "message": f"Error processing location: {e}"}

# --- User Registration ---
@app.post("/api/register", response_model=User)
async def register_user(user: UserCreate):
    db_user = await get_user_by_email(user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user.password)
    
    user_dict = {
        "id": user_id,
        "name": user.name,
        "email": user.email,
        "hashed_password": hashed_password,
        "locations": []
    }
    
    users_collection.insert_one(user_dict)
    
    # Return the user without the hashed password
    return User(
        id=user_id,
        name=user.name,
        email=user.email,
        locations=[]
    )

# --- User Login ---
@app.post("/api/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Location Management ---
@app.post("/api/add-location")
async def add_location(location: Location, current_user: User = Depends(get_current_user)):
    location_id = str(uuid.uuid4())
    new_location = {
        "id": location_id,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "name": location.name or f"Location {len(current_user.locations) + 1}"
    }
    
    # Update user's locations in MongoDB
    users_collection.update_one(
        {"email": current_user.email},
        {"$push": {"locations": new_location}}
    )
    
    # Immediately fetch and store weather data for the new location
    try:
        weather_data = fetch_weather_data(location.latitude, location.longitude)
        if weather_data:
            store_weather_mongodb(weather_data)  # Only MongoDB now
            logger.info(f"🌦️ Immediately stored weather for new location: {new_location['name']}")
        else:
            logger.warning(f"⚠️ Failed to fetch weather for new location: {new_location['name']}")
    except Exception as e:
        logger.error(f"❌ Error fetching initial weather: {e}")
    
    # Return success with reload instruction for frontend
    return {
        "status": "success", 
        "location": new_location,
        "reload_required": True,  # Signal frontend to reload page
        "message": "Location added successfully. Page will reload to show updated data."
    }

@app.get("/api/my-locations")
async def get_my_locations(current_user: User = Depends(get_current_user)):
    # Always fetch fresh data from database - no caching
    user = users_collection.find_one({"email": current_user.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"locations": user.get("locations", [])}

@app.delete("/api/delete-location/{location_id}")
async def remove_location(location_id: str, current_user: User = Depends(get_current_user)):
    result = users_collection.update_one(
        {"email": current_user.email},
        {"$pull": {"locations": {"id": location_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Location not found")
    
    return {
        "status": "success", 
        "message": "Location removed",
        "reload_required": True  # Signal frontend to reload page
    }

# --- Get Weather for User Locations ---
@app.get("/api/user-weather")
async def get_user_weather(current_user: User = Depends(get_current_user)):
    print(f"Fetching weather for user: {current_user.email}")
    
    # Always fetch fresh user data - no caching
    user = users_collection.find_one({"email": current_user.email})
    if not user:
        print("User not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    locations = user.get("locations", [])
    print(f"User has {len(locations)} locations: {locations}")
    
    weather_data = []
    
    for loc in locations:
        print(f"Looking for weather at: {loc['latitude']}, {loc['longitude']}")
        
        # Find the latest weather data for this location using a range query - no caching
        latest_weather = mongo_collection.find_one(
            {
                "latitude": {"$gte": loc["latitude"] - 0.001, "$lte": loc["latitude"] + 0.001},
                "longitude": {"$gte": loc["longitude"] - 0.001, "$lte": loc["longitude"] + 0.001}
            },
            sort=[("timestamp", -1)]
        )
        
        if latest_weather:
            timezone_offset = latest_weather.get("timezone_offset", 0)
            utc_timestamp = latest_weather["timestamp"]
            local_timestamp = utc_timestamp + timedelta(seconds=timezone_offset)
            print(f"Found weather data: {latest_weather['condition']}, {latest_weather['temperature']}°C")
            weather_entry = {
                "temperature": latest_weather.get("temperature"),
                "feels_like": latest_weather.get("feels_like"),
                "condition": latest_weather.get("condition"),
                "humidity": latest_weather.get("humidity"),
                "wind_speed": latest_weather.get("wind_speed"),
                "pressure": latest_weather.get("pressure"),
                "timestamp": latest_weather["timestamp"].isoformat(),  # UTC time
                "timezone_offset": latest_weather.get("timezone_offset", 0)
                }
            
            weather_data.append({
                "location": loc,
                "weather": weather_entry
            })
        else:
            print(f"No weather data found for location")
    
    print(f"Returning {len(weather_data)} weather entries")
    return {"user_weather": weather_data}

# --- Scheduled Weather Fetch & Store Job (COMMENTED OUT) ---
# def scheduled_job():
#     try:
#         all_users = users_collection.find({})
#         processed_locations = set()
#         
#         for user in all_users:
#             for location in user.get("locations", []):
#                 loc_key = (location["latitude"], location["longitude"])
#                 if loc_key in processed_locations:
#                     continue
#                     
#                 processed_locations.add(loc_key)
#                 
#                 try:
#                     weather_data = fetch_weather_data(*loc_key)
#                     if weather_data:
#                         store_weather_mongodb(weather_data)  # Only MongoDB now
#                         logger.info(f"✅ Scheduled update for {location.get('name', 'unnamed location')}")
#                     else:
#                         logger.warning(f"⚠️ Scheduled update failed for {loc_key}")
#                 except Exception as e:
#                     logger.error(f"❌ Scheduled job error for {loc_key}: {str(e)}")
#         
#     except Exception as e:
#         logger.error(f"❌ Global scheduled job error: {str(e)}")

# --- Scheduler Thread (COMMENTED OUT) ---
# def run_scheduler():
#     # Update weather every hour
#     schedule.every(30).minutes.do(scheduled_job)
#     schedule.every().day.at("00:00").do(clear_database)
#     logger.info("🕒 Scheduler started...")
#     while True:
#         schedule.run_pending()
#         time.sleep(1)

# threading.Thread(target=run_scheduler, daemon=True).start()

# --- Serve Frontend HTML ---
index_file = frontend_path / "index.html"

@app.get("/")
async def get_index():
    return FileResponse(index_file)

# --- API to Get Latest Weather Data (Modified - no PostgreSQL) ---
@app.get("/api/get-latest-weather")
async def get_latest_weather(latitude: float = None, longitude: float = None):
    try:
        if not latitude or not longitude:
            raise HTTPException(status_code=400, detail="Latitude and longitude are required")

        # --- Fetch Weather Data from MongoDB Only ---
        mongo_data = None
        try:
            latest_weather_mongo = mongo_collection.find_one(
                {
                    "latitude": {"$gte": latitude - 0.01, "$lte": latitude + 0.01},
                    "longitude": {"$gte": longitude - 0.01, "$lte": longitude + 0.01}
                },
                sort=[("timestamp", -1)]
            )

            if latest_weather_mongo:
                timezone_offset = latest_weather_mongo.get("timezone_offset", 0)
                utc_timestamp = latest_weather_mongo["timestamp"]
                local_timestamp = utc_timestamp + timedelta(seconds=timezone_offset)
                latest_weather_mongo["timestamp"] = local_timestamp.isoformat()

                if "_id" in latest_weather_mongo:
                    latest_weather_mongo["_id"] = str(latest_weather_mongo["_id"])

                if "timestamp" in latest_weather_mongo and isinstance(latest_weather_mongo["timestamp"], datetime):
                    latest_weather_mongo["timestamp"] = latest_weather_mongo["timestamp"].isoformat()

                mongo_data = latest_weather_mongo
                logger.info(f"🌦️ Retrieved weather from MongoDB for {mongo_data.get('city', 'Unknown')}")
            else:
                logger.warning("⚠️ No weather data found in MongoDB")
        except Exception as e:
            logger.error(f"❌ Error retrieving weather from MongoDB: {e}")

        if not mongo_data:
            # If no data found, fetch fresh data
            try:
                weather_data = fetch_weather_data(latitude, longitude)
                if weather_data:
                    store_weather_mongodb(weather_data)
                    # Convert the fresh data to the expected format
                    mongo_data = weather_data
                    logger.info(f"🌦️ Fetched fresh weather data for ({latitude}, {longitude})")
            except Exception as e:
                logger.error(f"❌ Error fetching fresh weather data: {e}")
                return {"error": "No weather data available and failed to fetch fresh data"}

        return {
            "mongodb_weather": mongo_data
        }

    except Exception as e:
        logger.error(f"❌ Error retrieving weather: {e}")
        return {"error": f"Error retrieving weather data: {str(e)}"}

@app.get("/api/debug")
async def debug_endpoint():
    """Return raw data from MongoDB for debugging"""
    try:
        # Get the latest record from MongoDB
        mongo_data = mongo_collection.find_one(sort=[("timestamp", -1)])
        
        if mongo_data:
            # Convert ObjectId to string
            mongo_data["_id"] = str(mongo_data["_id"])
            # Convert datetime to string if needed
            if isinstance(mongo_data.get("timestamp"), datetime):
                mongo_data["timestamp"] = mongo_data["timestamp"].isoformat()
                
            return {"raw_mongo_data": mongo_data}
        else:
            return {"error": "No data found in MongoDB"}
    except Exception as e:
        return {"error": str(e)}

# --- User Profile ---
@app.get("/api/me", response_model=User)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    # Fetch fresh user data - no caching
    user = users_collection.find_one({"email": current_user.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        locations=user.get("locations", [])
    )

# --- Report Endpoints ---
@app.post("/api/submit-report")
async def submit_report(report_data: Dict[str, Any]):
    try:
        # Add timestamp to the report
        report_data["timestamp"] = datetime.utcnow()
        
        # Add a unique ID
        report_data["id"] = str(uuid.uuid4())
        
        # Insert the report into MongoDB
        result = reports_collection.insert_one(report_data)
        
        logger.info(f"📝 New report submitted with ID: {result.inserted_id}")
        return {"status": "success", "message": "Report submitted successfully", "report_id": str(result.inserted_id)}
    
    except Exception as e:
        logger.error(f"❌ Error submitting report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit report: {str(e)}"
        )
        
# --- Weather Alerts Endpoint ---
@app.get("/api/weather-alerts")
async def get_weather_alerts(current_user: User = Depends(get_current_user)):
    try:
        # Get user's locations - fetch fresh data
        user = users_collection.find_one({"email": current_user.email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        locations = user.get("locations", [])
        alerts = []
        
        # Process each location
        for loc in locations:
            # Find the latest weather data for this location - no caching
            latest_weather = mongo_collection.find_one(
                {
                    "latitude": {"$gte": loc["latitude"] - 0.001, "$lte": loc["latitude"] + 0.001},
                    "longitude": {"$gte": loc["longitude"] - 0.001, "$lte": loc["longitude"] + 0.001}
                },
                sort=[("timestamp", -1)]
            )
            
            if not latest_weather:
                continue
                
            location_name = loc.get("name", f"Location ({loc['latitude']:.2f}, {loc['longitude']:.2f})")
            
            # Check for extreme temperatures (high)
            if latest_weather.get("temperature") and latest_weather["temperature"] >= 35:
                alerts.append({
                    "location_name": location_name,
                    "severity": "severe",
                    "title": "Extreme Heat",
                    "message": f"Temperature of {latest_weather['temperature']}°C detected. Stay hydrated and avoid direct sun exposure."
                })
            
            # Check for extreme temperatures (low)
            elif latest_weather.get("temperature") and latest_weather["temperature"] <= 0:
                alerts.append({
                    "location_name": location_name,
                    "severity": "moderate",
                    "title": "Freezing Temperatures",
                    "message": f"Temperature of {latest_weather['temperature']}°C detected. Be cautious of icy surfaces and dress warmly."
                })
            
            # Check for high humidity
            if latest_weather.get("humidity") and latest_weather["humidity"] >= 90:
                alerts.append({
                    "location_name": location_name,
                    "severity": "moderate",
                    "title": "High Humidity",
                    "message": f"Humidity level at {latest_weather['humidity']}%. This may cause discomfort."
                })
            
            # Check for precipitation (rain, snow, etc.)
            if latest_weather.get("condition"):
                condition = latest_weather["condition"].lower()
                
                # Check for rain conditions
                if "rain" in condition or "shower" in condition or "drizzle" in condition:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "normal",
                        "title": "Rain Alert",
                        "message": f"Current conditions: {latest_weather['condition']}. Consider carrying an umbrella."
                    })
                
                # Check for storm conditions
                elif "storm" in condition or "thunder" in condition or "lightning" in condition:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "severe",
                        "title": "Storm Warning",
                        "message": f"Current conditions: {latest_weather['condition']}. Take necessary precautions."
                    })
                
                # Check for snow conditions
                elif "snow" in condition or "sleet" in condition or "blizzard" in condition:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "moderate",
                        "title": "Snow Alert",
                        "message": f"Current conditions: {latest_weather['condition']}. Road travel may be affected."
                    })
            
            # Check for high wind speeds
            if latest_weather.get("wind_speed") and latest_weather["wind_speed"] >= 30:
                alerts.append({
                    "location_name": location_name,
                    "severity": "moderate",
                    "title": "High Winds",
                    "message": f"Wind speed of {latest_weather['wind_speed']} km/h detected. Secure loose outdoor items."
                })
            
            # Check for low pressure (potential for storms)
            if latest_weather.get("pressure") and latest_weather["pressure"] < 1000:
                alerts.append({
                    "location_name": location_name,
                    "severity": "normal",
                    "title": "Low Pressure System",
                    "message": f"Atmospheric pressure of {latest_weather['pressure']} hPa detected. Weather changes likely."
                })
                
        return {"alerts": alerts}
    
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"❌ Error generating weather alerts: {e}")
        return {"error": "Could not retrieve weather alerts. Please try again later."}

# --- Manual Refresh Endpoint ---
@app.post("/api/refresh-weather")
async def refresh_weather(current_user: User = Depends(get_current_user)):
    """Manually refresh weather data for all user locations when user presses reload"""
    try:
        user = users_collection.find_one({"email": current_user.email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        locations = user.get("locations", [])
        updated_count = 0
        
        for location in locations:
            try:
                weather_data = fetch_weather_data(location["latitude"], location["longitude"])
                if weather_data:
                    store_weather_mongodb(weather_data)
                    updated_count += 1
                    logger.info(f"✅ Refreshed weather for {location.get('name', 'unnamed location')}")
                else:
                    logger.warning(f"⚠️ Failed to refresh weather for {location.get('name', 'unnamed location')}")
            except Exception as e:
                logger.error(f"❌ Error refreshing weather for location {location.get('name', 'unnamed location')}: {e}")
        
        return {
            "status": "success",
            "message": f"Weather data refreshed for {updated_count} out of {len(locations)} locations",
            "updated_locations": updated_count
        }
    
    except Exception as e:
        logger.error(f"❌ Error during manual weather refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh weather data: {str(e)}"
        )
 
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))  # Render injects $PORT, default 8000 locally
    uvicorn.run("main:app", host="0.0.0.0", port=port)

# --- Removed PostgreSQL test endpoint ---
# @app.get("/test-pg") - Removed completely