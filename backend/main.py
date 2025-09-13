from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import logging
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.fetch_weather import fetch_weather_data, get_user_location
from app.store_data import store_weather_mongodb


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
mongo_client = MongoClient(os.getenv("MONGODB_URI"))
mongo_db = mongo_client["cloudwatch"]
mongo_collection = mongo_db["weather"]
users_collection = mongo_db["users"]
reports_collection = mongo_db["reports"]

# --- JWT Settings ---
SECRET_KEY = "key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

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
    # Always fetch fresh data from database
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

# --- Location Endpoint - Always fetch fresh data ---
@app.post("/api/send-location")
async def send_location(location: Location):
    try:
        logger.info(f"Received location: ({location.latitude}, {location.longitude})")
        
        # Always fetch fresh weather data - no cache check
        try:
            weather_data = fetch_weather_data(
                latitude=location.latitude, 
                longitude=location.longitude
            )
            if weather_data:
                success = store_weather_mongodb(weather_data)
                if success:
                    logger.info(f"Fresh weather data stored for location: ({location.latitude}, {location.longitude})")
                    return {
                        "status": "success", 
                        "message": "Location received and fresh weather data fetched.",
                        "weather": weather_data
                    }
                else:
                    logger.warning("Weather data fetched but not stored successfully")
                    return {
                        "status": "partial_success",
                        "message": "Location received, weather fetched but storage failed",
                        "weather": weather_data
                    }
            else:
                logger.warning(f"Failed to fetch weather for location: ({location.latitude}, {location.longitude})")
                return {
                    "status": "error",
                    "message": "Could not fetch weather data for this location"
                }
        except ValueError as ve:
            logger.error(f"Invalid coordinates: {ve}")
            return {
                "status": "error",
                "message": f"Invalid coordinates: {str(ve)}"
            }
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return {
                "status": "error",
                "message": f"Error fetching weather: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Error processing location: {e}")
        return {"status": "error", "message": f"Error processing location: {e}"}

# --- User Registration ---
@app.post("/api/register", response_model=User)
async def register_user(user: UserCreate):
    # Always check fresh data from database
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
        "name": location.name or f"Location {datetime.now().strftime('%H:%M:%S')}"
    }
    
    # Update user's locations in MongoDB
    users_collection.update_one(
        {"email": current_user.email},
        {"$push": {"locations": new_location}}
    )
    
    # Always fetch fresh weather data for new location
    try:
        weather_data = fetch_weather_data(
            latitude=location.latitude, 
            longitude=location.longitude
        )
        if weather_data:
            success = store_weather_mongodb(weather_data)
            if success:
                logger.info(f"Fresh weather stored for new location: {new_location['name']}")
            else:
                logger.warning(f"Weather fetched but not stored for: {new_location['name']}")
        else:
            logger.warning(f"Failed to fetch weather for new location: {new_location['name']}")
    except ValueError as ve:
        logger.error(f"Invalid coordinates for new location: {ve}")
    except Exception as e:
        logger.error(f"Error fetching initial weather: {e}")
    
    return {
        "status": "success", 
        "location": new_location,
        "reload_required": True,
        "message": "Location added successfully. Fresh weather data will be fetched."
    }

@app.get("/api/my-locations")
async def get_my_locations(current_user: User = Depends(get_current_user)):
    # Always fetch fresh data from database - no cache
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
        "reload_required": True
    }

