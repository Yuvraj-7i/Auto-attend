import os
import cv2
import time
import math
import base64
import random
import threading
import numpy as np
import logging
from config import Config
from services.face_recognition_service import face_service
from services.attendance_service import attendance_service
from database.db_manager import fetch_all, fetch_one, execute_query

logger = logging.getLogger("AutoAttend-Camera")

class CameraService:
    """
    Manages camera video capture, real-time AI overlay rendering,
    streaming, frame processing, and simulated demo mode.
    """

    def __init__(self):
        self.camera_index = Config.CAMERA_INDEX
        self.cap = None
        self.is_running = False
        self.is_demo_mode = Config.DEMO_MODE
        self.active_session_id = None
        self.lock = threading.Lock()
        self.last_frame = None
        self.detection_events = [] # Recent recognition events for live feed
        self.stats = {
            "detected": 0,
            "recognized": 0,
            "pending": 0,
            "fps": 0
        }
        self.sim_tick = 0

    def start_camera(self, camera_index=None, demo_mode=False):
        """Initializes the physical webcam or demo generator."""
        with self.lock:
            if self.is_running:
                return True

            self.is_demo_mode = demo_mode
            if camera_index is not None:
                self.camera_index = camera_index

            if not self.is_demo_mode:
                try:
                    # DirectShow is the reliable webcam backend on Windows.
                    if os.name == "nt":
                        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                    else:
                        self.cap = cv2.VideoCapture(self.camera_index)
                    if not self.cap.isOpened() and os.name == "nt":
                        self.cap.release()
                        self.cap = cv2.VideoCapture(self.camera_index)
                    if not self.cap.isOpened():
                        logger.warning("Could not open physical webcam index %s. Falling back to Demo Mode.", self.camera_index)
                        self.is_demo_mode = True
                        self.cap = None
                    else:
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        self.cap.set(cv2.CAP_PROP_FPS, 30)
                except Exception as e:
                    logger.warning("Webcam init exception: %s. Switching to Demo Mode.", str(e))
                    self.is_demo_mode = True
                    self.cap = None

            self.is_running = True
            logger.info("Camera service started (Demo Mode: %s)", self.is_demo_mode)
            return True

    def stop_camera(self):
        """Releases the camera device."""
        with self.lock:
            self.is_running = False
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            logger.info("Camera service stopped.")

    def set_active_session(self, session_id):
        """Associates the camera stream with an active attendance session."""
        self.active_session_id = session_id
        self.detection_events.clear()

    def process_client_frame(self, base64_image_data, session_id=None):
        """
        Processes a frame sent directly by the browser (via HTML5 getUserMedia Canvas).
        Returns detection results and attendance triggers.
        """
        try:
            if "," in base64_image_data:
                base64_image_data = base64_image_data.split(",")[1]

            image_bytes = base64.b64decode(base64_image_data)
            np_arr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                return {"success": False, "message": "Failed to decode frame"}

            results = face_service.recognize_faces_in_frame(frame, threshold=Config.FACE_MATCH_THRESHOLD)
            target_session = session_id or self.active_session_id

            marked_students = []
            if target_session:
                for det in results:
                    stu_id = det.get("student_id")
                    if stu_id and det.get("status") == "recognized":
                        marked, obs, conf = face_service.accumulate_observation(
                            target_session, stu_id, det["confidence"], Config.MIN_OBSERVATIONS
                        )
                        det["observations"] = obs
                        det["is_marked"] = marked
                        if marked:
                            marked_students.append(det)
                            attendance_service.record_live_arrival(target_session, stu_id)
                            self._add_event(f"Attendance Recorded: {det['full_name']} ({det['roll_number']})", "success", det)
                    elif det.get("status") == "low_confidence":
                        self._add_event(f"Uncertain Match: {det['full_name']} (Under Review)", "warning", det)
                    elif det.get("status") == "unknown":
                        self._add_event("Unknown Face Detected", "danger", det)

            return {
                "success": True,
                "detections": results,
                "marked_count": len(marked_students),
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error("Process client frame error: %s", str(e))
            return {"success": False, "error": str(e)}

    def _add_event(self, message, event_type="info", data=None):
        """Logs an event for the live recognition feed UI."""
        event = {
            "id": int(time.time() * 1000) + random.randint(1, 999),
            "time": time.strftime("%H:%M:%S"),
            "message": message,
            "type": event_type,
            "data": data or {}
        }
        self.detection_events.insert(0, event)
        if len(self.detection_events) > 30:
            self.detection_events.pop()

    def generate_demo_frame(self):
        """
        Synthesizes a realistic camera view for testing & presentation demonstration.
        Renders simulated classroom video frame with face tracking boxes,
        confidence scores, and attendance triggers.
        """
        self.sim_tick += 1
        h, w = 480, 640

        # Background classroom simulation (dark navy gradient with cyber grid)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Create subtle background gradient
        for y in range(h):
            val = int(24 + (y / h) * 35)
            frame[y, :] = (val + 10, val + 5, val)

        # Draw futuristic grid lines
        grid_color = (45, 40, 55)
        for gx in range(0, w, 40):
            cv2.line(frame, (gx, 0), (gx, h), grid_color, 1)
        for gy in range(0, h, 40):
            cv2.line(frame, (gy, 0), (gy, w), grid_color, 1)

        # Classroom seating silhouette
        cv2.rectangle(frame, (0, 380), (640, 480), (30, 25, 38), -1)
        cv2.line(frame, (0, 380), (640, 380), (70, 60, 95), 2)

        # Simulated students list from DB
        students = fetch_all("SELECT id, full_name, roll_number FROM students LIMIT 6;")
        if not students:
            students = [
                {"id": 1, "full_name": "Yuvraj Soni", "roll_number": "0827CS211180"},
                {"id": 2, "full_name": "Tanishk Jain", "roll_number": "0827CS211165"},
                {"id": 3, "full_name": "Umesh Dhakad", "roll_number": "0827CS211172"},
                {"id": 4, "full_name": "Vinayak Sahu", "roll_number": "0827CS211178"}
            ]

        # Animate 2 to 3 simulated face positions
        t = self.sim_tick * 0.05
        face_coords = [
            (int(140 + 25 * math.sin(t)), int(180 + 10 * math.cos(t)), 110, 130, students[0]),
            (int(380 + 20 * math.cos(t * 0.8)), int(160 + 15 * math.sin(t * 0.8)), 110, 130, students[1]),
        ]

        # Occasionally add a 3rd student or an unknown face
        if len(students) > 2 and (self.sim_tick // 40) % 2 == 0:
            face_coords.append(
                (int(260 + 15 * math.sin(t * 1.2)), int(220 + 8 * math.cos(t * 1.2)), 95, 115, students[2])
            )

        recognized_count = 0
        for fx, fy, fw, fh, stu in face_coords:
            # Draw realistic avatar silhouette inside bounding box
            cv2.circle(frame, (fx + fw//2, fy + fh//2 - 10), 32, (180, 170, 160), -1) # Head
            cv2.ellipse(frame, (fx + fw//2, fy + fh + 15), (45, 30), 0, 0, 180, (140, 130, 120), -1) # Shoulders

            # Calculate simulated confidence
            confidence = round(0.88 + 0.08 * math.sin(t + fx), 2)
            is_match = confidence >= Config.FACE_MATCH_THRESHOLD

            if is_match:
                recognized_count += 1
                color = (79, 214, 115) # Green / Emerald
                status_text = f"MATCH {int(confidence * 100)}%"
            else:
                color = (48, 170, 245) # Amber
                status_text = f"SCANNING {int(confidence * 100)}%"

            # Futuristic bounding box corner brackets
            self._draw_hud_box(frame, fx, fy, fw, fh, color)

            # Label banner
            label = f"{stu['full_name']} | {stu['roll_number']}"
            cv2.rectangle(frame, (fx - 5, fy - 30), (fx + fw + 5, fy - 5), (20, 20, 30), -1)
            cv2.rectangle(frame, (fx - 5, fy - 30), (fx + fw + 5, fy - 5), color, 1)
            cv2.putText(frame, label, (fx, fy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
            cv2.putText(frame, status_text, (fx, fy + fh + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)

            # If an active session is in progress, accumulate observation
            if self.active_session_id and self.sim_tick % 10 == 0:
                marked, obs, _ = face_service.accumulate_observation(
                    self.active_session_id, stu["id"], confidence, Config.MIN_OBSERVATIONS
                )
                if marked:
                    attendance_service.record_live_arrival(self.active_session_id, stu["id"])
                    self._add_event(f"Attendance Recorded: {stu['full_name']} ({stu['roll_number']})", "success", stu)

        # Update stats
        self.stats["detected"] = len(face_coords)
        self.stats["recognized"] = recognized_count
        self.stats["pending"] = len(face_coords) - recognized_count

        # Top HUD Banner: Demo Mode Indicator
        cv2.rectangle(frame, (10, 10), (630, 42), (15, 23, 42), -1)
        cv2.rectangle(frame, (10, 10), (630, 42), (6, 182, 212), 1)
        cv2.putText(frame, "[DEMO SIMULATION ACTIVE] - AutoAttend Vision Engine", (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (6, 182, 212), 1)
        session_info = f"Session: #{self.active_session_id if self.active_session_id else 'Idle'} | Faces: {len(face_coords)}"
        cv2.putText(frame, session_info, (420, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        return frame

    def _draw_hud_box(self, frame, x, y, w, h, color):
        """Draws aesthetic sci-fi HUD bounding box corners."""
        line_len = min(20, w // 4, h // 4)
        thickness = 2
        # Top-left
        cv2.line(frame, (x, y), (x + line_len, y), color, thickness)
        cv2.line(frame, (x, y), (x, y + line_len), color, thickness)
        # Top-right
        cv2.line(frame, (x + w, y), (x + w - line_len, y), color, thickness)
        cv2.line(frame, (x + w, y), (x + w, y + line_len), color, thickness)
        # Bottom-left
        cv2.line(frame, (x, y + h), (x + line_len, y + h), color, thickness)
        cv2.line(frame, (x, y + h), (x, y + h - line_len), color, thickness)
        # Bottom-right
        cv2.line(frame, (x + w, y + h), (x + w - line_len, y + h), color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w, y + h - line_len), color, thickness)

    def get_frame(self):
        """Yields annotated JPEG frames for MJPEG video streaming."""
        while self.is_running:
            if self.is_demo_mode or self.cap is None:
                frame = self.generate_demo_frame()
                time.sleep(0.04) # ~25 FPS
            else:
                success, raw_frame = self.cap.read()
                if not success or raw_frame is None:
                    # Physical camera stream interrupted, yield demo frame
                    frame = self.generate_demo_frame()
                    time.sleep(0.04)
                else:
                    # Run face recognition on real camera frame
                    detections = face_service.recognize_faces_in_frame(raw_frame, Config.FACE_MATCH_THRESHOLD)
                    self.stats["detected"] = len(detections)
                    recognized = 0

                    for det in detections:
                        x, y, w, h = det["bbox"]
                        status = det["status"]
                        conf = det["confidence"]
                        name = det["full_name"]

                        if status == "recognized":
                            recognized += 1
                            color = (79, 214, 115) # Green
                            label = f"{name} ({int(conf * 100)}%)"
                            # Accumulate
                            if self.active_session_id:
                                marked, obs, _ = face_service.accumulate_observation(
                                    self.active_session_id, det["student_id"], conf, Config.MIN_OBSERVATIONS
                                )
                                if marked:
                                    attendance_service.record_live_arrival(self.active_session_id, det["student_id"])
                                    self._add_event(f"Attendance Recorded: {name}", "success", det)
                        elif status == "low_confidence":
                            color = (48, 170, 245) # Amber
                            label = f"Verifying: {name} ({int(conf * 100)}%)"
                        else:
                            color = (80, 80, 235) # Red
                            label = "Unknown Face (Not Enrolled)"

                        self._draw_hud_box(raw_frame, x, y, w, h, color)
                        cv2.rectangle(raw_frame, (x, y - 24), (x + w, y), (20, 20, 30), -1)
                        cv2.putText(raw_frame, label, (x + 4, y - 6),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)

                    self.stats["recognized"] = recognized
                    self.stats["pending"] = len(detections) - recognized
                    frame = raw_frame

            self.last_frame = frame
            # Encode frame to JPEG format
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

camera_service = CameraService()
