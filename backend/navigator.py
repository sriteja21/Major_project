import os
import math
import re
import time
import json
import threading
import webbrowser
import logging
import requests
import urllib.parse
import favourites as fav
from voice import SpeechListener
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("Nav")
PLACE_TYPES = {
    "hospital":    ("amenity", "hospital"),
    "clinic":      ("amenity", "clinic"),
    "atm":         ("amenity", "atm"),
    "cash":        ("amenity", "atm"),
    "pharmacy":    ("amenity", "pharmacy"),
    "chemist":     ("amenity", "pharmacy"),
    "restaurant":  ("amenity", "restaurant"),
    "food":        ("amenity", "restaurant"),
    "cafe":        ("amenity", "cafe"),
    "bus":         ("amenity", "bus_station"),
    "bus stop":    ("highway", "bus_stop"),
    "police":      ("amenity", "police"),
    "school":      ("amenity", "school"),
    "college":     ("amenity", "college"),
    "bank":        ("amenity", "bank"),
    "supermarket": ("shop",    "supermarket"),
    "shop":        ("shop",    "convenience"),
    "park":        ("leisure", "park"),
    "petrol":      ("amenity", "fuel"),
    "fuel":        ("amenity", "fuel"),
    "hotel":       ("tourism", "hotel"),
    "airport":     ("aeroway", "aerodrome"),
    "toilet":      ("amenity", "toilets"),
    "parking":     ("amenity", "parking"),
}

IDLE             = "idle"
AWAITING_DEST    = "awaiting_dest"
AWAITING_CONFIRM = "awaiting_confirm"
NAVIGATING       = "navigating"