# --- Get Weather for User Locations - Always fresh data ---
@app.get("/api/user-weather")
async def get_user_weather(current_user: User = Depends(get_current_user)):
    logger.info(f"Fetching FRESH weather data for user: {current_user.email}")
    
    # Always fetch fresh user data from database
    user = users_collection.find_one({"email": current_user.email})
    if not user:
        logger.error("User not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    locations = user.get("locations", [])
    logger.info(f"User has {len(locations)} locations - fetching fresh weather for each")
    
    weather_data = []
    
    for loc in locations:
        logger.info(f"Fetching FRESH weather for: {loc['latitude']}, {loc['longitude']}")
        
        try:
            # Always fetch fresh weather data from API - no cache check
            fresh_weather = fetch_weather_data(
                latitude=loc["latitude"], 
                longitude=loc["longitude"]
            )
            
            if fresh_weather:
                # Store the fresh data
                store_weather_mongodb(fresh_weather)
                
                timezone_offset = fresh_weather.get("timezone_offset", 0)
                logger.info(f"Fresh weather data: {fresh_weather['condition']}, {fresh_weather['temperature']}°C")
                
                weather_entry = {
                    "temperature": fresh_weather.get("temperature"),
                    "feels_like": fresh_weather.get("feels_like"),
                    "condition": fresh_weather.get("condition"),
                    "humidity": fresh_weather.get("humidity"),
                    "wind_speed": fresh_weather.get("wind_speed"),
                    "pressure": fresh_weather.get("pressure"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "timezone_offset": timezone_offset,
                    "city": fresh_weather.get("city"),
                    "country": fresh_weather.get("country")
                }
                
                weather_data.append({
                    "location": loc,
                    "weather": weather_entry
                })
            else:
                logger.warning(f"Failed to fetch fresh weather for location {loc.get('name', 'Unknown')}")
                weather_data.append({
                    "location": loc,
                    "weather": None
                })
        except Exception as e:
            logger.error(f"Error fetching fresh weather for location {loc.get('name', 'Unknown')}: {e}")
            weather_data.append({
                "location": loc,
                "weather": None
            })
    
    logger.info(f"Returning {len(weather_data)} fresh weather entries")
    return {"user_weather": weather_data}

# --- Serve Frontend HTML ---
index_file = frontend_path / "index.html"

@app.get("/")
async def get_index():
    return FileResponse(index_file)

# --- API to Get Latest Weather Data - Always fresh ---
@app.get("/api/get-latest-weather")
async def get_latest_weather(latitude: float = None, longitude: float = None):
    try:
        if not latitude or not longitude:
            raise HTTPException(status_code=400, detail="Latitude and longitude are required")

        logger.info(f"Fetching FRESH weather data for ({latitude}, {longitude})")
        
        # Always fetch fresh data from API - no cache lookup
        try:
            weather_data = fetch_weather_data(
                latitude=latitude, 
                longitude=longitude
            )
            if weather_data:
                success = store_weather_mongodb(weather_data)
                if success:
                    logger.info(f"Fresh weather data fetched and stored for ({latitude}, {longitude})")
                else:
                    logger.warning(f"Fresh weather data fetched but storage failed for ({latitude}, {longitude})")
                
                return {
                    "mongodb_weather": weather_data,
                    "timestamp": datetime.utcnow().isoformat(),
                    "fresh_data": True
                }
            else:
                return {"error": "Failed to fetch fresh weather data"}
        except ValueError as ve:
            logger.error(f"Invalid coordinates: {ve}")
            return {"error": f"Invalid coordinates: {str(ve)}"}
        except Exception as e:
            logger.error(f"Error fetching fresh weather data: {e}")
            return {"error": f"Error fetching fresh weather data: {str(e)}"}

    except Exception as e:
        logger.error(f"Error retrieving weather: {e}")
        return {"error": f"Error retrieving weather data: {str(e)}"}

# --- Debug Endpoints ---
@app.get("/api/debug")
async def debug_endpoint():
    """Return raw data from MongoDB for debugging"""
    try:
        mongo_data = mongo_collection.find_one(sort=[("timestamp", -1)])
        
        if mongo_data:
            mongo_data["_id"] = str(mongo_data["_id"])
            if isinstance(mongo_data.get("timestamp"), datetime):
                mongo_data["timestamp"] = mongo_data["timestamp"].isoformat()
                
            return {"raw_mongo_data": mongo_data}
        else:
            return {"error": "No data found in MongoDB"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/debug-user-locations")
async def debug_user_locations(current_user: User = Depends(get_current_user)):
    """Debug endpoint to check user's stored locations"""
    user = users_collection.find_one({"email": current_user.email})
    if not user:
        return {"error": "User not found"}
    
    return {
        "user_email": current_user.email,
        "locations": user.get("locations", []),
        "location_count": len(user.get("locations", [])),
        "fetched_at": datetime.utcnow().isoformat()
    }

@app.get("/api/debug-weather-data")
async def debug_weather_data():
    """Debug endpoint to check all weather data in MongoDB"""
    try:
        weather_records = list(mongo_collection.find(
            {},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10))
        
        return {
            "total_records": mongo_collection.count_documents({}),
            "recent_records": weather_records,
            "fetched_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

# --- User Profile ---
@app.get("/api/me", response_model=User)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    # Fetch fresh user data from database
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
        report_data["timestamp"] = datetime.utcnow()
        report_data["id"] = str(uuid.uuid4())
        
        result = reports_collection.insert_one(report_data)
        
        logger.info(f"📝 New report submitted with ID: {result.inserted_id}")
        return {"status": "success", "message": "Report submitted successfully", "report_id": str(result.inserted_id)}
    
    except Exception as e:
        logger.error(f"❌ Error submitting report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit report: {str(e)}"
        )

# --- Weather Alerts Endpoint - Always fresh data ---
@app.get("/api/weather-alerts")
async def get_weather_alerts(current_user: User = Depends(get_current_user)):
    try:
        # Get fresh user data from database
        user = users_collection.find_one({"email": current_user.email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        locations = user.get("locations", [])
        alerts = []
        
        # Process each location with fresh weather data
        for loc in locations:
            logger.info(f"Fetching FRESH weather for alerts: {loc.get('name')}")
            
            try:
                # Always fetch fresh weather data for alerts
                fresh_weather = fetch_weather_data(
                    latitude=loc["latitude"], 
                    longitude=loc["longitude"]
                )
                
                if not fresh_weather:
                    continue
                
                # Store fresh data
                store_weather_mongodb(fresh_weather)
                
                location_name = loc.get("name", f"Location ({loc['latitude']:.2f}, {loc['longitude']:.2f})")
                
                # Check for extreme temperatures (high)
                if fresh_weather.get("temperature") and fresh_weather["temperature"] >= 35:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "severe",
                        "title": "Extreme Heat",
                        "message": f"Temperature of {fresh_weather['temperature']}°C detected. Stay hydrated and avoid direct sun exposure."
                    })
                
                # Check for extreme temperatures (low)
                elif fresh_weather.get("temperature") and fresh_weather["temperature"] <= 0:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "moderate",
                        "title": "Freezing Temperatures",
                        "message": f"Temperature of {fresh_weather['temperature']}°C detected. Be cautious of icy surfaces and dress warmly."
                    })
                
                # Check for high humidity
                if fresh_weather.get("humidity") and fresh_weather["humidity"] >= 90:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "moderate",
                        "title": "High Humidity",
                        "message": f"Humidity level at {fresh_weather['humidity']}%. This may cause discomfort."
                    })
                
                # Check for precipitation
                if fresh_weather.get("condition"):
                    condition = fresh_weather["condition"].lower()
                    
                    if "rain" in condition or "shower" in condition or "drizzle" in condition:
                        alerts.append({
                            "location_name": location_name,
                            "severity": "normal",
                            "title": "Rain Alert",
                            "message": f"Current conditions: {fresh_weather['condition']}. Consider carrying an umbrella."
                        })
                    
                    elif "storm" in condition or "thunder" in condition or "lightning" in condition:
                        alerts.append({
                            "location_name": location_name,
                            "severity": "severe",
                            "title": "Storm Warning",
                            "message": f"Current conditions: {fresh_weather['condition']}. Take necessary precautions."
                        })
                    
                    elif "snow" in condition or "sleet" in condition or "blizzard" in condition:
                        alerts.append({
                            "location_name": location_name,
                            "severity": "moderate",
                            "title": "Snow Alert",
                            "message": f"Current conditions: {fresh_weather['condition']}. Road travel may be affected."
                        })
                
                # Check for high wind speeds
                if fresh_weather.get("wind_speed") and fresh_weather["wind_speed"] >= 30:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "moderate",
                        "title": "High Winds",
                        "message": f"Wind speed of {fresh_weather['wind_speed']} km/h detected. Secure loose outdoor items."
                    })
                
                # Check for low pressure
                if fresh_weather.get("pressure") and fresh_weather["pressure"] < 1000:
                    alerts.append({
                        "location_name": location_name,
                        "severity": "normal",
                        "title": "Low Pressure System",
                        "message": f"Atmospheric pressure of {fresh_weather['pressure']} hPa detected. Weather changes likely."
                    })
            
            except Exception as e:
                logger.error(f"Error fetching fresh weather for alerts at {loc.get('name')}: {e}")
                continue
                
        return {"alerts": alerts, "generated_at": datetime.utcnow().isoformat()}
    
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"❌ Error generating weather alerts: {e}")
        return {"error": "Could not retrieve weather alerts. Please try again later."}

