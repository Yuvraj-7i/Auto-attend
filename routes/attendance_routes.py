from flask import Blueprint, request, jsonify, Response, session
from database.db_manager import fetch_all, fetch_one
from services.attendance_service import attendance_service
from services.camera_service import camera_service
from routes.auth_routes import login_required

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api')

# ==========================================
# Classrooms & Subjects Endpoints
# ==========================================
@attendance_bp.route('/classrooms', methods=['GET'])
@login_required
def get_classrooms():
    """Returns available classrooms list."""
    rooms = fetch_all("SELECT * FROM classrooms WHERE is_active = 1 ORDER BY room_number ASC")
    return jsonify({"success": True, "classrooms": rooms})

@attendance_bp.route('/subjects', methods=['GET'])
@login_required
def get_subjects():
    """Returns subjects curriculum list."""
    subjects = fetch_all("SELECT * FROM subjects ORDER BY subject_code ASC")
    return jsonify({"success": True, "subjects": subjects})

# ==========================================
# Attendance Sessions Endpoints
# ==========================================
@attendance_bp.route('/attendance/sessions', methods=['POST'])
@login_required
def start_attendance_session():
    """Starts a new lecture attendance session."""
    data = request.get_json() or {}
    classroom_id = data.get('classroom_id')
    subject_id = data.get('subject_id')
    is_demo = bool(data.get('is_demo_mode', False))
    teacher_id = session.get('user_id')

    if not classroom_id or not subject_id:
        return jsonify({"success": False, "message": "Classroom and Subject must be selected."}), 400

    session_info = attendance_service.create_session(
        classroom_id=int(classroom_id),
        subject_id=int(subject_id),
        teacher_id=teacher_id,
        is_demo_mode=is_demo
    )

    # Link active session to camera service
    camera_service.set_active_session(session_info["session_id"])

    return jsonify({"success": True, "session": session_info}), 201

@attendance_bp.route('/attendance/sessions/<int:session_id>', methods=['GET'])
@login_required
def get_session(session_id):
    """Fetches details and marked student records of a session."""
    summary = attendance_service.get_session_summary(session_id)
    if not summary:
        return jsonify({"success": False, "message": "Session not found"}), 404
    return jsonify({"success": True, **summary})

@attendance_bp.route('/attendance/sessions/<int:session_id>/stop', methods=['POST'])
@login_required
def stop_attendance_session(session_id):
    """Stops the active session and seals final attendance counts."""
    summary = attendance_service.end_session(session_id, user_id=session.get('user_id'))
    if camera_service.active_session_id == session_id:
        camera_service.set_active_session(None)
    return jsonify({"success": True, "message": "Session completed.", **summary})

# ==========================================
# Attendance Records & Manual Overrides
# ==========================================
@attendance_bp.route('/attendance/records', methods=['GET'])
@login_required
def list_attendance_records():
    """Returns filtered and paginated attendance records."""
    filters = {
        "student_id": request.args.get('student_id'),
        "classroom_id": request.args.get('classroom_id'),
        "subject_id": request.args.get('subject_id'),
        "status": request.args.get('status'),
        "start_date": request.args.get('start_date'),
        "end_date": request.args.get('end_date'),
        "search": request.args.get('search', '').strip()
    }
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 15))

    result = attendance_service.get_attendance_records(filters, page, per_page)
    return jsonify({"success": True, **result})

@attendance_bp.route('/attendance/records/<int:record_id>', methods=['PATCH'])
@login_required
def override_record_status(record_id):
    """Teacher correction workflow with mandatory audit trail."""
    data = request.get_json() or {}
    new_status = data.get('status', '').strip().lower()
    audit_note = data.get('audit_note', '').strip()

    if not audit_note:
        return jsonify({"success": False, "message": "Please provide an explanation/note for manually overriding attendance."}), 400

    result = attendance_service.update_attendance_status(
        record_id=record_id,
        new_status=new_status,
        audit_note=audit_note,
        user_id=session.get('user_id')
    )
    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code

# ==========================================
# Camera & Video Streaming Endpoints
# ==========================================
@attendance_bp.route('/camera/start', methods=['POST'])
@login_required
def start_camera_stream():
    """Powers on camera capture or demo generator."""
    data = request.get_json() or {}
    cam_index = data.get('camera_index', 0)
    demo_mode = bool(data.get('demo_mode', False))
    success = camera_service.start_camera(cam_index, demo_mode)
    return jsonify({
        "success": success,
        "is_demo_mode": camera_service.is_demo_mode,
        "is_running": camera_service.is_running
    })

@attendance_bp.route('/camera/stop', methods=['POST'])
@login_required
def stop_camera_stream():
    """Turns off video capture."""
    camera_service.stop_camera()
    return jsonify({"success": True, "is_running": False})

@attendance_bp.route('/camera/stream', methods=['GET'])
def video_feed():
    """MJPEG streaming endpoint with real-time HUD annotations."""
    if not camera_service.is_running:
        camera_service.start_camera(demo_mode=True)

    return Response(
        camera_service.get_frame(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@attendance_bp.route('/camera/process-frame', methods=['POST'])
@login_required
def process_client_frame():
    """Accepts base64 camera frame captured directly in HTML5 browser."""
    data = request.get_json() or {}
    image_b64 = data.get('image', '')
    session_id = data.get('session_id')
    if not image_b64:
        return jsonify({"success": False, "message": "No frame data received."}), 400

    res = camera_service.process_client_frame(image_b64, session_id)
    return jsonify(res)

@attendance_bp.route('/camera/events', methods=['GET'])
@login_required
def get_camera_events():
    """Provides recent AI recognition detection events and live counts."""
    return jsonify({
        "success": True,
        "events": camera_service.detection_events,
        "stats": camera_service.stats,
        "is_running": camera_service.is_running,
        "is_demo_mode": camera_service.is_demo_mode,
        "active_session_id": camera_service.active_session_id
    })
