import threading
import time
import logging
import requests
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger("GPS")

_location = {"lat": None, "lon": None, "source": None}
_lock = threading.Lock()


# ── Browser GPS receiver (port 5000) ─────────────────────────────────────────

class _Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            lat = body.get("lat")
            lon = body.get("lon")
            if lat is not None and lon is not None:
                with _lock:
                    _location.update({
                        "lat": float(lat),
                        "lon": float(lon),
                        "source": "browser"
                    })
                log.info(f"Browser GPS: lat={lat:.5f}, lon={lon:.5f}")
        except Exception as e:
            log.warning(f"GPS receiver error: {e}")
        self._ok()

    def do_OPTIONS(self):   # CORS preflight
        self._ok()

    def _ok(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *_): pass


# ── Browser GPS page (port 5001) ─────────────────────────────────────────────

GPS_PAGE = """<!DOCTYPE html>
<html>
<head>
  <title>GPS - Allow Location</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee;
           display: flex; align-items: center; justify-content: center;
           height: 100vh; margin: 0; flex-direction: column; }
    h2   { color: #00d4ff; margin-bottom: 10px; }
    p    { font-size: 1.1em; color: #aaa; }
    #status { font-size: 1.3em; color: #0f0; margin: 20px 0; font-weight: bold; }
    #coords { font-size: 1em; color: #ffd700; }
    .warn   { color: #ff6b6b !important; }
    button  { margin-top: 20px; padding: 12px 28px; font-size: 1em;
              background: #00d4ff; border: none; border-radius: 8px;
              cursor: pointer; color: #000; font-weight: bold; }
  </style>
</head>
<body>
  <h2>Navigation GPS</h2>
  <p>Allow <strong>location access</strong> in the browser popup above.</p>
  <div id="status">Requesting GPS...</div>
  <div id="coords"></div>
  <button onclick="requestGPS()">Allow & Get Location</button>
  <script>
    var sent = 0;
    function send(lat, lon, src) {
      document.getElementById('status').innerText = src;
      document.getElementById('coords').innerText = lat.toFixed(5) + ', ' + lon.toFixed(5);
      document.getElementById('status').classList.remove('warn');
      sent++;
      fetch('http://localhost:5000', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({lat: lat, lon: lon})
      }).catch(function(){});
    }
    function onErr(e) {
      var msg = e.code === 1 ? 'Location DENIED - please click Allow above'
              : e.code === 2 ? 'Position unavailable' : 'Timeout - retrying...';
      document.getElementById('status').innerText = msg;
      document.getElementById('status').classList.add('warn');
      setTimeout(requestGPS, 3000);
    }
    function requestGPS() {
      document.getElementById('status').innerText = 'Requesting GPS...';
      navigator.geolocation.getCurrentPosition(
        function(p) { send(p.coords.latitude, p.coords.longitude, 'GPS acquired (accurate)'); },
        onErr,
        {enableHighAccuracy: true, timeout: 15000, maximumAge: 0}
      );
    }
    // Watch for continuous updates
    navigator.geolocation.watchPosition(
      function(p) { send(p.coords.latitude, p.coords.longitude, 'GPS live update'); },
      function(){},
      {enableHighAccuracy: true, maximumAge: 5000}
    );
    requestGPS();
  </script>
</body>
</html>"""



class _PageServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(GPS_PAGE.encode())

    def log_message(self, *_): pass


# ── IP geolocation fallback ───────────────────────────────────────────────────

_IP_PROVIDERS = [
    # (url, lat_key, lon_key)
    ("https://ip-api.com/json/",        "lat",       "lon"),
    ("https://ipapi.co/json/",          "latitude",  "longitude"),
    ("https://ipwhois.app/json/",       "latitude",  "longitude"),
    ("https://geolocation-db.com/json/","latitude",  "longitude"),
]


def _ip_fallback():
    """Query multiple IP geolocation providers in parallel and use the first success."""
    coords = []
    lock = threading.Lock()

    def query(url, lk, lnk):
        try:
            r = requests.get(url, timeout=5).json()
            lat = r.get(lk)
            lon = r.get(lnk)
            if lat and lon and float(lat) != 0:
                with lock:
                    coords.append((float(lat), float(lon)))
        except Exception:
            pass

    threads = [
        threading.Thread(target=query, args=(url, lk, lnk), daemon=True)
        for url, lk, lnk in _IP_PROVIDERS
    ]
    for t in threads:
        t.start()

    # Wait up to 6 seconds for at least one response
    deadline = time.time() + 6
    while time.time() < deadline:
        with lock:
            if coords:
                break
        time.sleep(0.2)

    with lock:
        if not coords:
            log.warning("IP geolocation: all providers failed")
            return

    # Use first result (fastest responder wins)
    lat, lon = coords[0]
    with _lock:
        if _location["lat"] is None:   # don't overwrite browser GPS
            _location.update({"lat": lat, "lon": lon, "source": "ip"})
            log.info(f"IP geolocation: lat={lat:.5f}, lon={lon:.5f}")


# ── Public API ────────────────────────────────────────────────────────────────

def start(open_browser_page: bool = True):
    """
    Start GPS servers and IP fallback.
    If open_browser_page=True, opens localhost:5001 in the default browser
    so the user can grant location permission for accurate GPS.
    """
    # Start receiver on 5000
    recv_srv = HTTPServer(("localhost", 5000), _Receiver)
    threading.Thread(target=recv_srv.serve_forever, daemon=True).start()

    # Start page server on 5001
    page_srv = HTTPServer(("localhost", 5001), _PageServer)
    threading.Thread(target=page_srv.serve_forever, daemon=True).start()

    # Start IP fallback immediately (no delay)
    threading.Thread(target=_ip_fallback, daemon=True).start()

    # Open browser GPS page (gives most accurate location)
    if open_browser_page:
        threading.Thread(
            target=lambda: (time.sleep(1), webbrowser.open("http://localhost:5001")),
            daemon=True
        ).start()

    log.info("GPS started (IP fallback + browser GPS via localhost:5001)")


def get():
    with _lock:
        return _location["lat"], _location["lon"]


def source():
    with _lock:
        return _location.get("source", "none")


def ready():
    lat, lon = get()
    return lat is not None and lon is not None
