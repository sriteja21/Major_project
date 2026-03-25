from ultralytics import YOLO
import logging
log = logging.getLogger("Detector")

class Detector:
    def __init__(self):
        self.model = YOLO("yolov8n.pt")

    def detect(self, frame):
        """Returns list of (label, conf, x1, y1, x2, y2, track_id)."""
        try:
            results = self.model.track(frame, persist=True, verbose=False)[0]
            out = []
            for box in results.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label    = self.model.names[int(box.cls[0])]
                conf     = float(box.conf[0])
                track_id = int(box.id[0]) if box.id is not None else -1
                out.append((label, conf, x1, y1, x2, y2, track_id))
            return out
        except KeyboardInterrupt:
            raise   # let main handle clean exit
        except Exception as e:
            log.warning(f"Detection skipped: {e}")
            return []