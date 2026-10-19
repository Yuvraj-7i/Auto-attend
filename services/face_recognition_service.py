import os
import json
import logging
import cv2
import numpy as np
from config import Config
from database.db_manager import fetch_one, fetch_all, execute_query

logger = logging.getLogger("AutoAttend-AI")

class FaceRecognitionService:
    """
    Core AI & Computer Vision Service for AutoAttend.
    Implements:
    - Face Detection using OpenCV Haar Cascade / DNN.
    - Normalized Face Embedding extraction (illumination-invariant feature representation).
    - Cosine similarity matching against registered student biometric templates.
    - Multi-frame observation accumulation to eliminate false positives.
    - Privacy-first template storage and deletion.
    - Labelled interactive Demo Mode simulation.
    """

    FACE_ANGLES = ("front", "left", "right", "up", "down", "other")
    IDENTITY_MODEL = "AutoAttend-Identity-v2"
    # A match is kept only when the correct student is clearly ahead of the next student.
    IDENTITY_MARGIN = 0.08

    def __init__(self):
        self.cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(self.cascade_path)
        self.profile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_profileface.xml'
        )
        if self.face_cascade.empty():
            logger.error("Failed to load OpenCV Haar Cascade from %s", self.cascade_path)
        else:
            logger.info("OpenCV Haar Cascade loaded successfully.")

        # In-memory accumulator for active session observations:
        # structure: { session_id: { student_id: { 'count': int, 'confidences': list } } }
        self._session_observations = {}
        self._templates_refreshed = False

    def detect_faces(self, image_bgr, group=False):
        """
        Detects all faces in a BGR image frame.
        Returns a list of bounding boxes: [(x, y, w, h), ...]
        Uses adaptive equalization (CLAHE) and multi-pass detection for robust detection under varied lighting.
        """
        if image_bgr is None or self.face_cascade.empty():
            return []

        # Downscale very large uploaded images to avoid slow cascade scanning
        h, w = image_bgr.shape[:2]
        max_dim = max(h, w)
        scale_ratio = 1.0
        proc_img = image_bgr
        scan_limit = 1800 if group else 1000
        if max_dim > scan_limit:
            scale_ratio = scan_limit / max_dim
            proc_img = cv2.resize(image_bgr, (int(w * scale_ratio), int(h * scale_ratio)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(proc_img, cv2.COLOR_BGR2GRAY)
        
        # Primary pass with CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)

        min_size = (22, 22) if group else (36, 36)
        neighbors = 3 if group else 4
        faces = self._run_cascade(self.face_cascade, gray_clahe, min_neighbors=neighbors, min_size=min_size)

        # Fallback pass: standard global histogram equalization if primary pass found no face
        if len(faces) == 0:
            gray_eq = cv2.equalizeHist(gray)
            faces = self._run_cascade(self.face_cascade, gray_eq, min_neighbors=3, min_size=(30, 30))

        # Profile views (left/right) are missed by the frontal cascade.
        if len(faces) == 0 and not self.profile_cascade.empty():
            gray_eq = cv2.equalizeHist(gray)
            faces = self._run_cascade(self.profile_cascade, gray_eq, min_neighbors=3, min_size=(30, 30))
            if len(faces) == 0:
                flipped = cv2.flip(gray_eq, 1)
                flipped_faces = self._run_cascade(
                    self.profile_cascade, flipped, min_neighbors=3, min_size=(30, 30)
                )
                img_w = proc_img.shape[1]
                faces = [(img_w - x - w_box, y, w_box, h_box) for (x, y, w_box, h_box) in flipped_faces]

        if scale_ratio != 1.0:
            faces = [(int(x / scale_ratio), int(y / scale_ratio), int(w_box / scale_ratio), int(h_box / scale_ratio)) for (x, y, w_box, h_box) in faces]
        else:
            faces = [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]
        if group:
            faces = self._suppress_overlaps(faces)
        return faces

    def _iou(self, a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

    def _suppress_overlaps(self, boxes, iou_thresh=0.35):
        ordered = sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)
        kept = []
        for box in ordered:
            if all(self._iou(box, other) < iou_thresh for other in kept):
                kept.append(box)
        return kept

    def _run_cascade(self, cascade, gray, min_neighbors=4, min_size=(36, 36)):
        if cascade is None or cascade.empty():
            return []
        found = cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=min_neighbors,
            minSize=min_size,
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        if found is None or len(found) == 0:
            return []
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in found]

    def _largest_face(self, faces):
        if not faces:
            return None
        return max(faces, key=lambda box: box[2] * box[3])

    def _guided_center_crop(self, image_bgr):
        """Uses the on-screen oval as the face when the detector misses an angled view."""
        h_img, w_img = image_bgr.shape[:2]
        side = int(min(h_img, w_img) * 0.62)
        cx, cy = w_img // 2, int(h_img * 0.48)
        x1 = max(0, cx - side // 2)
        y1 = max(0, cy - int(side * 0.48))
        x2 = min(w_img, x1 + side)
        y2 = min(h_img, y1 + side)
        crop = image_bgr[y1:y2, x1:x2]
        return crop if crop.size else None

    def _load_samples(self, embedding_data):
        if not embedding_data:
            return []
        try:
            data = json.loads(embedding_data)
        except (TypeError, json.JSONDecodeError):
            return []
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            return [{"angle": "front", "embedding": data}]
        if isinstance(data, dict):
            samples = []
            for sample in data.get("samples") or []:
                if isinstance(sample, dict) and sample.get("embedding"):
                    samples.append({
                        "angle": sample.get("angle") or "front",
                        "embedding": sample["embedding"]
                    })
            return samples
        return []

    def _raw_cosine(self, embedding1, embedding2):
        if not embedding1 or not embedding2 or len(embedding1) != len(embedding2):
            return -1.0
        vec1 = np.array(embedding1, dtype=np.float32)
        vec2 = np.array(embedding2, dtype=np.float32)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return -1.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def _best_similarity(self, embedding, stored_raw):
        best = -1.0
        for sample in self._load_samples(stored_raw):
            sim = self._raw_cosine(embedding, sample["embedding"])
            if sim > best:
                best = sim
        return best

    def _rank_templates(self, embedding, templates):
        ranked = []
        for template in templates:
            try:
                sim = self._best_similarity(embedding, template["embedding_data"])
            except Exception as exc:
                logger.error("Error comparing template: %s", exc)
                continue
            ranked.append((sim, template))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    def _decision(self, ranked, threshold):
        """Returns the student only when they are clearly ahead of everyone else."""
        if not ranked:
            return None, 0.0, "unknown"
        best_sim, best = ranked[0]
        second_sim = ranked[1][0] if len(ranked) > 1 else -1.0
        margin = best_sim - second_sim
        if best_sim >= threshold and margin >= self.IDENTITY_MARGIN:
            return best, best_sim, "recognized"
        if best_sim >= max(0.5, threshold - 0.12):
            return best, best_sim, "low_confidence"
        return None, best_sim if best_sim > 0 else 0.0, "unknown"

    def extract_face_embedding(self, face_bgr):
        """
        Builds an identity signature from the inner face.
        Brightness is removed so two different students no longer look alike.
        """
        if face_bgr is None or face_bgr.size == 0:
            return None
        height, width = face_bgr.shape[:2]
        if height < 20 or width < 20:
            return None

        y1, y2 = int(height * 0.12), int(height * 0.88)
        x1, x2 = int(width * 0.08), int(width * 0.92)
        crop = face_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            crop = face_bgr

        gray = cv2.cvtColor(cv2.resize(crop, (48, 48)), cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray).astype(np.float32)
        gray = (gray - gray.mean()) / (gray.std() + 1e-6)
        shape = gray.flatten()
        shape = shape / (np.linalg.norm(shape) + 1e-6)

        hsv = cv2.cvtColor(cv2.resize(crop, (24, 24)), cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 0] /= 180.0
        hsv[:, :, 1] /= 255.0
        hsv[:, :, 2] /= 255.0
        color = hsv.reshape(-1)
        color = (color - color.mean()) / (color.std() + 1e-6)
        color = color / (np.linalg.norm(color) + 1e-6)

        combined = np.concatenate([shape * 0.75, color * 0.25]).astype(np.float32)
        combined = combined / (np.linalg.norm(combined) + 1e-6)
        return combined.tolist()

    def refresh_saved_templates(self):
        """Rebuilds stored signatures from the saved face photos after the matcher changes."""
        if self._templates_refreshed:
            return
        self._templates_refreshed = True
        folder = os.path.join(Config.UPLOAD_FOLDER, "faces")
        if not os.path.isdir(folder):
            return
        grouped = {}
        for name in os.listdir(folder):
            if not name.startswith("student_") or not name.lower().endswith(".jpg"):
                continue
            stem = name[:-4]
            parts = stem.split("_")
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            angle = parts[2].lower()
            if angle not in self.FACE_ANGLES:
                continue
            grouped.setdefault(int(parts[1]), []).append((angle, os.path.join(folder, name)))

        for student_id, views in grouped.items():
            samples = []
            for angle, path in views:
                image = cv2.imread(path)
                embedding = self.extract_face_embedding(image)
                if embedding:
                    samples.append({"angle": angle, "embedding": embedding})
            if not samples:
                continue
            payload = json.dumps({"samples": samples})
            existing = fetch_one("SELECT id FROM face_templates WHERE student_id = %s", (student_id,))
            if existing:
                execute_query(
                    "UPDATE face_templates SET embedding_data = %s, samples_count = %s, model_name = %s WHERE student_id = %s",
                    (payload, len(samples), self.IDENTITY_MODEL, student_id)
                )
            else:
                execute_query(
                    "INSERT INTO face_templates (student_id, embedding_data, model_name, samples_count) VALUES (%s, %s, %s, %s)",
                    (student_id, payload, self.IDENTITY_MODEL, len(samples))
                )

    def calculate_similarity(self, embedding1, embedding2):
        """
        Computes cosine similarity between two feature vectors.
        Returns float between 0.0 and 1.0.
        """
        if not embedding1 or not embedding2:
            return 0.0
        vec1 = np.array(embedding1, dtype=np.float32)
        vec2 = np.array(embedding2, dtype=np.float32)

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.0

        similarity = float(np.dot(vec1, vec2) / (norm1 * norm2))
        return max(0.0, min(1.0, (similarity + 1.0) / 2.0)) # Scaled to [0, 1]

    def register_student_face(self, student_id: int, image_bgr, angle: str = "front"):
        """
        Stores one face view for a student. Repeating the same angle replaces that view.
        Several angles (front, left, right, up, down, other) are kept together.
        """
        angle = (angle or "front").strip().lower()
        if angle not in self.FACE_ANGLES:
            angle = "other"

        faces = self.detect_faces(image_bgr)
        used_guide = False
        if len(faces) > 1:
            # Keep the largest face so a busy background does not block enrollment.
            faces = [self._largest_face(faces)]

        if faces:
            x, y, w, h = faces[0]
            pad = int(0.15 * max(w, h))
            h_img, w_img = image_bgr.shape[:2]
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w_img, x + w + pad)
            y2 = min(h_img, y + h + pad)
            face_roi = image_bgr[y1:y2, x1:x2]
        else:
            face_roi = self._guided_center_crop(image_bgr)
            used_guide = True

        embedding = self.extract_face_embedding(face_roi)
        if not embedding:
            return {
                "success": False,
                "message": "Could not read a face from this photo. Move closer, face the light, and try again."
            }

        upload_dir = os.path.join(Config.UPLOAD_FOLDER, "faces")
        os.makedirs(upload_dir, exist_ok=True)
        angle_name = f"student_{student_id}_{angle}.jpg"
        cv2.imwrite(os.path.join(upload_dir, angle_name), cv2.resize(face_roi, (200, 200)))

        existing = fetch_one(
            "SELECT embedding_data FROM face_templates WHERE student_id = %s",
            (student_id,)
        )
        samples = self._load_samples(existing["embedding_data"]) if existing else []
        samples = [
            sample for sample in samples
            if sample.get("angle") != angle and len(sample.get("embedding") or []) == len(embedding)
        ]
        samples.append({"angle": angle, "embedding": embedding})

        embedding_json = json.dumps({"samples": samples})
        if existing:
            execute_query(
                "UPDATE face_templates SET embedding_data = %s, samples_count = %s, model_name = %s WHERE student_id = %s",
                (embedding_json, len(samples), self.IDENTITY_MODEL, student_id)
            )
        else:
            execute_query(
                "INSERT INTO face_templates (student_id, embedding_data, model_name, samples_count) VALUES (%s, %s, %s, %s)",
                (student_id, embedding_json, self.IDENTITY_MODEL, len(samples))
            )

        front_file = os.path.join(upload_dir, f"student_{student_id}_front.jpg")
        avatar_file = os.path.join(upload_dir, f"student_{student_id}.jpg")
        source_thumb = front_file if os.path.exists(front_file) else os.path.join(upload_dir, angle_name)
        avatar_rel_path = f"/static/uploads/faces/student_{student_id}.jpg"
        if os.path.exists(source_thumb):
            cv2.imwrite(avatar_file, cv2.imread(source_thumb))

        execute_query(
            "UPDATE students SET face_registered = 1, avatar_url = %s WHERE id = %s",
            (avatar_rel_path, student_id)
        )

        saved_angles = [sample["angle"] for sample in samples]
        note = " Saved from the guide box because the face was at an angle." if used_guide else ""
        return {
            "success": True,
            "message": f"{angle.replace('_', ' ').title()} photo saved.{note}",
            "angle": angle,
            "samples_count": len(samples),
            "saved_angles": saved_angles,
            "avatar_url": avatar_rel_path,
            "guided": used_guide
        }

    def remove_student_face(self, student_id: int):
        """
        Deletes student's registered face template and clears face_registered status.
        Ensures compliance with student biometric privacy rights.
        """
        execute_query("DELETE FROM face_templates WHERE student_id = %s", (student_id,))
        execute_query(
            "UPDATE students SET face_registered = 0, avatar_url = '/static/images/avatars/default_avatar.png' WHERE id = %s",
            (student_id,)
        )
        faces_dir = os.path.join(Config.UPLOAD_FOLDER, "faces")
        if os.path.isdir(faces_dir):
            prefix = f"student_{student_id}"
            for name in os.listdir(faces_dir):
                if name.startswith(prefix) and name.lower().endswith((".jpg", ".jpeg", ".png")):
                    try:
                        os.remove(os.path.join(faces_dir, name))
                    except OSError:
                        pass
        return {"success": True, "message": "All saved face photos for this student were removed."}

    def recognize_faces_in_frame(self, image_bgr, threshold: float = 0.65):
        """
        Analyzes a camera frame, detects all faces, and matches against registered templates.
        Returns list of detection dictionaries:
        [
            {
                "bbox": [x, y, w, h],
                "student_id": int or None,
                "full_name": str,
                "roll_number": str,
                "confidence": float,
                "status": "recognized" | "low_confidence" | "unknown"
            }
        ]
        """
        bboxes = self.detect_faces(image_bgr)
        if not bboxes:
            return []

        self.refresh_saved_templates()
        templates = fetch_all("""
            SELECT ft.student_id, ft.embedding_data, s.full_name, s.roll_number, s.avatar_url
            FROM face_templates ft
            JOIN students s ON ft.student_id = s.id
            WHERE s.consent_given = 1;
        """)

        pending = []
        for (x, y, w, h) in bboxes:
            face_roi = image_bgr[y:y + h, x:x + w]
            embedding = self.extract_face_embedding(face_roi)
            ranked = self._rank_templates(embedding, templates) if embedding else []
            match, score, status = self._decision(ranked, threshold)
            pending.append({
                "bbox": [x, y, w, h],
                "match": match,
                "score": score,
                "status": status
            })

        # One student can own only the strongest face in this frame.
        pending.sort(key=lambda item: item["score"], reverse=True)
        claimed = set()
        results = []
        for item in pending:
            match = item["match"]
            status = item["status"]
            student_id = None
            full_name = "Unknown Face"
            roll_number = "N/A"
            avatar_url = "/static/images/avatars/default_avatar.png"
            if match and status == "recognized":
                if match["student_id"] in claimed:
                    status = "low_confidence"
                    full_name = match["full_name"] + " (Duplicate)"
                    roll_number = match["roll_number"]
                    avatar_url = match["avatar_url"]
                else:
                    claimed.add(match["student_id"])
                    student_id = match["student_id"]
                    full_name = match["full_name"]
                    roll_number = match["roll_number"]
                    avatar_url = match["avatar_url"]
            elif match and status == "low_confidence":
                full_name = match["full_name"] + " (Verify)"
                roll_number = match["roll_number"]
                avatar_url = match["avatar_url"]
            results.append({
                "bbox": item["bbox"],
                "student_id": student_id,
                "full_name": full_name,
                "roll_number": roll_number,
                "avatar_url": avatar_url,
                "confidence": round(float(item["score"]), 2),
                "status": status
            })
        return results

    def accumulate_observation(self, session_id: int, student_id: int, confidence: float, min_observations: int = 3):
        """
        Accumulates observations across multiple frames to satisfy attendance criteria.
        Returns:
            marked: bool (True if this observation met the threshold and marked attendance)
            obs_count: int
            avg_confidence: float
        """
        if session_id not in self._session_observations:
            self._session_observations[session_id] = {}

        student_obs = self._session_observations[session_id].setdefault(
            student_id, {"count": 0, "confidences": []}
        )

        student_obs["count"] += 1
        student_obs["confidences"].append(confidence)

        obs_count = student_obs["count"]
        avg_conf = round(float(np.mean(student_obs["confidences"])), 2)

        # Check if already marked present in database
        existing = fetch_one(
            "SELECT id, status FROM attendance_records WHERE session_id = %s AND student_id = %s",
            (session_id, student_id)
        )

        if existing:
            # Update observations count if already recorded
            execute_query(
                "UPDATE attendance_records SET repeated_observations = %s, confidence_score = %s WHERE id = %s",
                (obs_count, avg_conf, existing["id"])
            )
            return False, obs_count, avg_conf

        # Mark present only after meeting repeated-observation threshold!
        if obs_count >= min_observations:
            execute_query(
                """
                INSERT INTO attendance_records
                (session_id, student_id, status, verification_method, confidence_score, repeated_observations)
                VALUES (%s, %s, 'present', 'ai_face_recognition', %s, %s)
                """,
                (session_id, student_id, avg_conf, obs_count)
            )

            # Update session total_present counter
            execute_query(
                "UPDATE attendance_sessions SET total_present = total_present + 1 WHERE id = %s",
                (session_id,)
            )

            return True, obs_count, avg_conf

        return False, obs_count, avg_conf

    def match_group_photo(self, image_bgr, class_section: str, threshold: float = 0.65, review_margin: float = 0.12):
        """
        Detects every face in a classroom photo and compares embeddings with students
        enrolled in the selected class. Uncertain scores stay Needs Review.
        The same student is kept once; extra detections are marked duplicate.
        """
        boxes = self.detect_faces(image_bgr, group=True)
        self.refresh_saved_templates()
        templates = fetch_all(
            """
            SELECT ft.student_id, ft.embedding_data, s.full_name, s.roll_number, s.student_id AS enrollment_no
            FROM face_templates ft
            JOIN students s ON ft.student_id = s.id
            WHERE s.consent_given = 1 AND s.class_section = %s
            """,
            (class_section,)
        )
        detections = []
        for (x, y, w, h) in boxes:
            roi = image_bgr[y:y + h, x:x + w]
            embedding = self.extract_face_embedding(roi)
            ranked = self._rank_templates(embedding, templates) if embedding else []
            best, best_sim, status = self._decision(ranked, threshold)
            if status == "recognized":
                result = "matched"
            elif status == "low_confidence":
                result = "needs_review"
            else:
                result = "unmatched"
                best = None
            detections.append({
                "bbox": [int(x), int(y), int(w), int(h)],
                "student_id": best["student_id"] if best else None,
                "full_name": best["full_name"] if best else None,
                "roll_number": best["roll_number"] if best else None,
                "confidence": round(max(float(best_sim), 0.0), 3),
                "match_result": result
            })

        best_by_student = {}
        for index, det in enumerate(detections):
            sid = det["student_id"]
            if not sid or det["match_result"] == "unmatched":
                continue
            current = best_by_student.get(sid)
            if current is None or det["confidence"] > detections[current]["confidence"]:
                best_by_student[sid] = index
        for index, det in enumerate(detections):
            sid = det["student_id"]
            if sid and sid in best_by_student and best_by_student[sid] != index:
                det["match_result"] = "duplicate"
        return detections

    def clear_session_cache(self, session_id: int):
        """Cleans up memory when an attendance session concludes."""
        if session_id in self._session_observations:
            del self._session_observations[session_id]


face_service = FaceRecognitionService()
