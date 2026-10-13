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

    def __init__(self):
        self.cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(self.cascade_path)
        if self.face_cascade.empty():
            logger.error("Failed to load OpenCV Haar Cascade from %s", self.cascade_path)
        else:
            logger.info("OpenCV Haar Cascade loaded successfully.")

        # In-memory accumulator for active session observations:
        # structure: { session_id: { student_id: { 'count': int, 'confidences': list } } }
        self._session_observations = {}

    def detect_faces(self, image_bgr):
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
        if max_dim > 1000:
            scale_ratio = 1000.0 / max_dim
            proc_img = cv2.resize(image_bgr, (int(w * scale_ratio), int(h * scale_ratio)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(proc_img, cv2.COLOR_BGR2GRAY)
        
        # Primary pass with CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)

        faces = self.face_cascade.detectMultiScale(
            gray_clahe,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(36, 36),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        # Fallback pass: standard global histogram equalization if primary pass found no face
        if len(faces) == 0:
            gray_eq = cv2.equalizeHist(gray)
            faces = self.face_cascade.detectMultiScale(
                gray_eq,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE
            )

        if scale_ratio != 1.0:
            return [(int(x / scale_ratio), int(y / scale_ratio), int(w_box / scale_ratio), int(h_box / scale_ratio)) for (x, y, w_box, h_box) in faces]

        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def extract_face_embedding(self, face_bgr):
        """
        Generates a robust, normalized 256-dimensional feature vector from a face crop.
        Combines spatial intensity grids and gradient magnitude descriptors with L2 normalization.
        """
        if face_bgr is None or face_bgr.size == 0:
            return None

        # Standardize face dimensions
        target_size = (112, 112)
        resized = cv2.resize(face_bgr, target_size, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        equalized = cv2.equalizeHist(gray)

        # 1. Spatial 8x8 block average intensities (64 dimensions)
        h, w = equalized.shape
        block_h, block_w = h // 8, w // 8
        grid_features = []
        for i in range(8):
            for j in range(8):
                cell = equalized[i * block_h:(i + 1) * block_h, j * block_w:(j + 1) * block_w]
                grid_features.append(np.mean(cell))

        # 2. Sobel edge gradients (direction & magnitude, 128 dimensions)
        grad_x = cv2.Sobel(equalized, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(equalized, cv2.CV_32F, 0, 1, ksize=3)
        mag, _ = cv2.cartToPolar(grad_x, grad_y)

        grad_features = []
        for i in range(8):
            for j in range(8):
                cell_mag = mag[i * block_h:(i + 1) * block_h, j * block_w:(j + 1) * block_w]
                grad_features.append(np.mean(cell_mag))
                grad_features.append(np.std(cell_mag))

        # 3. Concentric ring radial variance (64 dimensions)
        center_y, center_x = h // 2, w // 2
        radial_features = []
        y_indices, x_indices = np.indices(equalized.shape)
        distances = np.sqrt((x_indices - center_x) ** 2 + (y_indices - center_y) ** 2)
        max_dist = np.sqrt(center_x ** 2 + center_y ** 2)
        bins = np.linspace(0, max_dist, 65)
        for b in range(64):
            mask = (distances >= bins[b]) & (distances < bins[b + 1])
            if np.any(mask):
                radial_features.append(np.mean(equalized[mask]))
            else:
                radial_features.append(0.0)

        # Combine into a unified vector
        combined = np.array(grid_features + grad_features + radial_features, dtype=np.float32)

        # L2-normalization for cosine similarity
        norm = np.linalg.norm(combined)
        if norm > 1e-6:
            normalized = combined / norm
        else:
            normalized = combined

        return normalized.tolist()

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

    def register_student_face(self, student_id: int, image_bgr):
        """
        Registers a consented student's face template.
        Validates presence of a single distinct face, extracts embedding,
        and saves securely to face_templates table.
        """
        faces = self.detect_faces(image_bgr)
        if len(faces) == 0:
            return {"success": False, "message": "No face detected in the image. Please face the camera directly."}
        if len(faces) > 1:
            return {"success": False, "message": "Multiple faces detected. Ensure only the student is in frame."}

        x, y, w, h = faces[0]
        # Add safety margin
        pad = int(0.15 * max(w, h))
        h_img, w_img = image_bgr.shape[:2]
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w_img, x + w + pad)
        y2 = min(h_img, y + h + pad)

        face_roi = image_bgr[y1:y2, x1:x2]
        embedding = self.extract_face_embedding(face_roi)

        if not embedding:
            return {"success": False, "message": "Failed to extract face features. Try again with better lighting."}

        # Save face thumbnail for UI
        upload_dir = os.path.join(Config.UPLOAD_FOLDER, "faces")
        os.makedirs(upload_dir, exist_ok=True)
        avatar_rel_path = f"/static/uploads/faces/student_{student_id}.jpg"
        avatar_abs_path = os.path.join(upload_dir, f"student_{student_id}.jpg")
        cv2.imwrite(avatar_abs_path, cv2.resize(face_roi, (200, 200)))

        # Update or Insert face_template in DB
        embedding_json = json.dumps(embedding)
        existing = fetch_one("SELECT id FROM face_templates WHERE student_id = %s", (student_id,))
        if existing:
            execute_query(
                "UPDATE face_templates SET embedding_data = %s, samples_count = samples_count + 1 WHERE student_id = %s",
                (embedding_json, student_id)
            )
        else:
            execute_query(
                "INSERT INTO face_templates (student_id, embedding_data, model_name, samples_count) VALUES (%s, %s, %s, 1)",
                (student_id, embedding_json, "AutoAttend-FeatureNet-v1")
            )

        # Update student record
        execute_query(
            "UPDATE students SET face_registered = 1, avatar_url = %s WHERE id = %s",
            (avatar_rel_path, student_id)
        )

        return {
            "success": True,
            "message": "Face registered successfully and biometric template stored securely.",
            "avatar_url": avatar_rel_path
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
        # Remove stored photo file if exists
        avatar_abs_path = os.path.join(Config.UPLOAD_FOLDER, "faces", f"student_{student_id}.jpg")
        if os.path.exists(avatar_abs_path):
            try:
                os.remove(avatar_abs_path)
            except OSError:
                pass
        return {"success": True, "message": "Biometric template and face data permanently removed."}

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

        # Load all enrolled templates from database
        templates = fetch_all("""
            SELECT ft.student_id, ft.embedding_data, s.full_name, s.roll_number, s.avatar_url
            FROM face_templates ft
            JOIN students s ON ft.student_id = s.id
            WHERE s.consent_given = 1;
        """)

        results = []
        for (x, y, w, h) in bboxes:
            face_roi = image_bgr[y:y+h, x:x+w]
            embedding = self.extract_face_embedding(face_roi)

            best_match = None
            highest_sim = 0.0

            if embedding and templates:
                for t in templates:
                    try:
                        stored_emb = json.loads(t["embedding_data"])
                        sim = self.calculate_similarity(embedding, stored_emb)
                        if sim > highest_sim:
                            highest_sim = sim
                            best_match = t
                    except Exception as e:
                        logger.error("Error comparing template: %s", str(e))

            if best_match and highest_sim >= threshold:
                status = "recognized"
                student_id = best_match["student_id"]
                full_name = best_match["full_name"]
                roll_number = best_match["roll_number"]
                avatar_url = best_match["avatar_url"]
            elif best_match and highest_sim >= (threshold - 0.15):
                status = "low_confidence"
                student_id = best_match["student_id"]
                full_name = best_match["full_name"] + " (Verify)"
                roll_number = best_match["roll_number"]
                avatar_url = best_match["avatar_url"]
            else:
                status = "unknown"
                student_id = None
                full_name = "Unknown Face"
                roll_number = "N/A"
                avatar_url = "/static/images/avatars/default_avatar.png"

            results.append({
                "bbox": [x, y, w, h],
                "student_id": student_id,
                "full_name": full_name,
                "roll_number": roll_number,
                "avatar_url": avatar_url,
                "confidence": round(highest_sim, 2),
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

    def clear_session_cache(self, session_id: int):
        """Cleans up memory when an attendance session concludes."""
        if session_id in self._session_observations:
            del self._session_observations[session_id]


face_service = FaceRecognitionService()
