import asyncio
import httpx

from cachetools import TTLCache

class CurrencyConverter:
    def __init__(self, api_key: str):
        self.base_url = (
            f"https://v6.exchangerate-api.com/v6/{api_key}/latest"
        )
        self.client = httpx.AsyncClient(timeout=10.0)

        # Cache exchange rates for one hour.
        self.rates_cache = TTLCache(
            maxsize=64,
            ttl=3600
        )

        self.cache_lock = asyncio.Lock()

    async def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str
    ):
        """Convert currency using cached exchange rates."""

        from_currency = from_currency.strip().upper()
        to_currency = to_currency.strip().upper()

        # Check cache using the source currency.
        async with self.cache_lock:
            rates = self.rates_cache.get(from_currency)

        if rates is not None:
            print(f"[CACHE HIT] currency_rates: {from_currency}")

        else:
            print(f"[CACHE MISS] currency_rates: {from_currency}")

            url = f"{self.base_url}/{from_currency}"

            response = await self.client.get(url)

            if response.status_code != 200:
                raise Exception(
                    f"API call failed: {response.text}"
                )

            data = response.json()

            if data.get("result") != "success":
                raise ValueError(
                    f"Exchange rate API error: {data.get('error-type')}"
                )

            rates = data.get("conversion_rates")

            if not rates:
                raise ValueError("Exchange rates not found in API response.")

            # Cache only successful exchange-rate responses.
            async with self.cache_lock:
                self.rates_cache[from_currency] = rates

        if to_currency not in rates:
            raise ValueError(
                f"{to_currency} not found in exchange rates."
            )

        # Calculate using the latest cached exchange rates.
        return amount * rates[to_currency]

    async def close(self):
        """Close the reusable HTTP client."""
        await self.client.aclose()