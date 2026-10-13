import functools
from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash
from database.db_manager import fetch_one, execute_query
from services.attendance_service import attendance_service

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

def login_required(view):
    """Decorator to protect authenticated routes."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
        return view(**kwargs)
    return wrapped_view

@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticates teacher or admin user."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = bool(data.get('remember', False))

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    user = fetch_one("SELECT * FROM users WHERE email = %s", (email,))
    if not user:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

    if not check_password_hash(user['password_hash'], password):
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

    # Store user in Flask session
    session.clear()
    session['user_id'] = user['id']
    session['user_name'] = user['full_name']
    session['user_email'] = user['email']
    session['user_role'] = user['role']
    session['user_avatar'] = user.get('avatar_url', '/static/images/avatars/teacher_avatar.png')
    session.permanent = remember

    attendance_service.log_audit(
        user['id'], "LOGIN", "users", user['id'],
        f"User {user['full_name']} logged in successfully."
    )

    return jsonify({
        "success": True,
        "message": f"Welcome back, {user['full_name']}!",
        "user": {
            "id": user['id'],
            "name": user['full_name'],
            "email": user['email'],
            "role": user['role'],
            "department": user.get('department', 'CSE'),
            "avatar": session['user_avatar']
        }
    })

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logs out current user and clears session."""
    user_id = session.get('user_id')
    if user_id:
        attendance_service.log_audit(user_id, "LOGOUT", "users", user_id, "User logged out.")
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."})

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """Returns currently authenticated user profile."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"authenticated": False}), 200

    user = fetch_one("SELECT id, full_name, email, role, department, avatar_url FROM users WHERE id = %s", (user_id,))
    if not user:
        session.clear()
        return jsonify({"authenticated": False}), 200

    return jsonify({
        "authenticated": True,
        "user": {
            "id": user['id'],
            "name": user['full_name'],
            "email": user['email'],
            "role": user['role'],
            "department": user['department'],
            "avatar": user['avatar_url']
        }
    })

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Allows authenticated user to change password securely."""
    data = request.get_json() or {}
    curr_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')

    if not curr_pw or not new_pw:
        return jsonify({"success": False, "message": "Both current and new passwords are required."}), 400

    if len(new_pw) < 6:
        return jsonify({"success": False, "message": "New password must be at least 6 characters long."}), 400

    user_id = session['user_id']
    user = fetch_one("SELECT password_hash FROM users WHERE id = %s", (user_id,))
    if not user or not check_password_hash(user['password_hash'], curr_pw):
        return jsonify({"success": False, "message": "Incorrect current password."}), 400

    new_hash = generate_password_hash(new_pw)
    execute_query("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_id))

    attendance_service.log_audit(user_id, "PASSWORD_CHANGE", "users", user_id, "Password changed successfully.")
    return jsonify({"success": True, "message": "Password changed successfully."})
