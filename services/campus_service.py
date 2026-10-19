"""
Group-photo attendance, leave applications, late arrivals, and teacher workload helpers.
Recognition compares detected faces with enrolled embeddings. It does not invent arrival times.
"""
import datetime
import os
import logging
import cv2
from config import Config
from database.db_manager import fetch_one, fetch_all, execute_query
from services.face_recognition_service import face_service
from services.attendance_service import attendance_service, _grace_minutes, _upsert_late_row

logger = logging.getLogger("AutoAttend-Campus")

ATTENDANCE_CHOICES = ("present", "late", "absent", "needs_review", "approved_leave", "unmarked")


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def setting_float(key, default):
    row = fetch_one("SELECT value_text FROM system_settings WHERE key_name = %s", (key,))
    try:
        return float(row["value_text"]) if row else default
    except (TypeError, ValueError):
        return default


def notify(user_id, title, body, kind="info"):
    if not user_id:
        return
    execute_query(
        "INSERT INTO notifications (user_id, title, body, kind, is_read) VALUES (%s, %s, %s, %s, 0)",
        (user_id, title, body, kind)
    )


def notify_teachers(title, body, kind="info"):
    teachers = fetch_all("SELECT id FROM users WHERE role IN ('teacher', 'admin')")
    for teacher in teachers:
        notify(teacher["id"], title, body, kind)


def user_for_student(student_id):
    return fetch_one("SELECT id FROM users WHERE student_ref_id = %s", (student_id,))


def approved_leave_on(student_id, day):
    row = fetch_one(
        """
        SELECT id FROM leave_applications
        WHERE student_id = %s AND status = 'approved' AND start_date <= %s AND end_date >= %s
        LIMIT 1
        """,
        (student_id, day, day)
    )
    return row is not None


def attendance_policy(student_id):
    """
    Present and late count as attended.
    Approved leave is excluded from both the numerator and the denominator.
    Needs-review and unmarked rows stay out of the percentage until a teacher decides.
    """
    records = fetch_all(
        """
        SELECT ar.status, s.session_date
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        WHERE ar.student_id = %s
        """,
        (student_id,)
    )
    attended = 0
    counted = 0
    for record in records:
        status = (record.get("status") or "").lower()
        day = str(record.get("session_date") or "")[:10]
        if status in ("needs_review", "unmarked", "flagged", ""):
            continue
        if status == "approved_leave" or approved_leave_on(student_id, day):
            continue
        counted += 1
        if status in ("present", "late"):
            attended += 1
    percentage = round((attended / counted) * 100, 1) if counted else None
    return {"attended": attended, "counted_sessions": counted, "percentage": percentage}


def existing_attendance_warning(class_section, subject_id, attendance_date, lecture_slot_id):
    params = [attendance_date, subject_id, class_section]
    slot_sql = ""
    if lecture_slot_id:
        slot_sql = " AND (s.lecture_slot_id = %s OR s.lecture_slot_id IS NULL)"
        params.append(lecture_slot_id)
    row = fetch_one(
        f"""
        SELECT COUNT(*) AS cnt
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        WHERE s.session_date = %s AND s.subject_id = %s AND s.class_section = %s
        {slot_sql}
        """,
        tuple(params)
    )
    count = int(row["cnt"]) if row else 0
    if count <= 0:
        return None
    return (
        f"Attendance already exists for this class, subject, and date ({count} record(s)). "
        "Confirming will update those students instead of creating duplicates."
    )