# --- Current Location Weather ---
@app.get("/api/get-user-location")
async def get_current_user_location():
    """Get user's current location using IP geolocation"""
    try:
        location = get_user_location()
        if location:
            latitude, longitude = location
            return {
                "status": "success",
                "latitude": latitude,
                "longitude": longitude,
                "message": "Location detected successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Could not detect location"
            }
    except Exception as e:
        logger.error(f"Error getting user location: {e}")
        return {
            "status": "error",
            "message": f"Error detecting location: {str(e)}"
        }

@app.post("/api/weather-current-location")
async def get_weather_current_location():
    """Fetch fresh weather for user's current location"""
    try:
        # Always fetch fresh weather data
        weather_data = fetch_weather_data(use_user_location=True)
        if weather_data:
            store_weather_mongodb(weather_data)
            return {
                "status": "success",
                "weather": weather_data,
                "message": f"Fresh weather fetched for {weather_data['city']}, {weather_data['country']}",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Could not fetch weather for current location"
            }
    except Exception as e:
        logger.error(f"Error fetching weather for current location: {e}")
        return {
            "status": "error",
            "message": f"Error fetching weather: {str(e)}"
        }

# --- Manual Refresh Endpoint - Always fresh data ---
@app.post("/api/refresh-weather")
async def refresh_weather(current_user: User = Depends(get_current_user)):
    """Manually refresh weather data - always fetch fresh data from API"""
    try:
        # Get fresh user data
        user = users_collection.find_one({"email": current_user.email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        locations = user.get("locations", [])
        logger.info(f"Refreshing with FRESH weather data for {len(locations)} user locations")
        
        updated_count = 0
        failed_locations = []
        
        for location in locations:
            try:
                logger.info(f"Fetching FRESH weather for {location.get('name', 'unnamed location')} at ({location['latitude']}, {location['longitude']})")
                
                # Always fetch fresh data from API
                weather_data = fetch_weather_data(
                    latitude=location["latitude"], 
                    longitude=location["longitude"]
                )
                
                if weather_data:
                    success = store_weather_mongodb(weather_data)
                    if success:
                        updated_count += 1
                        logger.info(f"✅ Fresh weather data stored for {location.get('name', 'unnamed location')}")
                    else:
                        failed_locations.append(location.get('name', 'unnamed location'))
                        logger.warning(f"⚠️ Fresh weather fetched but not stored for {location.get('name', 'unnamed location')}")
                else:
                    failed_locations.append(location.get('name', 'unnamed location'))
                    logger.warning(f"❌ Failed to fetch fresh weather for {location.get('name', 'unnamed location')}")
            except ValueError as ve:
                failed_locations.append(location.get('name', 'unnamed location'))
                logger.error(f"❌ Invalid coordinates for location {location.get('name', 'unnamed location')}: {ve}")
            except Exception as e:
                failed_locations.append(location.get('name', 'unnamed location'))
                logger.error(f"❌ Error refreshing weather for location {location.get('name', 'unnamed location')}: {e}")
        
        message = f"Fresh weather data fetched for {updated_count} out of {len(locations)} locations"
        if failed_locations:
            message += f". Failed: {', '.join(failed_locations[:3])}"
        
        return {
            "status": "success",
            "message": message,
            "updated_locations": updated_count,
            "total_locations": len(locations),
            "failed_locations": failed_locations if failed_locations else None,
            "refresh_timestamp": datetime.utcnow().isoformat(),
            "fresh_data": True
        }
    
    except Exception as e:
        logger.error(f"❌ Error during manual weather refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh weather data: {str(e)}"
        )

# --- City Search ---
@app.get("/api/search-cities")
async def search_cities(q: str, current_user: User = Depends(get_current_user)):
    """Search for cities using OpenWeatherMap API"""
    try:
        if len(q.strip()) < 3:
            return {"cities": []}
            
        API_KEY = os.getenv("OPENWEATHER_API_KEY", "fb23af25eda4f16a60eb16a48f7ca7e8")
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://api.openweathermap.org/geo/1.0/direct?q={q}&limit=5&appid={API_KEY}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {"cities": data}
                else:
                    logger.error(f"OpenWeather API error: {response.status}")
                    return {"cities": [], "error": "Failed to search cities"}
                    
    except Exception as e:
        logger.error(f"City search error: {e}")
        return {"cities": [], "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)