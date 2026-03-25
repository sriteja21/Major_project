"""
GPS acquisition: serves a tiny HTML page on localhost:5001.
The browser's navigator.geolocation POSTs coords to localhost:5000.
Falls back to IP geolocation if browser GPS is unavailable.
"""
import threading
import time
import requests
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

_location = {"lat": None, "lon": None, "source": None}
_lock = threading.Lock()


class _Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        with _lock:
            _location.update({"lat": body["lat"], "lon": body["lon"], "source": "browser"})
        self._ok()

    def do_OPTIONS(self):   # CORS preflight
        self._ok()

    def _ok(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *_): pass   ─

GPS_PAGE = """<!DOCTYPE html><html><body>
<script>
navigator.geolocation.getCurrentPosition(
  p => fetch('http://localhost:5000',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({lat:p.coords.latitude,lon:p.coords.longitude})
  }),
  e => console.warn('GPS error',e),
  {enableHighAccuracy:true,timeout:10000}
);
</script><p>Acquiring GPS...</p></body></html>"""

class _PageServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(GPS_PAGE.encode())
    def log_message(self, *_): pass


def _ip_fallback():
    providers = [
        "https://ipapi.co/json/",
        "https://ip-api.com/json/",
        "https://ipwhois.app/json/",
    ]
    coords = []
    for url in providers:
        try:
            r = requests.get(url, timeout=3).json()
            lat = r.get("latitude") or r.get("lat")
            lon = r.get("longitude") or r.get("lon") or r.get("lng")
            if lat and lon:
                coords.append((float(lat), float(lon)))
        except Exception:
            pass
    if coords:
        lat = sorted(c[0] for c in coords)[len(coords) // 2]
        lon = sorted(c[1] for c in coords)[len(coords) // 2]
        with _lock:
            if _location["lat"] is None:
                _location.update({"lat": lat, "lon": lon, "source": "ip"})


def start():
    for port, handler in [(5000, _Receiver), (5001, _PageServer)]:
        srv = HTTPServer(("localhost", port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=lambda: (time.sleep(5), _ip_fallback()), daemon=True).start()

def get():
    with _lock:
        return _location["lat"], _location["lon"]

def ready():
    lat, lon = get()
    return lat is not None and lon is not None
