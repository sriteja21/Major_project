"""
Navigator — full turn-by-turn GPS navigation with voice confirmation.
States: IDLE → AWAITING_DEST → AWAITING_CONFIRM → NAVIGATING
"""
import os
import math
import time
import threading
import requests
import webbrowser
import logging
import favourites as fav
from voice import SpeechListener

log      = logging.getLogger("Nav")
MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

PLACE_TYPES = {
    "hospital": "hospital", "clinic": "hospital",
    "atm": "atm", "cash": "atm",
    "pharmacy": "pharmacy", "chemist": "pharmacy",
    "restaurant": "restaurant", "food": "restaurant",
    "bus": "bus_station", "bus stop": "bus_station",
    "police": "police",
    "school": "school", "college": "school",
    "bank": "bank",
    "supermarket": "supermarket", "shop": "supermarket",
    "park": "park",
}

# State constants
IDLE             = "idle"
AWAITING_DEST    = "awaiting_dest"
AWAITING_CONFIRM = "awaiting_confirm"
NAVIGATING       = "navigating"

def _hav(lat1, lon1, lat2, lon2):
    R  = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def _dw(m):
    return f"{int(m)} metres" if m < 1000 else f"{m/1000:.1f} kilometres"

def _clean_html(s):
    import re
    return re.sub(r"<[^>]+>", " ", s).replace("  ", " ").strip()


