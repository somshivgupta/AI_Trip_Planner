import os
from threading import RLock
from typing import List, Callable

from cachetools import TTLCache
from utils.place_info_search import GooglePlaceSearchTool, TavilyPlaceSearchTool
from langchain.tools import tool
from dotenv import load_dotenv
from utils.timing import measure_time


class PlaceSearchTool:
    def __init__(self):
        load_dotenv()

        self.google_api_key = os.environ.get("GPLACES_API_KEY")
        self.google_places_search = GooglePlaceSearchTool(self.google_api_key)
        self.tavily_search = TavilyPlaceSearchTool()

        # Cache up to 256 search results for one hour.
        self.cache = TTLCache(maxsize=256, ttl=3600)
        self.cache_lock = RLock()

        self.place_search_tool_list = self._setup_tools()

    def _search_with_cache(
        self,
        search_type: str,
        place: str,
        google_search: Callable,
        tavily_search: Callable,
        result_formatter: Callable
    ) -> str:
        """Search Google/Tavily with TTL caching."""

        normalized_place = place.strip().lower()
        cache_key = (search_type, normalized_place)

        # Check cache.
        with self.cache_lock:
            cached_result = self.cache.get(cache_key)

        if cached_result is not None:
            print(f"[CACHE HIT] {cache_key}")
            return cached_result

        print(f"[CACHE MISS] {cache_key}")

        # Fetch fresh result.
        try:
            result = google_search(place)

            if not result:
                raise ValueError("Google Places returned no results")

            response = result_formatter("google", result, None)

        except Exception as e:
            result = tavily_search(place)

            if not result:
                raise RuntimeError(
                    f"Both Google Places and Tavily returned no results for {place}"
                ) from e

            response = result_formatter("tavily", result, e)

        # Cache successful results.
        with self.cache_lock:
            self.cache[cache_key] = response

        return response

    def _setup_tools(self) -> List:

        @tool
        def search_attractions(place: str) -> str:
            """Search attractions of a place."""
            with measure_time("tool.search_attractions"):
                return self._search_with_cache(
                    "attractions",
                    place,
                    self.google_places_search.google_search_attractions,
                    self.tavily_search.tavily_search_attractions,
                    lambda provider, result, error: (
                        f"Following are the attractions of {place} "
                        f"as suggested by google: {result}"
                        if provider == "google"
                        else f"Google cannot find the details due to {error}. "
                             f"\nFollowing are the attractions of {place}: {result}"
                    )
                )

        @tool
        def search_restaurants(place: str) -> str:
            """Search restaurants of a place."""
            with measure_time("tool.search_restaurants"):
                return self._search_with_cache(
                    "restaurants",
                    place,
                    self.google_places_search.google_search_restaurants,
                    self.tavily_search.tavily_search_restaurants,
                    lambda provider, result, error: (
                        f"Following are the restaurants of {place} "
                        f"as suggested by google: {result}"
                        if provider == "google"
                        else f"Google cannot find the details due to {error}. "
                             f"\nFollowing are the restaurants of {place}: {result}"
                    )
                )

        @tool
        def search_activities(place: str) -> str:
            """Search activities of a place."""
            with measure_time("tool.search_activities"):
                return self._search_with_cache(
                    "activities",
                    place,
                    self.google_places_search.google_search_activity,
                    self.tavily_search.tavily_search_activity,
                    lambda provider, result, error: (
                        f"Following are the activities in and around {place} "
                        f"as suggested by google: {result}"
                        if provider == "google"
                        else f"Google cannot find the details due to {error}. "
                             f"\nFollowing are the activities of {place}: {result}"
                    )
                )

        @tool
        def search_transportation(place: str) -> str:
            """Search transportation of a place."""
            with measure_time("tool.search_transportation"):
                return self._search_with_cache(
                    "transportation",
                    place,
                    self.google_places_search.google_search_transportation,
                    self.tavily_search.tavily_search_transportation,
                    lambda provider, result, error: (
                        f"Following are the modes of transportation available "
                        f"in {place} as suggested by google: {result}"
                        if provider == "google"
                        else f"Google cannot find the details due to {error}. "
                             f"\nFollowing are the modes of transportation "
                             f"available in {place}: {result}"
                    )
                )

        return [
            search_attractions,
            search_restaurants,
            search_activities,
            search_transportation
        ]