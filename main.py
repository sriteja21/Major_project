"""
AI Navigation System for Visually Impaired
Run: python main.py  |  Press Q to quit
"""
import os
import cv2
import time
import logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)

from camera     import Camera
from detector   import Detector
from brain      import Brain
from voice      import VoiceEngine, SpeechListener
from gps        import start as start_gps, get as get_gps, ready as gps_ready
from navigator  import Navigator
from map_window import MapWindow
from ocr        import OCR
from scene      import SceneDescriber
import favourites as fav

def main():
    voice = VoiceEngine()
    say   = voice.speak

    say("Starting up. Please wait.", priority=True)

    map_win  = MapWindow()
    start_gps()
    camera   = Camera()
    detector = Detector()
    brain    = Brain(say)
    nav      = Navigator(say, get_gps, map_win, brain)
    ocr      = OCR(say)
    scene    = SceneDescriber(say)
    latest   = [None]

    def on_speech(text):
        t = text.lower().strip()

        # Save favourite
        for kw in ("save this as ", "save as ", "save location as "):
            if t.startswith(kw):
                name = t[len(kw):].strip()
                lat, lon = get_gps()
                if lat:
                    fav.save(name, lat, lon)
                    say(f"Saved current location as {name}.")
                else:
                    say("GPS not ready.")
                return

        # Describe scene — mutes mic, nothing interrupts
        if any(w in t for w in ("describe", "what is in front", "what do you see", "look", "scene")):
            if latest[0] is not None:
                scene.describe(latest[0])
            return

        # Read text — mutes mic, nothing interrupts
        if any(w in t for w in ("read this", "what does this say", "read sign", "read")):
            if latest[0] is not None:
                ocr.read_frame(latest[0])
            return

        # Everything else → navigator state machine
        nav.handle(t)

    listener       = SpeechListener(on_speech)
    scene.listener = listener
    ocr.listener   = listener

    # Wait for GPS
    for _ in range(20):
        if gps_ready(): break
        time.sleep(0.5)

    say(
        "System ready. "
        "Say start navigation to begin. "
        "Say describe to hear what is in front of you. "
        "Say read this to read any sign or text.",
        priority=True
    )

    # Main loop
    try:
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            latest[0]  = frame.copy()
            detections = detector.detect(frame)
            frame      = brain.process(frame, detections)

            cv2.putText(frame, f"State: {nav.state.upper()}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            cv2.imshow("Blind Navigation - Q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        cv2.destroyAllWindows()
        say("Shutting down. Goodbye.")

if __name__ == "__main__":
    main()