def _draw_annotations(image_bgr, detections):
    colors = {
        "matched": (46, 160, 67),
        "needs_review": (20, 140, 220),
        "unmatched": (60, 60, 220),
        "duplicate": (140, 140, 140),
    }
    canvas = image_bgr.copy()
    for det in detections:
        x, y, w, h = det["bbox"]
        color = colors.get(det["match_result"], (180, 180, 180))
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
        label = det["full_name"] or "Unmatched"
        if det["match_result"] == "duplicate":
            label = f"Duplicate {label}"
        elif det["match_result"] == "needs_review":
            label = f"Review {label}"
        cv2.rectangle(canvas, (x, max(0, y - 22)), (x + max(w, 120), y), color, -1)
        cv2.putText(canvas, label[:28], (x + 4, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return canvas


def analyze_group_photo(image_bgr, teacher_id, class_section, subject_id, lecture_slot_id, attendance_date, observation_time, original_name):
    threshold = setting_float("face_match_threshold", Config.FACE_MATCH_THRESHOLD)
    margin = setting_float("review_margin", 0.12)
    detections = face_service.match_group_photo(image_bgr, class_section, threshold, margin)
    annotated = _draw_annotations(image_bgr, detections)

    folder = os.path.join(Config.UPLOAD_FOLDER, "group_photos")
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    photo_name = f"class_{stamp}.jpg"
    annotated_name = f"class_{stamp}_marked.jpg"
    cv2.imwrite(os.path.join(folder, photo_name), image_bgr)
    cv2.imwrite(os.path.join(folder, annotated_name), annotated)
    photo_path = f"/static/uploads/group_photos/{photo_name}"
    annotated_path = f"/static/uploads/group_photos/{annotated_name}"

    warning = existing_attendance_warning(class_section, subject_id, attendance_date, lecture_slot_id)
    matched = [d for d in detections if d["match_result"] == "matched"]
    review = [d for d in detections if d["match_result"] == "needs_review"]
    unmatched = [d for d in detections if d["match_result"] == "unmatched"]
    uploaded_at = now_text()
    processed_at = now_text()

    created = execute_query(
        """
        INSERT INTO group_photo_batches
        (teacher_id, class_section, subject_id, lecture_slot_id, attendance_date, observation_time,
         photo_path, annotated_path, upload_timestamp, processing_timestamp, status,
         faces_detected, matched_count, unmatched_count, review_count, existing_warning)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s)
        """,
        (
            teacher_id, class_section, subject_id, lecture_slot_id or None, attendance_date,
            observation_time or None, photo_path, annotated_path, uploaded_at, processed_at,
            len(detections), len(matched), len(unmatched), len(review), warning
        )
    )
    batch_id = created["last_id"]
    seen_students = set()
    arrival = "present_at_observation" if observation_time else "present_time_unknown"

    for det in detections:
        if det["match_result"] == "matched":
            status = "approved_leave" if approved_leave_on(det["student_id"], attendance_date) else "present"
            seen_students.add(det["student_id"])
        elif det["match_result"] == "needs_review":
            status = "needs_review"
            if det["student_id"]:
                seen_students.add(det["student_id"])
        elif det["match_result"] == "duplicate":
            status = "unmarked"
        else:
            status = "unmarked"
        execute_query(
            """
            INSERT INTO group_photo_faces
            (batch_id, student_id, bbox, confidence, match_result, attendance_status, arrival_status, verification_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            """,
            (
                batch_id, det["student_id"], ",".join(str(n) for n in det["bbox"]),
                det["confidence"], det["match_result"], status,
                arrival if det["match_result"] == "matched" else "unknown"
            )
        )

    enrolled = fetch_all(
        """
        SELECT id, full_name, roll_number, student_id AS enrollment_no
        FROM students
        WHERE class_section = %s AND consent_given = 1
        ORDER BY full_name
        """,
        (class_section,)
    )
    for student in enrolled:
        if student["id"] in seen_students:
            continue
        status = "approved_leave" if approved_leave_on(student["id"], attendance_date) else "unmarked"
        execute_query(
            """
            INSERT INTO group_photo_faces
            (batch_id, student_id, bbox, confidence, match_result, attendance_status, arrival_status, verification_status)
            VALUES (%s, %s, NULL, 0, 'not_in_photo', %s, 'not_observed', 'pending')
            """,
            (batch_id, student["id"], status)
        )

    attendance_service.log_audit(
        teacher_id, "GROUP_PHOTO_ANALYZED", "group_photo_batches", batch_id,
        f"Detected {len(detections)} faces in {original_name} for {class_section} on {attendance_date}. Not saved yet."
    )
    return batch_payload(batch_id)


def batch_payload(batch_id):
    batch = fetch_one(
        """
        SELECT b.*, sub.subject_name, sub.subject_code, slot.title AS slot_title, slot.start_time AS slot_start
        FROM group_photo_batches b
        JOIN subjects sub ON sub.id = b.subject_id
        LEFT JOIN lecture_slots slot ON slot.id = b.lecture_slot_id
        WHERE b.id = %s
        """,
        (batch_id,)
    )
    if not batch:
        return None
    faces = fetch_all(
        """
        SELECT f.*, s.full_name, s.roll_number, s.student_id AS enrollment_no
        FROM group_photo_faces f
        LEFT JOIN students s ON s.id = f.student_id
        WHERE f.batch_id = %s
        ORDER BY f.id
        """,
        (batch_id,)
    )
    enrolled = fetch_one(
        "SELECT COUNT(*) AS cnt FROM students WHERE class_section = %s AND consent_given = 1",
        (batch["class_section"],)
    )
    return {
        "batch": batch,
        "faces": faces,
        "summary": {
            "enrolled": enrolled["cnt"] if enrolled else 0,
            "faces_detected": batch["faces_detected"],
            "matched": batch["matched_count"],
            "unmatched": batch["unmatched_count"],
            "needs_review": batch["review_count"],
        }
    }


def update_face_statuses(batch_id, updates):
    batch = fetch_one("SELECT id, status FROM group_photo_batches WHERE id = %s", (batch_id,))
    if not batch:
        return {"success": False, "message": "Photo batch not found."}
    if batch["status"] == "confirmed":
        return {"success": False, "message": "This photo was already confirmed. Open the records to correct a saved row."}
    for item in updates:
        face_id = item.get("id")
        status = (item.get("attendance_status") or "").lower()
        if status not in ATTENDANCE_CHOICES:
            continue
        execute_query(
            "UPDATE group_photo_faces SET attendance_status = %s WHERE id = %s AND batch_id = %s",
            (status, face_id, batch_id)
        )
    return {"success": True}


def confirm_batch(batch_id, teacher_id, updates):
    if updates:
        saved = update_face_statuses(batch_id, updates)
        if not saved.get("success"):
            return saved
    payload = batch_payload(batch_id)
    if not payload:
        return {"success": False, "message": "Photo batch not found."}
    batch = payload["batch"]
    if batch["status"] == "confirmed":
        return {"success": False, "message": "Attendance for this photo is already confirmed."}

    slot = None
    if batch.get("lecture_slot_id"):
        slot = fetch_one("SELECT * FROM lecture_slots WHERE id = %s", (batch["lecture_slot_id"],))
    classroom_id = slot["classroom_id"] if slot else 1
    start_time = (batch.get("observation_time") or (slot["start_time"] if slot else None) or "09:00:00")
    start_time = str(start_time)[:8]

    session = fetch_one(
        """
        SELECT id FROM attendance_sessions
        WHERE session_date = %s AND subject_id = %s AND class_section = %s
          AND (lecture_slot_id = %s OR (%s IS NULL AND lecture_slot_id IS NULL))
        ORDER BY id DESC LIMIT 1
        """,
        (batch["attendance_date"], batch["subject_id"], batch["class_section"], batch.get("lecture_slot_id"), batch.get("lecture_slot_id"))
    )
    if session:
        session_id = session["id"]
    else:
        day_key = str(batch["attendance_date"])[:10].replace("-", "")
        code = f"PHOTO-{day_key}-{batch_id}"
        created = execute_query(
            """
            INSERT INTO attendance_sessions
            (session_code, classroom_id, subject_id, teacher_id, session_date, start_time, status,
             class_section, lecture_slot_id, is_demo_mode)
            VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s, %s, 0)
            """,
            (
                code, classroom_id, batch["subject_id"], teacher_id, batch["attendance_date"],
                start_time, batch["class_section"], batch.get("lecture_slot_id")
            )
        )
        session_id = created["last_id"]

    saved_rows = 0
    skipped = 0
    for face in payload["faces"]:
        status = (face.get("attendance_status") or "unmarked").lower()
        if not face.get("student_id") or status == "unmarked" or face.get("match_result") == "duplicate":
            skipped += 1
            continue
        if status == "late" and face.get("arrival_status") in ("unknown", "present_time_unknown", "present_at_observation", "not_observed"):
            face_arrival = "teacher_marked_without_timestamp"
        else:
            face_arrival = face.get("arrival_status") or "unknown"
        existing = fetch_one(
            "SELECT id FROM attendance_records WHERE session_id = %s AND student_id = %s",
            (session_id, face["student_id"])
        )
        note = f"Group photo batch #{batch_id}"
        if existing:
            execute_query(
                """
                UPDATE attendance_records
                SET status = %s, verification_method = 'group_photo', confidence_score = %s,
                    is_manually_edited = 1, audit_note = %s, edited_by = %s, arrival_status = %s,
                    teacher_verification = 'verified', updated_at = %s
                WHERE id = %s
                """,
                (status, face.get("confidence") or 0, note, teacher_id, face_arrival, now_text(), existing["id"])
            )
        else:
            execute_query(
                """
                INSERT INTO attendance_records
                (session_id, student_id, timestamp, status, verification_method, confidence_score,
                 repeated_observations, is_manually_edited, audit_note, edited_by, arrival_status, teacher_verification)
                VALUES (%s, %s, %s, %s, 'group_photo', %s, 1, 1, %s, %s, %s, 'verified')
                """,
                (
                    session_id, face["student_id"], f"{batch['attendance_date']} {start_time}",
                    status, face.get("confidence") or 0, note, teacher_id, face_arrival
                )
            )
        execute_query(
            "UPDATE group_photo_faces SET verification_status = 'verified' WHERE id = %s",
            (face["id"],)
        )
        saved_rows += 1

    present_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM attendance_records WHERE session_id = %s AND status IN ('present', 'late')",
        (session_id,)
    )
    execute_query(
        "UPDATE attendance_sessions SET total_present = %s, total_detected = %s, status = 'completed' WHERE id = %s",
        (present_count["cnt"] if present_count else 0, batch["faces_detected"], session_id)
    )
    confirmed_at = now_text()
    execute_query(
        """
        UPDATE group_photo_batches
        SET status = 'confirmed', session_id = %s, confirmed_by = %s, confirmation_timestamp = %s
        WHERE id = %s
        """,
        (session_id, teacher_id, confirmed_at, batch_id)
    )
    attendance_service.log_audit(
        teacher_id, "GROUP_PHOTO_CONFIRMED", "group_photo_batches", batch_id,
        f"Saved {saved_rows} attendance rows for {batch['attendance_date']}. Skipped {skipped} unmarked or duplicate faces."
    )
    return {
        "success": True,
        "message": f"Attendance saved for {saved_rows} students. {skipped} unmarked or duplicate faces were left unchanged.",
        "session_id": session_id,
        "saved": saved_rows,
        "skipped": skipped
    }


def list_late(filters):
    conditions = ["1=1"]
    params = []
    queue = (filters.get("queue") or "waiting").strip().lower()
    if queue == "waiting":
        conditions.append("(l.review_status IS NULL OR l.review_status = 'pending')")
    elif queue == "done":
        conditions.append("l.review_status IN ('present', 'absent', 'approved_leave')")
    if filters.get("date"):
        conditions.append("l.attendance_date = %s")
        params.append(filters["date"])
    if filters.get("month"):
        conditions.append("l.attendance_date LIKE %s")
        params.append(filters["month"] + "%")
    if filters.get("class_section"):
        conditions.append("l.class_section = %s")
        params.append(filters["class_section"])
    if filters.get("subject_id"):
        conditions.append("l.subject_id = %s")
        params.append(filters["subject_id"])
    if filters.get("student_id"):
        conditions.append("l.student_id = %s")
        params.append(filters["student_id"])
    rows = fetch_all(
        f"""
        SELECT l.*, s.full_name, s.roll_number, sub.subject_name, sub.subject_code,
               editor.full_name AS corrected_by_name,
               decider.full_name AS decided_by_name
        FROM late_arrivals l
        JOIN students s ON s.id = l.student_id
        JOIN subjects sub ON sub.id = l.subject_id
        LEFT JOIN users editor ON editor.id = l.corrected_by
        LEFT JOIN users decider ON decider.id = l.decided_by
        WHERE {' AND '.join(conditions)}
        ORDER BY l.attendance_date DESC, l.arrival_time DESC
        """,
        tuple(params)
    )
    return rows


def manual_checkin(teacher_id, student_id, subject_id, attendance_date, arrival_time, lecture_start=None):
    student = fetch_one("SELECT * FROM students WHERE id = %s", (student_id,))
    if not student:
        return {"success": False, "message": "Student not found."}
    slot = fetch_one(
        """
        SELECT * FROM lecture_slots
        WHERE class_section = %s AND subject_id = %s AND is_active = 1
        ORDER BY id LIMIT 1
        """,
        (student["class_section"], subject_id)
    )
    start_text = lecture_start or (str(slot["start_time"])[:8] if slot else "09:00:00")
    if len(start_text) == 5:
        start_text += ":00"
    arrival_text = arrival_time.replace("T", " ")
    if len(arrival_text) == 16:
        arrival_text += ":00"
    start_dt = datetime.datetime.strptime(f"{attendance_date} {start_text}", "%Y-%m-%d %H:%M:%S")
    arrival_dt = datetime.datetime.strptime(arrival_text[:19], "%Y-%m-%d %H:%M:%S")
    grace = int(slot["grace_minutes"]) if slot else _grace_minutes(student["class_section"], subject_id)
    elapsed = int((arrival_dt - start_dt).total_seconds() // 60)
    minutes_late = max(0, elapsed - grace)
    if minutes_late <= 0:
        return {
            "success": True,
            "late": False,
            "message": "This arrival is inside the grace period, so the student is not marked late."
        }
    late_id = _upsert_late_row(
        student_id=student_id,
        class_section=student["class_section"],
        subject_id=subject_id,
        session_id=None,
        attendance_date=attendance_date,
        lecture_start=start_text,
        arrival_time=arrival_dt.strftime("%Y-%m-%d %H:%M:%S"),
        grace_minutes=grace,
        minutes_late=minutes_late,
        source="manual_checkin"
    )
    attendance_service.log_audit(
        teacher_id, "LATE_CHECKIN", "late_arrivals", late_id,
        f"{student['full_name']} arrived {minutes_late} minutes late on {attendance_date}."
    )
    return {"success": True, "late": True, "minutes_late": minutes_late, "id": late_id}


def correct_late(late_id, teacher_id, arrival_time, note):
    row = fetch_one("SELECT * FROM late_arrivals WHERE id = %s", (late_id,))
    if not row:
        return {"success": False, "message": "Late record not found."}
    arrival_text = arrival_time.replace("T", " ")
    if len(arrival_text) == 16:
        arrival_text += ":00"
    start_text = str(row["lecture_start"])[:8]
    if len(start_text) == 5:
        start_text += ":00"
    start_dt = datetime.datetime.strptime(f"{str(row['attendance_date'])[:10]} {start_text}", "%Y-%m-%d %H:%M:%S")
    arrival_dt = datetime.datetime.strptime(arrival_text[:19], "%Y-%m-%d %H:%M:%S")
    elapsed = int((arrival_dt - start_dt).total_seconds() // 60)
    minutes_late = max(0, elapsed - int(row["grace_minutes"]))
    execute_query(
        """
        UPDATE late_arrivals
        SET arrival_time = %s, minutes_late = %s, correction_note = %s, corrected_by = %s, updated_at = %s
        WHERE id = %s
        """,
        (arrival_dt.strftime("%Y-%m-%d %H:%M:%S"), minutes_late, note, teacher_id, now_text(), late_id)
    )
    attendance_service.log_audit(
        teacher_id, "LATE_CORRECTED", "late_arrivals", late_id,
        f"Arrival corrected to {arrival_text}. Minutes late is now {minutes_late}. Note: {note}"
    )
    return {"success": True, "minutes_late": minutes_late, "message": "Late record corrected and logged."}


def decide_late(late_id, teacher_id, status, note=""):
    """Teacher sets a flagged late arrival to present, absent, or leave."""
    choices = {
        "present": "present",
        "absent": "absent",
        "leave": "approved_leave",
        "approved_leave": "approved_leave",
    }
    stored = choices.get((status or "").strip().lower())
    if not stored:
        return {"success": False, "message": "Choose present, absent, or leave."}
    row = fetch_one("SELECT * FROM late_arrivals WHERE id = %s", (late_id,))
    if not row:
        return {"success": False, "message": "Late record not found."}
    labels = {
        "present": "Present",
        "absent": "Absent",
        "approved_leave": "Leave",
    }
    reason = note or f"Teacher marked this late arrival as {labels[stored].lower()}."
    _apply_late_decision(row, stored, teacher_id, reason)
    execute_query(
        """
        UPDATE late_arrivals
        SET review_status = %s, decided_by = %s, decision_note = %s, updated_at = %s
        WHERE id = %s
        """,
        (stored, teacher_id, reason, now_text(), late_id)
    )
    student = fetch_one("SELECT full_name, roll_number FROM students WHERE id = %s", (row["student_id"],))
    attendance_service.log_audit(
        teacher_id, "LATE_DECIDED", "late_arrivals", late_id,
        f"{student['full_name']} marked {labels[stored]} for {row['attendance_date']}. {reason}"
    )
    user = user_for_student(row["student_id"])
    if user:
        notify(
            user["id"],
            "Attendance updated",
            f"Your late arrival on {str(row['attendance_date'])[:10]} was marked {labels[stored].lower()}.",
            "attendance"
        )
    return {
        "success": True,
        "status": stored,
        "message": f"{student['full_name']} is marked {labels[stored].lower()}."
    }


def _apply_late_decision(row, status, teacher_id, note):
    """Writes the teacher's choice onto the official attendance row."""
    record = None
    if row.get("session_id"):
        record = fetch_one(
            "SELECT id FROM attendance_records WHERE session_id = %s AND student_id = %s",
            (row["session_id"], row["student_id"])
        )
    if not record:
        record = fetch_one(
            """
            SELECT ar.id
            FROM attendance_records ar
            JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE ar.student_id = %s AND s.subject_id = %s AND s.session_date = %s
            ORDER BY ar.id DESC
            LIMIT 1
            """,
            (row["student_id"], row["subject_id"], str(row["attendance_date"])[:10])
        )
    if record:
        attendance_service.update_attendance_status(record["id"], status, note, teacher_id)
        return

    slot = fetch_one(
        """
        SELECT classroom_id FROM lecture_slots
        WHERE class_section = %s AND subject_id = %s
        ORDER BY id LIMIT 1
        """,
        (row["class_section"], row["subject_id"])
    )
    classroom_id = slot["classroom_id"] if slot else 1
    day = str(row["attendance_date"])[:10]
    created = execute_query(
        """
        INSERT INTO attendance_sessions
        (session_code, classroom_id, subject_id, teacher_id, session_date, start_time, end_time,
         status, class_section, is_demo_mode)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', %s, 0)
        """,
        (
            f"LATE-{row['id']}-{day.replace('-', '')}",
            classroom_id, row["subject_id"], teacher_id, day,
            str(row["lecture_start"] or "09:00:00")[:8],
            str(row["lecture_start"] or "09:00:00")[:8],
            row["class_section"]
        )
    )
    execute_query(
        """
        INSERT INTO attendance_records
        (session_id, student_id, status, verification_method, confidence_score,
         repeated_observations, is_manually_edited, audit_note, edited_by)
        VALUES (%s, %s, %s, 'teacher_late_review', 0, 0, 1, %s, %s)
        """,
        (created["last_id"], row["student_id"], status, note, teacher_id)
    )


def update_slot(slot_id, start_time, grace_minutes, teacher_id):
    if len(start_time) == 5:
        start_time += ":00"
    execute_query(
        "UPDATE lecture_slots SET start_time = %s, grace_minutes = %s WHERE id = %s",
        (start_time, int(grace_minutes), slot_id)
    )
    attendance_service.log_audit(
        teacher_id, "SLOT_UPDATED", "lecture_slots", slot_id,
        f"Lecture start set to {start_time} with a {grace_minutes} minute grace period."
    )
    return {"success": True}


def submit_leave(student_id, start_date, end_date, reason, attachment_path=None):
    if end_date < start_date:
        return {"success": False, "message": "The end date must be on or after the start date."}
    if not reason or len(reason.strip()) < 5:
        return {"success": False, "message": "Please enter a reason of at least a few words."}
    result = execute_query(
        """
        INSERT INTO leave_applications (student_id, start_date, end_date, reason, attachment_path, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
        """,
        (student_id, start_date, end_date, reason.strip(), attachment_path)
    )
    student = fetch_one("SELECT full_name, roll_number FROM students WHERE id = %s", (student_id,))
    notify_teachers(
        "New leave application",
        f"{student['full_name']} ({student['roll_number']}) requested leave from {start_date} to {end_date}.",
        "leave"
    )
    return {"success": True, "id": result["last_id"], "message": "Leave application submitted."}


def decide_leave(leave_id, teacher_id, status, comment):
    if status not in ("approved", "rejected"):
        return {"success": False, "message": "Choose approve or reject."}
    leave = fetch_one("SELECT * FROM leave_applications WHERE id = %s", (leave_id,))
    if not leave:
        return {"success": False, "message": "Application not found."}
    execute_query(
        """
        UPDATE leave_applications
        SET status = %s, teacher_comment = %s, reviewed_by = %s, reviewed_at = %s
        WHERE id = %s
        """,
        (status, comment or "", teacher_id, now_text(), leave_id)
    )
    account = user_for_student(leave["student_id"])
    if account:
        notify(
            account["id"],
            f"Leave {status}",
            f"Your leave from {leave['start_date']} to {leave['end_date']} was {status}. {comment or ''}".strip(),
            "leave"
        )
    attendance_service.log_audit(
        teacher_id, "LEAVE_DECISION", "leave_applications", leave_id,
        f"Leave #{leave_id} {status}. {comment or ''}"
    )
    return {"success": True, "message": f"Application {status}."}


def student_context(student_id):
    policy = attendance_policy(student_id)
    recent = fetch_all(
        """
        SELECT ar.status, ar.timestamp, sub.subject_name, s.session_date
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        JOIN subjects sub ON sub.id = s.subject_id
        WHERE ar.student_id = %s
        ORDER BY s.session_date DESC
        LIMIT 8
        """,
        (student_id,)
    )
    return {"policy": policy, "recent": recent}


def _status_counts(student_id):
    rows = fetch_all(
        """
        SELECT LOWER(COALESCE(status, '')) AS status, COUNT(*) AS cnt
        FROM attendance_records
        WHERE student_id = %s
        GROUP BY LOWER(COALESCE(status, ''))
        """,
        (student_id,)
    )
    counts = {row["status"]: int(row["cnt"]) for row in rows}
    return {
        "present": counts.get("present", 0),
        "late": counts.get("late", 0),
        "absent": counts.get("absent", 0),
        "approved_leave": counts.get("approved_leave", 0),
        "needs_review": counts.get("needs_review", 0) + counts.get("flagged", 0),
    }


def student_home(student_id):
    """Personal dashboard: attendance, today's classes, and leave totals."""
    student = fetch_one(
        """
        SELECT id, full_name, roll_number, student_id AS enrollment_no, email,
               class_section, department, avatar_url
        FROM students WHERE id = %s
        """,
        (student_id,)
    )
    if not student:
        return None
    policy = attendance_policy(student_id)
    counts = _status_counts(student_id)
    pending = fetch_one(
        "SELECT COUNT(*) AS cnt FROM leave_applications WHERE student_id = %s AND status = 'pending'",
        (student_id,)
    )
    approved = fetch_one(
        "SELECT COUNT(*) AS cnt FROM leave_applications WHERE student_id = %s AND status = 'approved'",
        (student_id,)
    )
    late_rows = fetch_one(
        "SELECT COUNT(*) AS cnt FROM late_arrivals WHERE student_id = %s",
        (student_id,)
    )
    recent = fetch_all(
        """
        SELECT ar.status, ar.timestamp, ar.confidence_score, ar.verification_method,
               sub.subject_name, sub.subject_code, s.session_date
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        JOIN subjects sub ON sub.id = s.subject_id
        WHERE ar.student_id = %s
        ORDER BY s.session_date DESC, ar.timestamp DESC
        LIMIT 12
        """,
        (student_id,)
    )
    section = student.get("class_section") or ""
    lectures = [
        slot for slot in today_schedule()
        if not section or slot.get("class_section") == section
    ]
    today = datetime.date.today()
    history = fetch_all(
        """
        SELECT ar.status, s.session_date
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.id = ar.session_id
        WHERE ar.student_id = %s AND s.session_date >= %s
        """,
        (student_id, (today - datetime.timedelta(days=6)).isoformat())
    )
    by_day = {}
    for row in history:
        day = str(row.get("session_date") or "")[:10]
        bucket = by_day.setdefault(day, {"present": 0, "absent": 0})
        status = (row.get("status") or "").lower()
        if status in ("present", "late"):
            bucket["present"] += 1
        elif status == "absent":
            bucket["absent"] += 1
    weekly = []
    for offset in range(6, -1, -1):
        day = today - datetime.timedelta(days=offset)
        key = day.isoformat()
        bucket = by_day.get(key, {"present": 0, "absent": 0})
        weekly.append({
            "day": day.strftime("%a"),
            "date": key,
            "present": bucket["present"],
            "absent": bucket["absent"],
        })
    threshold = setting_float("low_attendance_threshold", 75)
    percentage = policy["percentage"]
    return {
        "student": student,
        "policy": policy,
        "counts": counts,
        "pending_leaves": pending["cnt"] if pending else 0,
        "approved_leaves": approved["cnt"] if approved else 0,
        "late_marks": late_rows["cnt"] if late_rows else 0,
        "recent": recent,
        "lectures": lectures,
        "weekly": weekly,
        "threshold": threshold,
        "below_threshold": percentage is not None and percentage < threshold,
    }


def low_attendance_students():
    threshold = setting_float("low_attendance_threshold", 75)
    students = fetch_all("SELECT id, full_name, roll_number, class_section FROM students ORDER BY full_name")
    flagged = []
    for student in students:
        policy = attendance_policy(student["id"])
        if policy["percentage"] is None or policy["counted_sessions"] < 1:
            continue
        if policy["percentage"] < threshold:
            flagged.append({**student, **policy})
    flagged.sort(key=lambda row: row["percentage"])
    return {"threshold": threshold, "students": flagged}


def today_schedule():
    return fetch_all(
        """
        SELECT slot.*, sub.subject_name, sub.subject_code, c.room_number
        FROM lecture_slots slot
        JOIN subjects sub ON sub.id = slot.subject_id
        JOIN classrooms c ON c.id = slot.classroom_id
        WHERE slot.is_active = 1
        ORDER BY slot.start_time
        """
    )


def teacher_home():
    today = datetime.date.today().isoformat()
    pending = fetch_one("SELECT COUNT(*) AS cnt FROM leave_applications WHERE status = 'pending'")
    late_today = fetch_one("SELECT COUNT(*) AS cnt FROM late_arrivals WHERE attendance_date = %s", (today,))
    notes = fetch_all(
        """
        SELECT id, action, entity_type, details, created_at
        FROM audit_logs
        WHERE action IN ('GROUP_PHOTO_CONFIRMED', 'OVERRIDE_ATTENDANCE', 'LATE_CORRECTED', 'LEAVE_DECISION')
        ORDER BY id DESC LIMIT 8
        """
    )
    return {
        "lectures": today_schedule(),
        "pending_leaves": pending["cnt"] if pending else 0,
        "late_today": late_today["cnt"] if late_today else 0,
        "low_attendance": low_attendance_students(),
        "history": notes,
        "unread_notifications": 0
    }
