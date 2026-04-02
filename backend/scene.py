"""
Scene description using Ollama LLaVA (free, local).
Fallback: Gemini API if Ollama fails.
"""
import os
import threading
import cv2
import base64
import requests
from PIL import Image
import io
import logging

log = logging.getLogger("Scene")

PROMPT = (
    "Respond in 1–2 short, casual sentences. "
    "Say only what is important right now. "
    "Focus on what’s in front and if the path is safe or not. "
    "Mention position (left, right, center) only if needed. "
    "Give a simple action like move, stop, or continue. "
    "Be calm, clear, and encouraging. No extra details."
)

def _frame_to_b64(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

def _ollama_describe(b64):
    r = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": "llava",
            "prompt": PROMPT,
            "images": [b64],
            "stream": False
        },
        timeout=60
    )
    log.info(f"Ollama status: {r.status_code}")
    log.info(f"Ollama response: {r.text[:200]}")
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()

def _gemini_describe(b64, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    img   = Image.open(io.BytesIO(base64.b64decode(b64)))
    resp  = model.generate_content(
        [PROMPT, img],
        generation_config={"max_output_tokens": 150, "temperature": 0.2}
    )
    return "".join(p.text for p in resp.parts if hasattr(p, "text")).strip()


class SceneDescriber:
    def __init__(self, speak_fn, listener=None):
        self.speak       = speak_fn
        self.listener    = listener
        self._busy       = False
        self._gemini_key = os.getenv("GEMINI_API_KEY", "")

    def describe(self, frame):
        if self._busy:
            self.speak("Still describing, please wait.")
            return
        self._busy = True
        threading.Thread(target=self._run, args=(frame.copy(),), daemon=True).start()

    def _run(self, frame):
        if self.listener: self.listener.mute()
        try:
            self.speak("Let me look. Please wait.")
            b64 = _frame_to_b64(frame)

            # Try Ollama
            try:
                text = _ollama_describe(b64)
                log.info(f"Ollama result: {text[:100]}")
            except Exception as ollama_err:
                log.error(f"Ollama error: {ollama_err}")
                # Fallback to Gemini
                if self._gemini_key:
                    try:
                        text = _gemini_describe(b64, self._gemini_key)
                    except Exception as gem_err:
                        log.error(f"Gemini error: {gem_err}")
                        text = f"Description failed: {str(gem_err)[:80]}"
                else:
                    text = f"Ollama error: {str(ollama_err)[:100]}"

            self.speak(text if text else "I could not see clearly. Please try again.")
        except Exception as e:
            log.error(f"Scene run error: {e}")
            self.speak(f"Error: {str(e)[:80]}")
        finally:
            self._busy = False
            if self.listener: self.listener.unmute()