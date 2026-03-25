import requests
from dotenv import load_dotenv
load_dotenv()
import os
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
print("API Key loaded:", API_KEY)

def search_restaurants(location):
    # Step 1: Convert place name → lat, lon (Geocoding)
    geo_url = "https://maps.googleapis.com/maps/api/geocode/json"
    geo_params = {
        "address": location,
        "key": API_KEY
    }

    geo_res = requests.get(geo_url, params=geo_params).json()

    if geo_res["status"] != "OK":
        print("Geocoding failed:", geo_res["status"])
        return

    lat = geo_res["results"][0]["geometry"]["location"]["lat"]
    lon = geo_res["results"][0]["geometry"]["location"]["lng"]

    # Step 2: Search nearby restaurants
    places_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    places_params = {
        "location": f"{lat},{lon}",
        "radius": 3000,  # meters
        "type": "restaurant",
        "key": API_KEY
    }

    places_res = requests.get(places_url, params=places_params).json()

    if places_res["status"] != "OK":
        print("Places API failed:", places_res["status"])
        return

    for place in places_res["results"][:5]:
        print("Name:", place["name"])
        print("Address:", place.get("vicinity", "N/A"))
        print("Rating:", place.get("rating", "N/A"))
        print("Location:", place["geometry"]["location"])
        print("-" * 50)


search_restaurants("Hyderabad")