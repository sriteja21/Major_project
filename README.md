# AI Navigation System for Visually Impaired

A real-time, voice-driven navigation and scene awareness system.  
Backend: Python + Flask · Frontend: React + Vite · Maps: OpenStreetMap (Leaflet)

---

## Project Structure

```
mapmyindia-version/
├── backend/
│   ├── server.py        ← Flask entry point (run this)
│   ├── camera.py        ← Webcam capture
│   ├── detector.py      ← YOLOv8n object detection
│   ├── brain.py         ← Obstacle distance alerts
│   ├── gps.py           ← GPS acquisition (IP + browser)
│   ├── navigator.py     ← Turn-by-turn navigation state machine
│   ├── voice.py         ← TTS + speech recognition
│   ├── ocr.py           ← Sign/text reader (EasyOCR)
│   ├── scene.py         ← Scene description (LLaVA / Gemini)
│   ├── favourites.py    ← Save/load named locations
│   ├── requirements.txt
│   ├── .env             ← API keys (gitignored)
│   └── yolov8n.pt       ← YOLO weights (gitignored, download separately)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx      ← Main React component
│   │   ├── App.css      ← Styles
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python server.py
```

Runs at **http://localhost:5050**

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.  
Click **Allow** when the browser asks for location access — this gives accurate GPS.

---

## .env Setup

Create `backend/.env`:

```env
GOOGLE_MAPS_API_KEY = ""   # optional — only for check_gmaps.py
GEMINI_API_KEY      = ""   # optional — fallback for scene description
```

Navigation works with **zero API keys** (uses free OpenStreetMap services).

---

## Download YOLOv8 Weights

```bash
cd backend
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

This auto-downloads `yolov8n.pt` (~6 MB) on first run.

---

## Voice Commands

| Say | Action |
|-----|--------|
| `"start navigation"` | Begin navigation flow |
| `"<place name or type>"` | Search for destination (hospital, ATM, Charminar…) |
| `"yes"` | Confirm route and start |
| `"no"` / `"cancel"` | Cancel |
| `"stop"` | Stop active navigation |
| `"repeat"` | Replay current turn instruction |
| `"describe"` | AI describes what is in front of camera |
| `"read this"` | Read text/sign in camera frame |
| `"save as <name>"` | Save current GPS location as favourite |

---

## System Architecture

```
Browser (http://localhost:5173)
  │
  ├── Camera feed ←── GET /stream (MJPEG)  ──→ Flask backend
  ├── Leaflet map ←── GET /status (JSON)   ──→ Flask backend
  └── GPS         ──→ POST /gps  (coords)  ──→ Flask backend
                                                    │
                                              Python modules:
                                              YOLOv8 detector
                                              Brain (alerts)
                                              Navigator (OSM APIs)
                                              OCR (EasyOCR)
                                              Scene (LLaVA/Gemini)
                                              Voice (pyttsx3 + SpeechRecognition)
```

---

## APIs Used (All Free)

| Service | Purpose | Key needed? |
|---------|---------|------------|
| Overpass (OpenStreetMap) | Nearby place search | No |
| Nominatim (OpenStreetMap) | Address geocoding | No |
| OSRM | Walking route planning | No |
| EasyOCR | Sign/text reading | No |
| Ollama LLaVA | Scene description (local AI) | No |
| Gemini API | Scene description fallback | Optional |

---

## What You See in the UI

```
┌────────────────────────┬──────────────────────┐
│                        │                      │
│   CAMERA (live)        │   MAP (Leaflet/OSM)  │
│   with YOLO boxes      │   🔵 Your position   │
│                        │   🔴 Destination     │
│                        │                      │
├────────────────────────────────────────────────┤
│ ⬤ NAVIGATING    GPS(browser): 17.3850, 78.4867    🔔 Turn right onto Main Rd │
└────────────────────────────────────────────────┘
```

---

## Object Detection Alerts

Always-on (no voice command needed). YOLOv8n detects objects every frame:

- **< 300 cm** → speaks label + distance (e.g. *"person on your left, 2 metres"*)
- **< 150 cm** → *"Caution! person ahead, 1 metre"*
- **Traffic lights** → *"Red light ahead. Stop."* / *"Green light. You may cross."*
- **Fast vehicles** → *"Warning! Fast moving car on your right."*
