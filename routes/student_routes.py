import base64
import cv2
import numpy as np
from flask import Blueprint, request, jsonify, session
from database.db_manager import fetch_one, fetch_all, execute_query
from services.face_recognition_service import face_service
from services.attendance_service import attendance_service
from routes.auth_routes import login_required

student_bp = Blueprint('students', __name__, url_prefix='/api/students')

@student_bp.route('', methods=['GET'])
@login_required
def list_students():
    """Returns paginated, searchable, filterable student list."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    search = request.args.get('search', '').strip()
    department = request.args.get('department', '').strip()
    class_section = request.args.get('class_section', '').strip()
    face_status = request.args.get('face_status', '').strip() # 'registered', 'unregistered'

    conditions = ["1=1"]
    params = []

    if search:
        conditions.append("(full_name LIKE %s OR roll_number LIKE %s OR email LIKE %s OR student_id LIKE %s)")
        kw = f"%{search}%"
        params.extend([kw, kw, kw, kw])

    if department:
        conditions.append("department = %s")
        params.append(department)

    if class_section:
        conditions.append("class_section = %s")
        params.append(class_section)

    if face_status == "registered":
        conditions.append("face_registered = 1")
    elif face_status == "unregistered":
        conditions.append("face_registered = 0")

    where_clause = " AND ".join(conditions)

    count_res = fetch_one(f"SELECT COUNT(*) as total FROM students WHERE {where_clause}", tuple(params))
    total = count_res['total'] if count_res else 0

    offset = (page - 1) * per_page
    query_sql = f"""
        SELECT s.*,
               COUNT(ar.id) as total_sessions,
               SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_sessions,
               ROUND(CAST(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS FLOAT) /
                     NULLIF(COUNT(ar.id), 0) * 100, 1) as attendance_percentage
        FROM students s
        LEFT JOIN attendance_records ar ON s.id = ar.student_id
        WHERE {where_clause}
        GROUP BY s.id
        ORDER BY s.roll_number ASC
        LIMIT %s OFFSET %s
    """
    p_list = list(params) + [per_page, offset]
    students = fetch_all(query_sql, tuple(p_list))

    return jsonify({
        "success": True,
        "students": students,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page)
    })

@student_bp.route('/<int:student_id>', methods=['GET'])
@login_required
def get_student(student_id):
    """Fetches full profile and historical attendance for an individual student."""
    student = fetch_one("SELECT * FROM students WHERE id = %s", (student_id,))
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    # Calculate attendance summary
    stats = fetch_one(
        """
        SELECT
            COUNT(ar.id) as total_lectures,
            SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_count,
            SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_count,
            SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_count
        FROM attendance_records ar
        WHERE ar.student_id = %s
        """,
        (student_id,)
    )

    # Recent attendance records
    recent = fetch_all(
        """
        SELECT ar.*, s.session_date, sub.subject_code, sub.subject_name
        FROM attendance_records ar
        JOIN attendance_sessions s ON ar.session_id = s.id
        JOIN subjects sub ON s.subject_id = sub.id
        WHERE ar.student_id = %s
        ORDER BY ar.timestamp DESC
        LIMIT 10
        """,
        (student_id,)
    )

    tot = stats['total_lectures'] or 0
    pres = stats['present_count'] or 0
    pct = round((pres / tot * 100) if tot > 0 else 0, 1)

    return jsonify({
        "success": True,
        "student": student,
        "attendance_stats": {
            "total_lectures": tot,
            "present": pres,
            "absent": stats['absent_count'] or 0,
            "late": stats['late_count'] or 0,
            "percentage": pct
        },
        "recent_records": recent
    })

@student_bp.route('', methods=['POST'])
@login_required
def add_student():
    """Enrolls a new student with server-side validation."""
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    roll_number = data.get('roll_number', '').strip().upper()
    email = data.get('email', '').strip().lower()
    department = data.get('department', 'Computer Science & Engineering').strip()
    class_section = data.get('class_section', 'CSE-A').strip()
    consent = bool(data.get('consent_given', True))

    if not full_name or not roll_number or not email:
        return jsonify({"success": False, "message": "Full name, roll number, and email are required."}), 400

    # Check for duplicate roll number
    exists = fetch_one("SELECT id FROM students WHERE roll_number = %s", (roll_number,))
    if exists:
        return jsonify({"success": False, "message": f"Roll number '{roll_number}' is already registered."}), 409

    # Check for duplicate email
    exists_email = fetch_one("SELECT id FROM students WHERE email = %s", (email,))
    if exists_email:
        return jsonify({"success": False, "message": f"Email '{email}' is already registered."}), 409

    # Generate custom student ID code
    student_id_code = f"STU-{roll_number.replace(' ', '')}"

    res = execute_query(
        """
        INSERT INTO students (student_id, full_name, roll_number, email, department, class_section, consent_given)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (student_id_code, full_name, roll_number, email, department, class_section, 1 if consent else 0)
    )

    new_id = res['last_id']
    attendance_service.log_audit(
        session.get('user_id'), "CREATE_STUDENT", "students", new_id,
        f"Added student {full_name} ({roll_number})"
    )

    return jsonify({
        "success": True,
        "message": f"Student '{full_name}' added successfully.",
        "student_id": new_id
    }), 201

