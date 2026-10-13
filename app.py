import os
from flask import Flask, render_template, redirect, url_for, session
from config import Config
from database.db_manager import init_db
from routes.auth_routes import auth_bp
from routes.student_routes import student_bp
from routes.attendance_routes import attendance_bp
from routes.report_routes import report_bp
from routes.campus_routes import campus_bp

# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload and storage directories exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, "faces"), exist_ok=True)
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, "group_photos"), exist_ok=True)
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, "leaves"), exist_ok=True)
os.makedirs(os.path.join(app.root_path, "static", "images", "avatars"), exist_ok=True)

@app.after_request
def allow_camera(response):
    """Lets the page ask for the webcam as soon as the user clicks Allow camera."""
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    return response

# Register API blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(report_bp)
app.register_blueprint(campus_bp)

# ==========================================
# Frontend Page Routes
# ==========================================
@app.route('/')
def index():
    """Root redirect: to dashboard if logged in, else login page."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    """Login view."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

def _require_login():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return None

def _teacher_page(template):
    gate = _require_login()
    if gate:
        return gate
    if session.get('user_role') == 'student':
        return redirect(url_for('student_portal'))
    return render_template(template)

@app.route('/dashboard')
def dashboard():
    """Main Analytics Dashboard view."""
    return _teacher_page('dashboard.html')

@app.route('/live-attendance')
def live_attendance():
    """Live AI Face Recognition Attendance view."""
    return _teacher_page('live_attendance.html')

@app.route('/students')
def students_page():
    """Student Enrollment & Biometric Management view."""
    return _teacher_page('students.html')

@app.route('/attendance')
def attendance_page():
    """Attendance Records & Teacher Audit view."""
    return _teacher_page('attendance.html')

@app.route('/reports')
def reports_page():
    """Attendance Analytics & CSV Reports view."""
    return _teacher_page('reports.html')

@app.route('/settings')
def settings_page():
    """System & AI Thresholds Configuration view."""
    return _teacher_page('settings.html')

@app.route('/group-photo')
def group_photo_page():
    """Upload a classroom photo and review face matches before saving attendance."""
    return _teacher_page('group_photo.html')

@app.route('/late-arrivals')
def late_arrivals_page():
    """Late-comer records that have a reliable arrival time."""
    return _teacher_page('late_arrivals.html')

@app.route('/leaves')
def leaves_page():
    """Teacher review of student leave applications."""
    return _teacher_page('leaves.html')

@app.route('/student-portal')
def student_portal():
    """Student leave applications and attendance summary."""
    gate = _require_login()
    if gate:
        return gate
    if session.get('user_role') != 'student':
        return redirect(url_for('leaves_page'))
    return render_template('student_portal.html')

# ==========================================
# Error Handlers
# ==========================================
@app.errorhandler(404)
def not_found(e):
    return render_template('dashboard.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('dashboard.html', error="Internal server error"), 500

if __name__ == '__main__':
    # Initialize database tables and seed data
    init_db()
    port = Config.PORT
    print("==================================================")
    print("  AutoAttend is ready.")
    print(f"  Open this address in the browser: http://127.0.0.1:{port}")
    print("  Teacher login: teacher@autoattend.ai  (Sandeep)")
    print("  Password: password123")
    print("  Use 127.0.0.1 so the browser can turn the camera on.")
    print("==================================================")
    # Reloader starts a second process and can lock the webcam.
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG, use_reloader=False)
