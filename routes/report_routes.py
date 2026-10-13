from flask import Blueprint, request, jsonify, Response
from database.db_manager import fetch_all, fetch_one, execute_query
from services.attendance_service import attendance_service
from routes.auth_routes import login_required

report_bp = Blueprint('reports', __name__, url_prefix='/api')

@report_bp.route('/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """Provides high-level KPI indicators and Chart.js series for main dashboard."""
    stats = attendance_service.get_analytics_summary()

    # Recent activity stream
    recent_activity = fetch_all(
        """
        SELECT ar.id, ar.status, ar.timestamp, ar.confidence_score, ar.verification_method,
               st.full_name, st.roll_number, st.avatar_url,
               sub.subject_code, sub.subject_name
        FROM attendance_records ar
        JOIN attendance_sessions s ON ar.session_id = s.id
        JOIN students st ON ar.student_id = st.id
        JOIN subjects sub ON s.subject_id = sub.id
        ORDER BY ar.timestamp DESC
        LIMIT 8;
        """
    )

    # Next / Current scheduled lecture
    active_session = fetch_one(
        """
        SELECT s.*, c.room_number, sub.subject_name, sub.subject_code
        FROM attendance_sessions s
        JOIN classrooms c ON s.classroom_id = c.id
        JOIN subjects sub ON s.subject_id = sub.id
        WHERE s.status = 'active'
        ORDER BY s.id DESC
        LIMIT 1;
        """
    )

    return jsonify({
        "success": True,
        "kpis": {
            "total_students": stats["total_students"],
            "present_today": stats["present_today"],
            "absent_today": stats["absent_today"],
            "percentage_today": stats["percentage_today"]
        },
        "charts": {
            "weekly": stats["weekly_trends"],
            "doughnut": {
                "present": stats["present_today"],
                "absent": stats["absent_today"]
            },
            "subjects": stats["subject_stats"]
        },
        "recent_activity": recent_activity,
        "active_session": active_session
    })

@report_bp.route('/reports/summary', methods=['GET'])
@login_required
def get_reports_summary():
    """Provides detailed analytics for the reporting center."""
    summary = attendance_service.get_analytics_summary()
    return jsonify({"success": True, **summary})

@report_bp.route('/reports/export', methods=['GET'])
@login_required
def export_attendance_csv():
    """Exports attendance records as a downloadable CSV file."""
    filters = {
        "student_id": request.args.get('student_id'),
        "classroom_id": request.args.get('classroom_id'),
        "subject_id": request.args.get('subject_id'),
        "status": request.args.get('status'),
        "start_date": request.args.get('start_date'),
        "end_date": request.args.get('end_date')
    }
    csv_data = attendance_service.generate_csv_report(filters)
    filename = "AutoAttend_Report.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@report_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    """Returns application configuration parameters."""
    settings_rows = fetch_all("SELECT key_name, value_text, description FROM system_settings")
    settings_dict = {r["key_name"]: r["value_text"] for r in settings_rows}
    return jsonify({"success": True, "settings": settings_dict})

@report_bp.route('/settings', methods=['POST'])
@login_required
def update_settings():
    """Updates system thresholds and camera configuration."""
    data = request.get_json() or {}
    for key, val in data.items():
        execute_query(
            "UPDATE system_settings SET value_text = %s WHERE key_name = %s",
            (str(val), key)
        )
    return jsonify({"success": True, "message": "Settings updated successfully."})
