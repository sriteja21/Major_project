"""
OCR — reads text from signs, labels, boards.
Voice command: "read this" / "what does this say"
Mic is muted while reading so nothing interrupts.
"""
import threading
import logging
import easyocr
import cv2

log = logging.getLogger("OCR")

class OCR:
    def __init__(self, speak_fn, listener=None):
        self.speak    = speak_fn
        self.listener = listener
        self._busy    = False
        self._reader  = None
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        self._reader = easyocr.Reader(["en", "te"], verbose=False)
        log.info("OCR ready.")

    def read_frame(self, frame):
        if self._busy:
            self.speak("Still reading, please wait.")
            return
        if self._reader is None:
            self.speak("OCR is still loading, please wait.")
            return
        self._busy = True
        threading.Thread(target=self._run, args=(frame.copy(),), daemon=True).start()

    def _run(self, frame):
        if self.listener: self.listener.mute()
        try:
            self.speak("Reading now. Please hold still.")
            results = self._reader.readtext(frame, detail=0, paragraph=True)
            text    = " ".join(results).strip()
            self.speak(f"It says: {text}" if text else "No text found.")
        except Exception as e:
            self.speak("Could not read text.")
            log.error(e)
        finally:
            self._busy = False
            if self.listener: self.listener.unmute()
