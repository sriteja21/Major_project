import cv2
import time
import numpy as np
from collections import defaultdict

OBJECT_WIDTHS = {
    "person": 50, "car": 180, "truck": 250, "bus": 260,
    "bicycle": 60, "motorcycle": 80, "dog": 40, "cat": 25,
    "bottle": 8, "chair": 50, "default": 50
}

FOCAL_LENGTH = 600
DANGER_CM    = 300
URGENT_CM    = 150
IGNORE_CM    = 60
COOLDOWN     = 8
TL_COOLDOWN  = 5
CAR_COOLDOWN = 6
FAST_CAR_PX  = 18

class Brain:
    def __init__(self, speak_fn):
        self.speak         = speak_fn
        self._active       = False   # only alert when active
        self.last_alert    = 0
        self.last_tl       = 0
        self.last_car      = 0
        self.dist_history  = defaultdict(list)
        self.car_positions = defaultdict(list)

    def enable(self):  self._active = True
    def disable(self): self._active = False

    def _distance(self, label, pw):
        rw = OBJECT_WIDTHS.get(label, OBJECT_WIDTHS["default"])
        return (rw * FOCAL_LENGTH) / pw if pw > 0 else 9999

    def _zone(self, x1, x2, fw):
        cx = (x1 + x2) / 2
        if cx < fw / 3:       return "Left"
        elif cx < 2 * fw / 3: return "Centre"
        else:                  return "Right"

    def _smooth(self, tid, dist):
        h = self.dist_history[tid]
        h.append(dist)
        if len(h) > 5: h.pop(0)
        return sum(h) / len(h)

    def _tl_color(self, frame, x1, y1, x2, y2):
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0: return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        red = (cv2.inRange(hsv, np.array([0,100,100]),   np.array([10,255,255])) +
               cv2.inRange(hsv, np.array([160,100,100]), np.array([180,255,255])))
        grn =  cv2.inRange(hsv, np.array([40,80,80]),    np.array([90,255,255]))
        r, g = cv2.countNonZero(red), cv2.countNonZero(grn)
        if max(r, g) < 20: return None
        return "red" if r > g else "green"

    def _is_fast(self, label, tid, cx):
        if label not in ("car","truck","bus","motorcycle"): return False
        p = self.car_positions[tid]
        p.append(cx)
        if len(p) > 4: p.pop(0)
        if len(p) < 3: return False
        return abs(p[-1] - p[0]) / len(p) > FAST_CAR_PX

    def process(self, frame, detections):
        h, w    = frame.shape[:2]
        closest = None
        now     = time.time()

        for label, conf, x1, y1, x2, y2, tid in detections:
            cx = (x1 + x2) // 2

            # Always draw boxes
            cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 0), 1)

            if not self._active:
                continue

            # Traffic light
            if label == "traffic light" and now - self.last_tl > TL_COOLDOWN:
                c = self._tl_color(frame, x1, y1, x2, y2)
                if c == "red":
                    self.speak("Red light ahead. Stop.", priority=True)
                    self.last_tl = now
                elif c == "green":
                    self.speak("Green light. You may cross.", priority=True)
                    self.last_tl = now
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                continue

            # Fast car
            if self._is_fast(label, tid, cx) and now - self.last_car > CAR_COOLDOWN:
                self.speak(f"Warning! Fast moving {label} on your {self._zone(x1, x2, w)}. Do not cross.", priority=True)
                self.last_car = now

            # Obstacle distance
            dist = self._smooth(tid, self._distance(label, x2 - x1))
            if dist < IGNORE_CM or dist > DANGER_CM: continue

            color = (0, 0, 255) if dist < URGENT_CM else (0, 200, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {int(dist)}cm", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            if closest is None or dist < closest[0]:
                closest = (dist, label, self._zone(x1, x2, w))

        if closest and now - self.last_alert > COOLDOWN:
            dist, label, zone = closest
            self.speak(f"{'Caution! ' if dist < URGENT_CM else ''}{label} on your {zone}, {int(dist)} centimetres")
            self.last_alert = now

        return frame
