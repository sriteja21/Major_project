"""
Save and load favourite named places.
Stored in favourites.json next to this file.
Voice commands (handled in navigator.py):
  "save as home"   → saves current GPS as 'home'
  "save as work"   → saves current GPS as 'work'
  "take me home"   → navigates to saved home
  "take me to work"→ navigates to saved work
"""
import json
import os

_FILE = os.path.join(os.path.dirname(__file__), "favourites.json")

def _load():
    if os.path.exists(_FILE):
        with open(_FILE) as f:
            return json.load(f)
    return {}

def _save(data):
    with open(_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save(name: str, lat: float, lon: float):
    data = _load()
    data[name.lower()] = {"lat": lat, "lon": lon}
    _save(data)

def get(name: str):
    """Returns (lat, lon) or (None, None) if not saved."""
    data = _load()
    entry = data.get(name.lower())
    if entry:
        return entry["lat"], entry["lon"]
    return None, None

def list_all():
    return list(_load().keys())
