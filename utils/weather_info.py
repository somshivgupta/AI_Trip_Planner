import requests
import httpx

class WeatherForecastTool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_current_weather(self, place: str):
        """Get current weather of a place."""
        url = f"{self.base_url}/weather"

        params = {
            "q": place,
            "appid": self.api_key,
        }

        response = await self.client.get(url, params=params)

        if response.status_code == 200:
            return response.json()

        return {}

    async def get_forecast_weather(self, place: str):
        """Get weather forecast of a place."""
        url = f"{self.base_url}/forecast"

        params = {
            "q": place,
            "appid": self.api_key,
            "cnt": 10,
            "units": "metric",
        }

        response = await self.client.get(url, params=params)

        if response.status_code == 200:
            return response.json()

        return {}

    async def close(self):
        """Close the reusable HTTP client."""
        await self.client.aclose()