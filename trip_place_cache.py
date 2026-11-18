
import asyncio
import os

from dotenv import load_dotenv
from utils.currency_converter import CurrencyConverter


async def main():
    load_dotenv()

    api_key = os.environ.get("EXCHANGE_RATE_API_KEY")

    converter = CurrencyConverter(api_key)

    try:
        print("\n--- First conversion ---")
        result1 = await converter.convert(1000, "INR", "USD")
        print("1000 INR to USD:", result1)

        print("\n--- Second conversion ---")
        result2 = await converter.convert(2000, "INR", "USD")
        print("2000 INR to USD:", result2)

        print("\n--- Third conversion ---")
        result3 = await converter.convert(1000, "INR", "EUR")
        print("1000 INR to EUR:", result3)

        print("\n--- Verification ---")
        print("Different amounts produce different results:", result1 != result2)
        print("Same source currency reuses rates:", len(converter.rates_cache) == 1)

    finally:
        await converter.close()


asyncio.run(main())