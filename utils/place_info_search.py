import os
import json
from langchain_tavily import TavilySearch
from langchain_google_community import GooglePlacesTool, GooglePlacesAPIWrapper 

class GooglePlaceSearchTool:
    def __init__(self, api_key: str):
        self.places_wrapper = GooglePlacesAPIWrapper(gplaces_api_key=api_key)
        self.places_tool = GooglePlacesTool(api_wrapper=self.places_wrapper)
    
    def google_search_attractions(self, place: str) -> dict:
        """
        Searches for attractions in the specified place using GooglePlaces API.
        """
        return self.places_tool.run(f"top attractive places in and around {place}")
    
    def google_search_restaurants(self, place: str) -> dict:
        """
        Searches for available restaurants in the specified place using GooglePlaces API.
        """
        return self.places_tool.run(f"what are the top 10 restaurants and eateries in and around {place}?")
    
    def google_search_activity(self, place: str) -> dict:
        """
        Searches for popular activities in the specified place using GooglePlaces API.
        """
        return self.places_tool.run(f"Activities in and around {place}")

    def google_search_transportation(self, place: str) -> dict:
        """
        Searches for available modes of transportation in the specified place using GooglePlaces API.
        """
        return self.places_tool.run(f"What are the different modes of transportations available in {place}")


class TavilyPlaceSearchTool:
    def __init__(self):
        self.tavily_tool = TavilySearch(
            topic="general",
            include_answer="advanced"
        )

    def _search(self, query: str):
        result = self.tavily_tool.invoke({"query": query})

        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]

        return result

    def tavily_search_attractions(self, place: str) -> dict:
        return self._search(
            f"top attractive places in and around {place}"
        )

    def tavily_search_restaurants(self, place: str) -> dict:
        return self._search(
            f"what are the top 10 restaurants and eateries in and around {place}"
        )

    def tavily_search_activity(self, place: str) -> dict:
        return self._search(
            f"activities in and around {place}"
        )

    def tavily_search_transportation(self, place: str) -> dict:
        return self._search(
            f"What are the different modes of transportation available in {place}"
        )
