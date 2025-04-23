window.onload = function () {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(success, error);
  } else {
    showLocationError("Geolocation is not supported by this browser.");
  }
};

let hasInitialData = false;

function success(position) {
  const latitude = position.coords.latitude;
  const longitude = position.coords.longitude;

  fetch("/api/send-location", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude, longitude }),
  })
    .then(handleResponse)
    .then(fetchWeatherData)
    .catch(handleLocationError);
}

function fetchWeatherData() {
  fetch("/api/get-latest-weather")
    .then(handleResponse)
    .then((data) => {
      updateWeatherDisplay(data);
      if (!hasInitialData) {
        hasInitialData = true;
        document.getElementById("forecast-details").textContent =
          "Current weather information";
      }
    })
    .catch(handleWeatherError);
}

function updateWeatherDisplay(data) {
  const weather = data.mongodb_weather || data.postgresql_weather;
  if (!weather) return;

  // Get timezone offset from weather data (default to 0 if missing)
  const tzOffset = weather.timezone_offset || 0;

  document.getElementById(
    "location-name"
  ).textContent = `${weather.city}, ${weather.country}`;
  document.getElementById(
    "last-updated"
  ).textContent = `Last updated: ${formatTimestamp(
    weather.timestamp,
    tzOffset
  )}`;

  document.getElementById("weather-icon").className = getWeatherIcon(
    weather.condition
  );

  document.getElementById("forecast-details").innerHTML = `
    ${weather.condition} (${weather.description})<br>
    Temperature: ${weather.temperature}°C<br>
    Feels like: ${weather.feels_like}°C
  `;

  document.getElementById(
    "humidity-value"
  ).textContent = `${weather.humidity}%`;
  document.getElementById(
    "wind-value"
  ).textContent = `${weather.wind_speed} m/s`;

  const aqiElement = document.getElementById("aqi-value");
  aqiElement.textContent = weather.aqi || "--";
  aqiElement.className = `info-value aqi-${weather.aqi || "unknown"}`;
}

// Updated time formatting with timezone offset
function formatTimestamp(isoString, offsetSeconds) {
  try {
    const utcDate = new Date(isoString);
    const localTime = new Date(utcDate.getTime() + offsetSeconds * 1000);

    return localTime.toLocaleString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      month: "short",
      day: "numeric",
      timeZone: "UTC", // Use UTC to prevent browser timezone interference
    });
  } catch (e) {
    console.error("Time formatting error:", e);
    return "N/A";
  }
}

// Error handling remains the same
function error(err) {
  const messages = {
    1: "Location access denied. Please enable permissions",
    2: "Location unavailable",
    3: "Location request timed out",
  };
  showLocationError(messages[err.code] || "Error getting location");
}

function handleResponse(response) {
  if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
  return response.json();
}

function handleWeatherError(error) {
  console.error("Weather fetch error:", error);
  document.getElementById("forecast-details").textContent =
    "Error loading weather data";
}

function handleLocationError(error) {
  console.error("Location error:", error);
  showLocationError("Error sharing location. Please try again.");
}

function showLocationError(message) {
  const errorElement =
    document.getElementById("location-error") ||
    document.getElementById("forecast-details");
  errorElement.textContent = message;
}

// Auto-refresh every 10 seconds
setInterval(fetchWeatherData, 10000);

// Weather icon mapping remains the same
function getWeatherIcon(condition) {
  const icons = {
    Clouds: "fas fa-cloud",
    Clear: "fas fa-sun",
    Rain: "fas fa-cloud-rain",
    Snow: "fas fa-snowflake",
    Thunderstorm: "fas fa-bolt",
  };
  return icons[condition] || "fas fa-cloud";
}
