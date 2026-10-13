import io
import os
from flask import Blueprint, request, jsonify, session
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
import numpy as np
import cv2
from database.db_manager import fetch_all, fetch_one
from services import campus_service
from routes.auth_routes import login_required

campus_bp = Blueprint("campus", __name__, url_prefix="/api")

ALLOWED_IMAGES = {"jpg", "jpeg", "png", "webp", "bmp"}


def teacher_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(**kwargs):
        if "user_id" not in session:
            return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
        if session.get("user_role") == "student":
            return jsonify({"success": False, "message": "This action is limited to teachers."}), 403
        return view(**kwargs)

    return wrapped


def _image_from_upload(file_storage):
    raw = file_storage.read()
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("Please upload an image smaller than 12 MB.")
    image = Image.open(io.BytesIO(raw))
    image = ImageOps.exif_transpose(image).convert("RGB")
    array = np.array(image)
    return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)


@campus_bp.route("/meta/options", methods=["GET"])
@login_required
def meta_options():
    sections = fetch_all("SELECT DISTINCT class_section FROM students ORDER BY class_section")
    subjects = fetch_all("SELECT id, subject_code, subject_name FROM subjects ORDER BY subject_code")
    classrooms = fetch_all("SELECT id, room_number FROM classrooms WHERE is_active = 1")
    slots = campus_service.today_schedule()
    students = fetch_all("SELECT id, full_name, roll_number, class_section FROM students ORDER BY full_name")
    return jsonify({
        "success": True,
        "class_sections": [row["class_section"] for row in sections],
        "subjects": subjects,
        "classrooms": classrooms,
        "lecture_slots": slots,
        "students": students
    })


@campus_bp.route("/group-photo/analyze", methods=["POST"])
@teacher_required
def analyze_photo():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"success": False, "message": "Choose a classroom photo to upload."}), 400
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if ext not in ALLOWED_IMAGES:
        return jsonify({"success": False, "message": "Use a JPG, JPEG, PNG, WEBP, or BMP image."}), 400
    class_section = (request.form.get("class_section") or "").strip()
    subject_id = request.form.get("subject_id")
    lecture_slot_id = request.form.get("lecture_slot_id") or None
    attendance_date = (request.form.get("attendance_date") or "").strip()
    observation_time = (request.form.get("observation_time") or "").strip()
    if not class_section or not subject_id or not attendance_date:
        return jsonify({"success": False, "message": "Class, subject, and attendance date are required."}), 400
    try:
        image = _image_from_upload(photo)
        payload = campus_service.analyze_group_photo(
            image,
            session["user_id"],
            class_section,
            int(subject_id),
            int(lecture_slot_id) if lecture_slot_id else None,
            attendance_date,
            observation_time,
            secure_filename(photo.filename)
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "message": f"Could not process this photo. {exc}"}), 500
    return jsonify({"success": True, **payload})


@campus_bp.route("/group-photo/<int:batch_id>/confirm", methods=["POST"])
@teacher_required
def confirm_photo(batch_id):
    data = request.get_json() or {}
    result = campus_service.confirm_batch(batch_id, session["user_id"], data.get("updates") or [])
    code = 200 if result.get("success") else 400
    return jsonify(result), code


@campus_bp.route("/group-photo/history", methods=["GET"])
@teacher_required
def photo_history():
    rows = fetch_all(
        """
        SELECT b.id, b.attendance_date, b.class_section, b.status, b.faces_detected, b.matched_count,
               b.upload_timestamp, b.confirmation_timestamp, sub.subject_name
        FROM group_photo_batches b
        JOIN subjects sub ON sub.id = b.subject_id
        ORDER BY b.id DESC
        LIMIT 20
        """
    )
    return jsonify({"success": True, "history": rows})


@campus_bp.route("/late", methods=["GET"])
@teacher_required
def late_list():
    rows = campus_service.list_late({
        "date": request.args.get("date"),
        "month": request.args.get("month"),
        "class_section": request.args.get("class_section"),
        "subject_id": request.args.get("subject_id"),
        "student_id": request.args.get("student_id"),
    })
    return jsonify({"success": True, "records": rows})


@campus_bp.route("/late/checkin", methods=["POST"])
@teacher_required
def late_checkin():
    data = request.get_json() or {}
    try:
        result = campus_service.manual_checkin(
            session["user_id"],
            int(data.get("student_id")),
            int(data.get("subject_id")),
            data.get("attendance_date"),
            data.get("arrival_time"),
            data.get("lecture_start")
        )
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Enter a valid student, subject, date, and arrival time."}), 400
    return jsonify(result), 200 if result.get("success") else 400


@campus_bp.route("/late/<int:late_id>", methods=["PATCH"])
@teacher_required
def late_correct(late_id):
    data = request.get_json() or {}
    note = (data.get("note") or "").strip()
    if len(note) < 3:
        return jsonify({"success": False, "message": "Add a short note explaining the correction."}), 400
    try:
        result = campus_service.correct_late(late_id, session["user_id"], data.get("arrival_time"), note)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Enter a valid arrival time."}), 400
    return jsonify(result), 200 if result.get("success") else 400