class Navigator:
    def __init__(self, speak_fn, get_gps_fn, map_window=None, brain=None):
        self.speak      = speak_fn
        self.get_gps    = get_gps_fn   # callable → (lat, lon)
        self.map_win    = map_window
        self.brain      = brain        # Brain instance to enable/disable alerts
        self.state      = IDLE
        self._dest_name = None
        self._dest_lat  = None
        self._dest_lon  = None
        self._steps     = []           # list of (lat, lon, instruction)
        self._step_idx  = 0
        self._nav_thread = None

    # ── Public: called with every recognised speech word ─────────────────────

    def handle(self, text: str):
        text = text.lower().strip()

        if self.state == IDLE:
            return self._idle(text)
        elif self.state == AWAITING_DEST:
            return self._got_destination(text)
        elif self.state == AWAITING_CONFIRM:
            return self._got_confirm(text)
        elif self.state == NAVIGATING:
            return self._navigating_command(text)

    # ── State: IDLE ───────────────────────────────────────────────────────────

    def _idle(self, text):
        if "start navigation" in text or "navigate" in text or "start" in text:
            self.state = AWAITING_DEST
            self.speak("Where do you want to go?")
            return True
        return False   # not handled — let main handle describe/read

    # ── State: AWAITING_DEST ──────────────────────────────────────────────────

    def _got_destination(self, text):
        # Strip filler words
        for w in ("to ", "go to ", "take me to ", "navigate to "):
            text = text.replace(w, "")
        text = text.strip()
        if not text:
            self.speak("I did not catch that. Please say the destination again.")
            return True

        lat, lon = self.get_gps()
        if lat is None:
            self.speak("GPS not ready. Please wait a moment.")
            return True

        # Check favourites first
        flat, flon = fav.get(text)
        if flat:
            self._set_pending(text, flat, flon, lat, lon)
            return True

        # Search Google Maps Places
        place_type = next((v for k, v in PLACE_TYPES.items() if k in text), None)
        if place_type:
            self.speak(f"Searching for {text}...")
            places = self._nearby(lat, lon, place_type)
            if places:
                p = places[0]
                self._set_pending(
                    p["name"],
                    p["geometry"]["location"]["lat"],
                    p["geometry"]["location"]["lng"],
                    lat, lon
                )
                return True

        # Try geocoding the text as an address
        self.speak(f"Looking up {text}...")
        result = self._geocode(text, lat, lon)
        if result:
            self._set_pending(result["name"], result["lat"], result["lon"], lat, lon)
            return True

        self.speak(f"Sorry, I could not find {text}. Please try again.")
        return True

    def _set_pending(self, name, dlat, dlon, ulat, ulon):
        self._dest_name = name
        self._dest_lat  = dlat
        self._dest_lon  = dlon
        dist = _dw(_hav(ulat, ulon, dlat, dlon))
        self.state = AWAITING_CONFIRM
        self.speak(f"Found {name}, {dist} away. Say yes to start, or no to cancel.")

    # ── State: AWAITING_CONFIRM ───────────────────────────────────────────────

    def _got_confirm(self, text):
        if SpeechListener.is_yes(text):
            self.state = NAVIGATING
            self._start_navigation()
            return True
        elif SpeechListener.is_no(text):
            self.state = IDLE
            self.speak("Navigation cancelled. Say start navigation to try again.")
            return True
        return True  # stay in confirm state

    # ── Navigation start ──────────────────────────────────────────────────────

    def _start_navigation(self):
        lat, lon = self.get_gps()
        route = self._get_route(lat, lon, self._dest_lat, self._dest_lon)
        if not route:
            self.speak("Could not get route. Please try again.")
            self.state = IDLE
            return

        self._steps    = route["steps"]   # list of (lat, lon, instruction)
        self._step_idx = 0

        # Open map
        url = (f"https://www.google.com/maps/dir/?api=1"
               f"&destination={self._dest_lat},{self._dest_lon}&travelmode=walking")
        if self.map_win: self.map_win.load(url)
        else:            webbrowser.open(url)

        # Enable obstacle detection
        if self.brain: self.brain.enable()

        self.speak(
            f"Starting navigation to {self._dest_name}. "
            f"Total distance {route['distance']}, about {route['duration']}. "
            f"First instruction: {self._steps[0][2]}"
        )

        # Start GPS tracking thread
        self._nav_thread = threading.Thread(target=self._track_loop, daemon=True)
        self._nav_thread.start()

    # ── Navigation tracking loop ──────────────────────────────────────────────

    def _track_loop(self):
        """Runs in background. Checks GPS every 5s, speaks turns when close."""
        TURN_RADIUS = 25   # metres — speak next instruction within this distance

        while self.state == NAVIGATING:
            time.sleep(5)
            lat, lon = self.get_gps()
            if lat is None:
                continue

            if self._step_idx >= len(self._steps):
                # Reached destination
                self.speak(f"You have reached your destination, {self._dest_name}. Navigation complete.")
                self._stop()
                return

            step_lat, step_lon, instruction = self._steps[self._step_idx]
            dist_to_step = _hav(lat, lon, step_lat, step_lon)

            if dist_to_step < TURN_RADIUS:
                self._step_idx += 1
                if self._step_idx < len(self._steps):
                    next_inst = self._steps[self._step_idx][2]
                    self.speak(next_inst)
                else:
                    # Last step passed — check distance to destination
                    dist_to_dest = _hav(lat, lon, self._dest_lat, self._dest_lon)
                    if dist_to_dest < 50:
                        self.speak(f"You have reached your destination, {self._dest_name}.")
                        self._stop()
                        return
                    else:
                        self.speak(f"Continue for {_dw(dist_to_dest)}.")

    # ── State: NAVIGATING commands ────────────────────────────────────────────

    def _navigating_command(self, text):
        if "stop navigation" in text or "stop" in text or "cancel" in text:
            self._stop()
            self.speak("Navigation stopped.")
            return True
        if "repeat" in text or "say again" in text:
            if self._step_idx < len(self._steps):
                self.speak(self._steps[self._step_idx][2])
            return True
        if "how far" in text or "distance" in text:
            lat, lon = self.get_gps()
            if lat:
                d = _hav(lat, lon, self._dest_lat, self._dest_lon)
                self.speak(f"{_dw(d)} remaining to {self._dest_name}.")
            return True
        return False  # let brain handle obstacle commands

    def _stop(self):
        self.state = IDLE
        if self.brain: self.brain.disable()

    # ── Google Maps API helpers ───────────────────────────────────────────────

    def _nearby(self, lat, lon, place_type, radius=3000):
        try:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={"location": f"{lat},{lon}", "radius": radius,
                        "type": place_type, "key": MAPS_KEY}, timeout=5
            ).json()
            return r.get("results", [])
        except Exception: return []

    def _geocode(self, query, lat, lon):
        try:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": query, "key": MAPS_KEY,
                        "location": f"{lat},{lon}"}, timeout=5
            ).json()
            results = r.get("results", [])
            if not results: return None
            loc = results[0]["geometry"]["location"]
            return {"name": results[0]["formatted_address"],
                    "lat": loc["lat"], "lon": loc["lng"]}
        except Exception: return None

    def _get_route(self, olat, olon, dlat, dlon):
        try:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={"origin": f"{olat},{olon}",
                        "destination": f"{dlat},{dlon}",
                        "mode": "walking", "key": MAPS_KEY}, timeout=5
            ).json()
            routes = r.get("routes", [])
            if not routes: return None
            leg   = routes[0]["legs"][0]
            steps = []
            for s in leg["steps"]:
                end = s["end_location"]
                steps.append((end["lat"], end["lng"], _clean_html(s["html_instructions"])))
            return {
                "distance": leg["distance"]["text"],
                "duration": leg["duration"]["text"],
                "steps":    steps
            }
        except Exception as e:
            log.error(f"Route error: {e}")
            return None
