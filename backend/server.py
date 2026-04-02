"""
Flask backend server.
Run from backend/ folder: python server.py
"""
import sys
import os
import cv2
import time
import logging
import threading
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from camera    import Camera
from detector  import Detector
from brain     import Brain
from voice     import VoiceEngine, SpeechListener
from gps       import start as start_gps, get as get_gps, ready as gps_ready, source as gps_source
import gps as _gps_mod
from navigator import Navigator
from ocr       import OCR
from scene     import SceneDescriber
import favourites as fav

app = Flask(__name__)
CORS(app)

# ─── Shared state polled by React frontend ─────────────────────────────────────
_STATE = {
    "nav_state": "idle",
    "gps":       "GPS: waiting...",
    "alert":     "",
    "map_url":   "https://www.google.com/maps",
}
_state_lock = threading.Lock()

def set_state(**kw):
    with _state_lock:
        _STATE.update(kw)

def read_state():
    with _state_lock:
        return dict(_STATE)

# ─── Annotated frame buffer ────────────────────────────────────────────────────
_frame_buf = [None]
_nav_ref   = [None]

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/stream")
def stream():
    """MJPEG stream — consumed by <img src="..."> in React."""
    def generate():
        while True:
            frame = _frame_buf[0]
            if frame is None:
                time.sleep(0.03)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + buf.tobytes() + b"\r\n")
            time.sleep(0.033)
    return Response(generate(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status")
def status():
    """Polled every 500 ms by React for live updates."""
    s = read_state()
    lat, lon = get_gps()
    s["gps_label"] = (
        f"GPS ({gps_source()}): {lat:.4f}, {lon:.4f}"
        if lat else "GPS: waiting..."
    )
    s["gps_lat"] = lat
    s["gps_lon"] = lon

    nav = _nav_ref[0]
    if nav:
        s["nav_state"]  = nav.state
        s["dest_lat"]   = nav._dest_lat
        s["dest_lon"]   = nav._dest_lon
        s["dest_name"]  = nav._dest_name or ""
    return jsonify(s)

@app.route("/gps", methods=["POST", "OPTIONS"])
def update_gps():
    """React frontend POSTs real browser GPS here to override IP fallback."""
    if request.method == "OPTIONS":
        return jsonify({}), 200
    try:
        data = request.get_json()
        lat  = float(data["lat"])
        lon  = float(data["lon"])
        with _gps_mod._lock:
            _gps_mod._location.update({"lat": lat, "lon": lon, "source": "browser"})
        logging.info(f"GPS from browser: {lat:.5f}, {lon:.5f}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ─── App logic (runs in background thread) ─────────────────────────────────────

def _run():
    voice    = VoiceEngine()
    base_say = voice.speak

    def say(text, priority=False):
        base_say(text, priority=priority)
        set_state(alert=text)

    say("Starting up. Please wait.", priority=True)

    start_gps(open_browser_page=False)

    camera   = Camera()
    detector = Detector()
    brain    = Brain(say)
    brain.enable()   # ← enables obstacle voice alerts (was missing before)

    # Map bridge — when nav picks a URL, push it to state
    class MapBridge:
        def load(self, url: str):
            set_state(map_url=url)

    nav           = Navigator(say, get_gps, map_window=MapBridge(), brain=brain)
    _nav_ref[0]   = nav
    ocr           = OCR(say)
    scene         = SceneDescriber(say)
    latest        = [None]

    def on_speech(text):
        t = text.lower().strip()

        for kw in ("save this as ", "save as ", "save location as "):
            if t.startswith(kw):
                name = t[len(kw):].strip()
                lat, lon = get_gps()
                if lat:
                    fav.save(name, lat, lon)
                    say(f"Saved {name}.")
                else:
                    say("GPS not ready.")
                return

        if any(w in t for w in ("describe", "what is in front", "what do you see", "look", "scene")):
            if latest[0] is not None:
                scene.describe(latest[0])
            return

        if any(w in t for w in ("read this", "what does this say", "read sign", "read")):
            if latest[0] is not None:
                ocr.read_frame(latest[0])
            return

        nav.handle(t)

    listener       = SpeechListener(on_speech)
    scene.listener = listener
    ocr.listener   = listener

    say("Acquiring GPS.", priority=True)
    for _ in range(20):
        if gps_ready():
            lat, lon = get_gps()
            logging.info(f"GPS ready via '{gps_source()}': {lat:.5f}, {lon:.5f}")
            break
        time.sleep(0.5)

    say(
        "System ready. Say start navigation to begin. "
        "Say describe to hear what is ahead. "
        "Say read this to read any sign.",
        priority=True
    )

    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue
        latest[0]    = frame.copy()
        detections   = detector.detect(frame)
        _frame_buf[0] = brain.process(frame, detections)


if __name__ == "__main__":
    threading.Thread(target=_run, daemon=True).start()
    print("\n  Backend → http://localhost:5050")
    print("  Frontend → cd frontend && npm run dev\n")
    app.run(host="0.0.0.0", port=5050, threaded=True)