@campus_bp.route("/lecture-slots/<int:slot_id>", methods=["PUT"])
@teacher_required
def save_slot(slot_id):
    data = request.get_json() or {}
    if not data.get("start_time"):
        return jsonify({"success": False, "message": "Lecture start time is required."}), 400
    result = campus_service.update_slot(
        slot_id, data.get("start_time"), data.get("grace_minutes") or 10, session["user_id"]
    )
    return jsonify(result)


@campus_bp.route("/leaves", methods=["GET"])
@login_required
def list_leaves():
    status = request.args.get("status")
    params = []
    where = "1=1"
    if session.get("user_role") == "student":
        student = fetch_one("SELECT student_ref_id FROM users WHERE id = %s", (session["user_id"],))
        where += " AND l.student_id = %s"
        params.append(student["student_ref_id"] if student else 0)
    elif status:
        where += " AND l.status = %s"
        params.append(status)
    rows = fetch_all(
        f"""
        SELECT l.*, s.full_name, s.roll_number, s.class_section, reviewer.full_name AS reviewer_name
        FROM leave_applications l
        JOIN students s ON s.id = l.student_id
        LEFT JOIN users reviewer ON reviewer.id = l.reviewed_by
        WHERE {where}
        ORDER BY l.id DESC
        """,
        tuple(params)
    )
    return jsonify({"success": True, "applications": rows})


@campus_bp.route("/leaves", methods=["POST"])
@login_required
def create_leave():
    if session.get("user_role") != "student":
        return jsonify({"success": False, "message": "Students submit their own leave applications."}), 403
    account = fetch_one("SELECT student_ref_id FROM users WHERE id = %s", (session["user_id"],))
    if not account or not account.get("student_ref_id"):
        return jsonify({"success": False, "message": "This login is not linked to a student profile."}), 400
    attachment_path = None
    upload = request.files.get("attachment")
    if upload and upload.filename:
        safe = secure_filename(upload.filename)
        folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads", "leaves")
        os.makedirs(folder, exist_ok=True)
        stored = f"{session['user_id']}_{safe}"
        upload.save(os.path.join(folder, stored))
        attachment_path = f"/static/uploads/leaves/{stored}"
    if request.content_type and request.content_type.startswith("application/json"):
        data = request.get_json() or {}
    else:
        data = request.form
    result = campus_service.submit_leave(
        account["student_ref_id"],
        data.get("start_date"),
        data.get("end_date"),
        data.get("reason") or "",
        attachment_path
    )
    return jsonify(result), 200 if result.get("success") else 400


@campus_bp.route("/leaves/<int:leave_id>/decision", methods=["POST"])
@teacher_required
def leave_decision(leave_id):
    data = request.get_json() or {}
    result = campus_service.decide_leave(
        leave_id, session["user_id"], (data.get("status") or "").lower(), data.get("comment") or ""
    )
    return jsonify(result), 200 if result.get("success") else 400


@campus_bp.route("/leaves/<int:leave_id>/context", methods=["GET"])
@teacher_required
def leave_context(leave_id):
    leave = fetch_one("SELECT student_id FROM leave_applications WHERE id = %s", (leave_id,))
    if not leave:
        return jsonify({"success": False, "message": "Application not found."}), 404
    return jsonify({"success": True, **campus_service.student_context(leave["student_id"])})


@campus_bp.route("/me/attendance", methods=["GET"])
@login_required
def my_attendance():
    account = fetch_one("SELECT student_ref_id FROM users WHERE id = %s", (session["user_id"],))
    if not account or not account.get("student_ref_id"):
        return jsonify({"success": False, "message": "This account is not a student profile."}), 400
    return jsonify({"success": True, **campus_service.attendance_policy(account["student_ref_id"])})


@campus_bp.route("/notifications", methods=["GET"])
@login_required
def notifications():
    rows = fetch_all(
        """
        SELECT * FROM notifications
        WHERE user_id = %s
        ORDER BY id DESC LIMIT 30
        """,
        (session["user_id"],)
    )
    unread = fetch_one(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = %s AND is_read = 0",
        (session["user_id"],)
    )
    return jsonify({"success": True, "notifications": rows, "unread": unread["cnt"] if unread else 0})


@campus_bp.route("/notifications/read", methods=["POST"])
@login_required
def read_notifications():
    from database.db_manager import execute_query
    execute_query("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (session["user_id"],))
    return jsonify({"success": True})


@campus_bp.route("/reports/students", methods=["GET"])
@teacher_required
def student_percentages():
    class_section = request.args.get("class_section")
    query = "SELECT id, full_name, roll_number, class_section FROM students"
    params = []
    if class_section:
        query += " WHERE class_section = %s"
        params.append(class_section)
    query += " ORDER BY full_name"
    students = fetch_all(query, tuple(params))
    rows = []
    for student in students:
        policy = campus_service.attendance_policy(student["id"])
        rows.append({**student, **policy})
    return jsonify({
        "success": True,
        "threshold": campus_service.setting_float("low_attendance_threshold", 75),
        "students": rows,
        "policy": "Approved leave is excluded. Present and late count as attended. Unmarked rows are not treated as absent."
    })


@campus_bp.route("/dashboard/teacher", methods=["GET"])
@teacher_required
def teacher_dashboard():
    home = campus_service.teacher_home()
    unread = fetch_one(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = %s AND is_read = 0",
        (session["user_id"],)
    )
    home["unread_notifications"] = unread["cnt"] if unread else 0
    return jsonify({"success": True, **home})