@student_bp.route('/<int:student_id>', methods=['PUT'])
@login_required
def update_student(student_id):
    """Updates student information."""
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    roll_number = data.get('roll_number', '').strip().upper()
    email = data.get('email', '').strip().lower()
    department = data.get('department', '').strip()
    class_section = data.get('class_section', '').strip()

    if not full_name or not roll_number or not email:
        return jsonify({"success": False, "message": "Full name, roll number, and email are required."}), 400

    # Ensure roll number not taken by another student
    dup_roll = fetch_one("SELECT id FROM students WHERE roll_number = %s AND id != %s", (roll_number, student_id))
    if dup_roll:
        return jsonify({"success": False, "message": f"Roll number '{roll_number}' belongs to another student."}), 409

    dup_email = fetch_one("SELECT id FROM students WHERE email = %s AND id != %s", (email, student_id))
    if dup_email:
        return jsonify({"success": False, "message": f"Email '{email}' belongs to another student."}), 409

    execute_query(
        """
        UPDATE students
        SET full_name = %s, roll_number = %s, email = %s, department = %s, class_section = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (full_name, roll_number, email, department, class_section, student_id)
    )

    attendance_service.log_audit(
        session.get('user_id'), "UPDATE_STUDENT", "students", student_id,
        f"Updated details for student {full_name}"
    )

    return jsonify({"success": True, "message": "Student information updated successfully."})

@student_bp.route('/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    """Deletes student and associated face biometrics with audit confirmation."""
    student = fetch_one("SELECT full_name, roll_number FROM students WHERE id = %s", (student_id,))
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    # Delete face template file if exists
    face_service.remove_student_face(student_id)

    # Delete student record
    execute_query("DELETE FROM students WHERE id = %s", (student_id,))

    attendance_service.log_audit(
        session.get('user_id'), "DELETE_STUDENT", "students", student_id,
        f"Deleted student {student['full_name']} ({student['roll_number']})"
    )

    return jsonify({"success": True, "message": f"Student '{student['full_name']}' deleted successfully."})

@student_bp.route('/<int:student_id>/register-face', methods=['POST'])
@login_required
def register_face(student_id):
    """
    Enrolls a student's facial template from a captured camera frame or uploaded picture.
    Ensures student consent and validates face quality.
    """
    student = fetch_one("SELECT * FROM students WHERE id = %s", (student_id,))
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    data = request.get_json() or {}
    image_base64 = data.get('image', '')

    if not image_base64:
        return jsonify({"success": False, "message": "No image data provided for face registration."}), 400

    try:
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        image_bytes = base64.b64decode(image_base64)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Failed to decode camera image."}), 400

        result = face_service.register_student_face(student_id, frame)
        if result["success"]:
            attendance_service.log_audit(
                session.get('user_id'), "REGISTER_FACE", "students", student_id,
                f"Biometric face template registered for {student['full_name']}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        return jsonify({"success": False, "message": f"Face registration error: {str(e)}"}), 500

@student_bp.route('/<int:student_id>/face', methods=['DELETE'])
@login_required
def remove_face(student_id):
    """Removes registered facial template for privacy / re-enrollment."""
    result = face_service.remove_student_face(student_id)
    attendance_service.log_audit(
        session.get('user_id'), "REMOVE_FACE", "students", student_id,
        f"Removed biometric face template for student #{student_id}"
    )
    return jsonify(result)
