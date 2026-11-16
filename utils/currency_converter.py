import httpx

class CurrencyConverter:
    def __init__(self, api_key: str):
        self.base_url = (
            f"https://v6.exchangerate-api.com/v6/{api_key}/latest"
        )
        self.client = httpx.AsyncClient(timeout=10.0)

    async def convert(self, amount: float, from_currency: str, to_currency: str):
        """Convert the amount from one currency to another."""

        url = f"{self.base_url}/{from_currency.upper()}"

        response = await self.client.get(url)

        if response.status_code != 200:
            raise Exception(f"API call failed: {response.text}")

        rates = response.json()["conversion_rates"]

        to_currency = to_currency.upper()

        if to_currency not in rates:
            raise ValueError(
                f"{to_currency} not found in exchange rates."
            )

        return amount * rates[to_currency]

    async def close(self):
        """Close the reusable HTTP client."""
        await self.client.aclose()