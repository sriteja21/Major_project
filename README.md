# AI Navigation System for Visually Impaired

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API keys
```bash
copy .env.example .env
```
Edit `.env`:
```
GOOGLE_MAPS_API_KEY=AIza...    → https://console.cloud.google.com
GEMINI_API_KEY=AIza...         → https://aistudio.google.com/app/apikey
```

### 3. Enable Google Cloud APIs
- Maps JavaScript API
- Places API
- Directions API

### 4. Run
```bash
python main.py
```

---

## Voice Commands

| Say | What happens |
|-----|--------------|
| `hello` | System greets, lists saved places |
| `navigate to hospital` | Finds nearest hospital, asks confirmation |
| `find nearby ATM` | Finds nearest ATM |
| `take me home` | Navigates to saved home location |
| `save this as home` | Saves current GPS as "home" |
| `save this as work` | Saves current GPS as "work" |
| `yes` | Confirms navigation |
| `no` / `cancel` | Cancels navigation |
| `read this` | OCR — reads signs/labels aloud |
| `what is in front of me` | Gemini AI describes the scene |
| `describe` | Same as above |

---

## Automatic Alerts (no command needed)

| Event | Alert spoken |
|-------|-------------|
| Person/car too close | "Caution! person ahead on your Centre, 120 centimetres" |
| Traffic light red | "Red light ahead. Stop." |
| Traffic light green | "Green light. You may cross." |
| Fast moving vehicle | "Warning! Fast moving car on your Left. Do not cross." |
| Uneven ground | "Caution! Uneven ground ahead, slow down." |

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `camera.py` | Threaded webcam |
| `detector.py` | YOLOv8n detection + tracking |
| `brain.py` | Distance + traffic light + pothole + fast car |
| `voice.py` | TTS + Speech Recognition |
| `gps.py` | Browser GPS + IP fallback |
| `navigator.py` | Google Maps Places + Directions + Favourites |
| `favourites.py` | Save/load named locations (favourites.json) |
| `ocr.py` | EasyOCR text reading |
| `scene.py` | Gemini AI scene description |
| `map_window.py` | PyQt5 Google Maps browser |