NOMINATIM_UA  = "BlindNavApp/1.0"
OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
OSRM_URL      = "https://router.project-osrm.org/route/v1/foot"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def _hav(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _dw(metres):
    if metres < 1000:
        return f"{int(metres)} metres"
    return f"{metres / 1000:.1f} kilometres"


def _clean_html(s):
    return re.sub(r"<[^>]+>", " ", str(s)).strip()


# ── Navigator ─────────────────────────────────────────────────────────────────

class Navigator:

    def __init__(self, speak_fn, get_gps_fn, map_window=None, brain=None):
        self.speak   = speak_fn
        self.get_gps = get_gps_fn
        self.map_win = map_window
        self.brain   = brain
        self.state   = IDLE

        self._dest_name = None
        self._dest_lat  = None
        self._dest_lon  = None
        self._steps     = []
        self._step_idx  = 0
        self._nav_thread = None

    # ── Public entry point ───────────────────────────────────────────────────

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

    # ── IDLE ─────────────────────────────────────────────────────────────────

    def _idle(self, text):
        if any(w in text for w in ("start", "navigate", "direction", "go to", "take me")):
            self.state = AWAITING_DEST
            self.speak("Where do you want to go?")
            return True
        return False

    # ── AWAITING_DEST ────────────────────────────────────────────────────────

    def _got_destination(self, text):
        for prefix in ("navigate to ", "go to ", "take me to ", "directions to ", "to "):
            text = text.replace(prefix, "")
        text = text.strip()
        if not text:
            self.speak("Sorry, please say the destination name.")
            return True

        lat, lon = self.get_gps()
        if lat is None:
            self.speak("GPS not ready. Please wait.")
            return True

        # 1. Saved favourites
        flat, flon = fav.get(text)
        if flat:
            dist = _dw(_hav(lat, lon, flat, flon))
            self._set_pending(text, flat, flon, dist)
            return True

        # 2. Generic place type -> Overpass nearby search
        tag = next((v for k, v in PLACE_TYPES.items() if k in text), None)
        if tag:
            osm_key, osm_val = tag
            self.speak(f"Searching nearby {text}.")
            places = self._nearby_overpass(lat, lon, osm_key, osm_val)
            if places:
                p = places[0]
                dist = _dw(_hav(lat, lon, p["lat"], p["lon"]))
                self._set_pending(p["name"], p["lat"], p["lon"], dist)
            else:
                self.speak(f"No nearby {text} found.")
            return True

        # 3. Named place → Nominatim geocode
        result = self._geocode_nominatim(text, lat, lon)
        if result:
            dist = _dw(_hav(lat, lon, result["lat"], result["lon"]))
            self._set_pending(result["name"], result["lat"], result["lon"], dist)
            return True

        self.speak("Location not found. Please try again with a different name.")
        return True

    def _set_pending(self, name, dlat, dlon, dist_str):
        self._dest_name = name
        self._dest_lat  = float(dlat)
        self._dest_lon  = float(dlon)
        self.state      = AWAITING_CONFIRM
        self.speak(f"Found {name}, {dist_str} away. Say yes to start navigation.")

    # ── AWAITING_CONFIRM ─────────────────────────────────────────────────────

    def _got_confirm(self, text):
        if SpeechListener.is_yes(text):
            self.state = NAVIGATING
            threading.Thread(target=self._start_navigation, daemon=True).start()
            return True
        elif SpeechListener.is_no(text):
            self.state = IDLE
            self.speak("Cancelled.")
            return True
        return True

    # ── NAVIGATING ───────────────────────────────────────────────────────────

    def _navigating_command(self, text):
        if any(w in text for w in ("stop", "cancel")):
            self._stop()
            self.speak("Navigation stopped.")
            return True
        if any(w in text for w in ("repeat", "again", "what")):
            if self._steps and self._step_idx < len(self._steps):
                self.speak(self._steps[self._step_idx][2])
            return True
        return False

    # ── Navigation core ──────────────────────────────────────────────────────

    def _start_navigation(self):
        lat, lon = self.get_gps()
        log.info(f"GPS: {lat}, {lon}  |  DEST: {self._dest_lat}, {self._dest_lon}")

        if lat is None or lon is None:
            self.speak("GPS not ready. Cannot start navigation.")
            self.state = IDLE
            return

        if self._dest_lat is None or self._dest_lon is None:
            self.speak("Destination not set. Please try again.")
            self.state = IDLE
            return

        route = self._get_route_osrm(lat, lon, self._dest_lat, self._dest_lon)
        if not route:
            self.speak("Could not calculate a route. Please try again.")
            self.state = IDLE
            return

        self._steps    = route["steps"]
        self._step_idx = 0

        # Google Maps directions URL — works without API key
        url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={lat},{lon}"
            f"&destination={self._dest_lat},{self._dest_lon}"
            f"&travelmode=walking"
        )
        log.info(f"Map URL: {url}")
        if self.map_win:
            self.map_win.load(url)
        else:
            webbrowser.open(url)

        first = self._steps[0][2] if self._steps else "Start moving."
        self.speak(
            f"Starting navigation to {self._dest_name}. "
            f"Distance {route['distance']}, about {route['duration']}. "
            f"{first}"
        )

        self._nav_thread = threading.Thread(target=self._track_loop, daemon=True)
        self._nav_thread.start()

    def _track_loop(self):
        while self.state == NAVIGATING:
            time.sleep(5)
            lat, lon = self.get_gps()
            if lat is None:
                continue

            if self._step_idx >= len(self._steps):
                self.speak("You have reached your destination.")
                self._stop()
                return

            step_lat, step_lon, instruction = self._steps[self._step_idx]
            if _hav(lat, lon, step_lat, step_lon) < 25:
                self._step_idx += 1
                if self._step_idx < len(self._steps):
                    self.speak(self._steps[self._step_idx][2])

    def _stop(self):
        self.state = IDLE

    # ── Free API calls ───────────────────────────────────────────────────────

    def _nearby_overpass(self, lat, lon, osm_key, osm_val, radius=2000):
        """
        Overpass API: find nearby amenities by OSM key+value.
        Returns list of {name, lat, lon, distance} sorted by distance.
        """
        query = f"""
[out:json][timeout:15];
(
  node["{osm_key}"="{osm_val}"](around:{radius},{lat},{lon});
  way["{osm_key}"="{osm_val}"](around:{radius},{lat},{lon});
);
out center 10;
"""
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, timeout=20).json()
            places = []
            for el in r.get("elements", []):
                if el["type"] == "node":
                    plat, plon = el.get("lat"), el.get("lon")
                elif el["type"] == "way":
                    c = el.get("center", {})
                    plat, plon = c.get("lat"), c.get("lon")
                else:
                    continue
                if plat is None or plon is None:
                    continue
                name = (
                    el.get("tags", {}).get("name") or
                    el.get("tags", {}).get("amenity") or
                    el.get("tags", {}).get("shop") or
                    "Unknown"
                )
                dist = _hav(lat, lon, float(plat), float(plon))
                places.append({"name": name, "lat": float(plat), "lon": float(plon), "distance": dist})
            places.sort(key=lambda x: x["distance"])
            return places
        except Exception as e:
            log.error(f"Overpass error: {e}")
            return []

    def _geocode_nominatim(self, query, lat, lon):
        """
        Nominatim geocoding: address/place name → (lat, lon).
        Biases toward user's location using viewbox.
        Returns {name, lat, lon} or None.
        """
        try:
            # Bias to ±0.5° around current position
            viewbox = f"{lon-0.5},{lat+0.5},{lon+0.5},{lat-0.5}"
            r = requests.get(
                NOMINATIM_URL,
                params={
                    "q":              query,
                    "format":         "json",
                    "limit":          5,
                    "viewbox":        viewbox,
                    "bounded":        0,      # widen if nothing in viewbox
                    "addressdetails": 1,
                },
                headers={"User-Agent": NOMINATIM_UA},
                timeout=8,
            ).json()

            if not r:
                return None

            # Pick result closest to user
            best = min(
                r,
                key=lambda x: _hav(lat, lon, float(x["lat"]), float(x["lon"]))
            )
            name = best.get("display_name", query).split(",")[0]
            return {"name": name, "lat": float(best["lat"]), "lon": float(best["lon"])}
        except Exception as e:
            log.error(f"Nominatim error: {e}")
            return None

    def _get_route_osrm(self, olat, olon, dlat, dlon):
        """
        OSRM public routing API — walking mode, step-by-step.
        Returns {distance, duration, steps} or None.
        steps = list of (lat, lon, instruction_text)
        """
        try:
            coords = f"{olon},{olat};{dlon},{dlat}"
            r = requests.get(
                f"{OSRM_URL}/{coords}",
                params={"steps": "true", "annotations": "false", "overview": "false"},
                timeout=10,
            ).json()

            if r.get("code") != "Ok":
                log.warning(f"OSRM code: {r.get('code')} | message: {r.get('message')}")
                return None

            route = r["routes"][0]
            leg   = route["legs"][0]
            steps = []

            for step in leg.get("steps", []):
                loc  = step.get("maneuver", {}).get("location", [olon, olat])
                slon, slat = loc[0], loc[1]
                inst = step.get("name", "Continue")
                maneuver = step.get("maneuver", {})
                modifier = maneuver.get("modifier", "")
                mtype    = maneuver.get("type", "")

                # Build human-readable instruction
                if mtype == "arrive":
                    inst = "You have arrived at your destination."
                elif mtype == "depart":
                    inst = f"Head {modifier} on {inst}" if inst else "Start moving."
                elif modifier and inst:
                    inst = f"Turn {modifier} onto {inst}."
                elif modifier:
                    inst = f"Turn {modifier}."
                elif inst:
                    inst = f"Continue on {inst}."
                else:
                    inst = "Continue."

                steps.append((float(slat), float(slon), inst))

            dist_m = route.get("distance", 0)
            dur_s  = route.get("duration", 0)

            dist_str = _dw(dist_m)
            mins     = int(dur_s // 60)
            dur_str  = f"{mins} minutes" if mins > 1 else "less than a minute"

            return {"distance": dist_str, "duration": dur_str, "steps": steps}

        except Exception as e:
            log.error(f"OSRM error: {e}")
            return None