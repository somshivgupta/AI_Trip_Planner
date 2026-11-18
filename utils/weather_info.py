import asyncio
import httpx

from cachetools import TTLCache

class WeatherForecastTool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"

        # Reusable asynchronous HTTP client
        self.client = httpx.AsyncClient(timeout=10.0)

        # Separate caches for current weather and forecast
        self.current_weather_cache = TTLCache(
            maxsize=128,
            ttl=600  # 10 minutes
        )

        self.forecast_cache = TTLCache(
            maxsize=128,
            ttl=1800  # 30 minutes
        )

        # Protect cache access
        self.cache_lock = asyncio.Lock()

    async def get_current_weather(self, place: str):
        """Get current weather with TTL caching."""

        normalized_place = place.strip().lower()
        cache_key = normalized_place

        async with self.cache_lock:
            cached_data = self.current_weather_cache.get(cache_key)

        if cached_data is not None:
            print(f"[CACHE HIT] current_weather: {cache_key}")
            return cached_data

        print(f"[CACHE MISS] current_weather: {cache_key}")

        url = f"{self.base_url}/weather"

        params = {
            "q": place,
            "appid": self.api_key,
        }

        response = await self.client.get(url, params=params)

        if response.status_code == 200:
            weather_data = response.json()

            async with self.cache_lock:
                self.current_weather_cache[cache_key] = weather_data

            return weather_data

        return {}

    async def get_forecast_weather(self, place: str):
        """Get weather forecast with TTL caching."""

        normalized_place = place.strip().lower()
        cache_key = normalized_place

        async with self.cache_lock:
            cached_data = self.forecast_cache.get(cache_key)

        if cached_data is not None:
            print(f"[CACHE HIT] weather_forecast: {cache_key}")
            return cached_data

        print(f"[CACHE MISS] weather_forecast: {cache_key}")

        url = f"{self.base_url}/forecast"

        params = {
            "q": place,
            "appid": self.api_key,
            "cnt": 10,
            "units": "metric",
        }

        response = await self.client.get(url, params=params)

        if response.status_code == 200:
            forecast_data = response.json()

            async with self.cache_lock:
                self.forecast_cache[cache_key] = forecast_data

            return forecast_data

        return {}

    async def close(self):
        """Close the reusable HTTP client."""
        await self.client.aclose()