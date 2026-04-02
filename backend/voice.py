import pyttsx3
import speech_recognition as sr
import threading
import queue
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Voice")

class VoiceEngine:
    """Single persistent engine — never re-initialised."""

    def __init__(self):
        self._queue  = queue.Queue()
        self._ready  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TTS")
        self._thread.start()
        self._ready.wait(timeout=5)

    def speak(self, text: str, priority: bool = False):
        if priority:
            self._flush()
        self._queue.put(text)
        log.info(f"[SPEAK] {text}")

    def _flush(self):
        while not self._queue.empty():
            try: self._queue.get_nowait()
            except queue.Empty: break

    def _run(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", 155)
        engine.setProperty("volume", 1.0)
        for v in engine.getProperty("voices"):
            if "zira" in v.name.lower() or "female" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
        engine.startLoop(False)
        self._ready.set()
        while True:
            try:
                pending = []
                while not self._queue.empty():
                    try: pending.append(self._queue.get_nowait())
                    except queue.Empty: break
                if pending:
                    engine.say(". ".join(pending))
                engine.iterate()
            except Exception as e:
                log.error(f"TTS error: {e}")
            threading.Event().wait(0.05)


class SpeechListener:
    CONFIRM_YES = ["yes", "yeah", "yep", "sure", "ok", "okay", "correct"]
    CONFIRM_NO  = ["no",  "nope", "cancel", "stop navigation", "don't"]

    def __init__(self, callback):
        self.callback = callback
        self.rec      = sr.Recognizer()
        self.mic      = sr.Microphone()
        self._mute    = False   # mute while describing/reading
        self._listen  = True
        self._calibrate()
        threading.Thread(target=self._loop, daemon=True).start()

    def _calibrate(self):
        log.info("Calibrating mic...")
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1.5)
        self.rec.pause_threshold       = 0.8
        self.rec.phrase_threshold      = 0.3
        self.rec.non_speaking_duration = 0.5
        self.rec.energy_threshold      = max(self.rec.energy_threshold, 300)

    def mute(self):   self._mute = True
    def unmute(self): self._mute = False

    def _loop(self):
        log.info("Listening...")
        while self._listen:
            if self._mute:
                threading.Event().wait(0.2)
                continue
            try:
                with self.mic as src:
                    audio = self.rec.listen(src, timeout=5, phrase_time_limit=8)
                text = self.rec.recognize_google(audio).lower().strip()
                log.info(f"[HEARD] {text}")
                self.callback(text)
            except sr.WaitTimeoutError: pass
            except sr.UnknownValueError: pass
            except sr.RequestError as e: log.warning(f"SR error: {e}")
            except Exception as e: log.error(f"Listener error: {e}")

    @staticmethod
    def is_yes(t): return any(w in t for w in SpeechListener.CONFIRM_YES)
    @staticmethod
    def is_no(t):  return any(w in t for w in SpeechListener.CONFIRM_NO)
