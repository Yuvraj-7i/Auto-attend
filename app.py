import os
from flask import Flask, render_template, redirect, url_for, session
from config import Config
from database.db_manager import init_db
from routes.auth_routes import auth_bp
from routes.student_routes import student_bp
from routes.attendance_routes import attendance_bp
from routes.report_routes import report_bp

# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload and storage directories exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, "faces"), exist_ok=True)
os.makedirs(os.path.join(app.root_path, "static", "images", "avatars"), exist_ok=True)

# Register API blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(report_bp)

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

@app.route('/dashboard')
def dashboard():
    """Main Analytics Dashboard view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

@app.route('/live-attendance')
def live_attendance():
    """Live AI Face Recognition Attendance view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('live_attendance.html')

@app.route('/students')
def students_page():
    """Student Enrollment & Biometric Management view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('students.html')

@app.route('/attendance')
def attendance_page():
    """Attendance Records & Teacher Audit view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('attendance.html')

@app.route('/reports')
def reports_page():
    """Attendance Analytics & CSV Reports view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('reports.html')

@app.route('/settings')
def settings_page():
    """System & AI Thresholds Configuration view."""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('settings.html')

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
    print(f"==================================================")
    print(f"  AutoAttend AI Attendance System running on:")
    print(f"  http://127.0.0.1:{port}")
    print(f"  Demo Credentials: teacher@autoattend.ai / password123")
    print(f"==================================================")
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
