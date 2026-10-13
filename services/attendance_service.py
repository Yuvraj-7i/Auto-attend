import datetime
import io
import csv
import logging
from database.db_manager import fetch_one, fetch_all, execute_query
from services.face_recognition_service import face_service

logger = logging.getLogger("AutoAttend-AttendanceService")


def _combine_date_time(date_val, time_val):
    if not date_val or not time_val:
        return None
    date_text = str(date_val)[:10]
    time_text = str(time_val)[:8]
    if len(time_text) == 5:
        time_text += ":00"
    try:
        return datetime.datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _grace_minutes(class_section, subject_id):
    slot = fetch_one(
        """
        SELECT grace_minutes FROM lecture_slots
        WHERE class_section = %s AND subject_id = %s AND is_active = 1
        ORDER BY id LIMIT 1
        """,
        (class_section, subject_id)
    )
    if slot and slot.get("grace_minutes") is not None:
        return int(slot["grace_minutes"])
    setting = fetch_one(
        "SELECT value_text FROM system_settings WHERE key_name = %s",
        ("attendance_grace_period_mins",)
    )
    try:
        return int(setting["value_text"]) if setting else 15
    except (TypeError, ValueError):
        return 15


def _upsert_late_row(**fields):
    existing = fetch_one(
        """
        SELECT id FROM late_arrivals
        WHERE student_id = %s AND subject_id = %s AND attendance_date = %s AND source = %s
        """,
        (fields["student_id"], fields["subject_id"], fields["attendance_date"], fields["source"])
    )
    if existing:
        execute_query(
            """
            UPDATE late_arrivals
            SET class_section = %s, session_id = %s, lecture_start = %s, arrival_time = %s,
                grace_minutes = %s, minutes_late = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                fields["class_section"], fields["session_id"], fields["lecture_start"],
                fields["arrival_time"], fields["grace_minutes"], fields["minutes_late"],
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing["id"]
            )
        )
        return existing["id"]
    result = execute_query(
        """
        INSERT INTO late_arrivals
        (student_id, class_section, subject_id, session_id, attendance_date, lecture_start,
         arrival_time, grace_minutes, minutes_late, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fields["student_id"], fields["class_section"], fields["subject_id"], fields["session_id"],
            fields["attendance_date"], fields["lecture_start"], fields["arrival_time"],
            fields["grace_minutes"], fields["minutes_late"], fields["source"]
        )
    )
    return result["last_id"]


class AttendanceService:
    """
    Manages session workflows, attendance records, audit logs,
    and statistical reporting.
    """

    def create_session(self, classroom_id: int, subject_id: int, teacher_id: int, is_demo_mode: bool = False):
        """Initializes a new attendance lecture session."""
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        session_code = f"SES-{now.strftime('%Y%m%d%H%M%S')}-{subject_id}"

        res = execute_query(
            """
            INSERT INTO attendance_sessions
            (session_code, classroom_id, subject_id, teacher_id, session_date, start_time, status, is_demo_mode)
            VALUES (%s, %s, %s, %s, %s, %s, 'active', %s)
            """,
            (session_code, classroom_id, subject_id, teacher_id, date_str, time_str, 1 if is_demo_mode else 0)
        )

        session_id = res["last_id"]
        logger.info("Created attendance session #%s (Code: %s)", session_id, session_code)

        # Log audit entry
        self.log_audit(teacher_id, "START_SESSION", "attendance_sessions", session_id,
                       f"Started lecture session code {session_code}")

        return {
            "session_id": session_id,
            "session_code": session_code,
            "start_time": time_str,
            "date": date_str
        }

    def end_session(self, session_id: int, user_id: int = None):
        """
        Concludes an active attendance session, marks remaining unregistered students as absent,
        and generates the session wrap-up statistics.
        """
        now = datetime.datetime.now().strftime("%H:%M:%S")
        execute_query(
            "UPDATE attendance_sessions SET status = 'completed', end_time = %s WHERE id = %s",
            (now, session_id)
        )

        # Clear active observations cache in AI service
        face_service.clear_session_cache(session_id)

        # Automatically mark remaining students as absent if not marked present
        all_students = fetch_all("SELECT id FROM students WHERE consent_given = 1")
        marked_students = fetch_all("SELECT student_id FROM attendance_records WHERE session_id = %s", (session_id,))
        marked_ids = {r["student_id"] for r in marked_students}

        absent_count = 0
        for stu in all_students:
            if stu["id"] not in marked_ids:
                execute_query(
                    """
                    INSERT INTO attendance_records
                    (session_id, student_id, status, verification_method, confidence_score, repeated_observations)
                    VALUES (%s, %s, 'absent', 'system_end_of_session', 0.0, 0)
                    """,
                    (session_id, stu["id"])
                )
                absent_count += 1

        self.log_audit(user_id, "END_SESSION", "attendance_sessions", session_id,
                       f"Closed session #{session_id}. Automatically recorded {absent_count} absent students.")

        return self.get_session_summary(session_id)

    def get_session_summary(self, session_id: int):
        """Returns details and breakdown of an attendance session."""
        session = fetch_one(
            """
            SELECT s.*, c.room_number, sub.subject_name, sub.subject_code, u.full_name as teacher_name
            FROM attendance_sessions s
            JOIN classrooms c ON s.classroom_id = c.id
            JOIN subjects sub ON s.subject_id = sub.id
            JOIN users u ON s.teacher_id = u.id
            WHERE s.id = %s
            """,
            (session_id,)
        )
        if not session:
            return None

        records = fetch_all(
            """
            SELECT ar.*, st.full_name, st.roll_number, st.class_section, st.avatar_url
            FROM attendance_records ar
            JOIN students st ON ar.student_id = st.id
            WHERE ar.session_id = %s
            ORDER BY ar.status ASC, st.roll_number ASC
            """,
            (session_id,)
        )

        present_count = sum(1 for r in records if r["status"] == "present")
        absent_count = sum(1 for r in records if r["status"] == "absent")
        late_count = sum(1 for r in records if r["status"] == "late")
        total = len(records)

        return {
            "session": session,
            "records": records,
            "metrics": {
                "total": total,
                "present": present_count,
                "absent": absent_count,
                "late": late_count,
                "percentage": round((present_count / total * 100) if total > 0 else 0, 1)
            }
        }

    def update_attendance_status(self, record_id: int, new_status: str, audit_note: str, user_id: int):
        """
        Allows authorized teacher to correct attendance status with mandatory audit logging.
        Prevents unauthorized alterations without a trace.
        """
        valid_statuses = ("present", "absent", "late", "flagged", "needs_review", "approved_leave")
        if new_status not in valid_statuses:
            return {"success": False, "message": "Invalid status value"}

        rec = fetch_one("SELECT * FROM attendance_records WHERE id = %s", (record_id,))
        if not rec:
            return {"success": False, "message": "Attendance record not found"}

        old_status = rec["status"]
        execute_query(
            """
            UPDATE attendance_records
            SET status = %s, is_manually_edited = 1, audit_note = %s, edited_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (new_status, audit_note, user_id, record_id)
        )

        self.log_audit(
            user_id,
            "OVERRIDE_ATTENDANCE",
            "attendance_records",
            record_id,
            f"Changed student #{rec['student_id']} status from '{old_status}' to '{new_status}'. Reason: {audit_note}"
        )

        return {"success": True, "message": f"Status updated to '{new_status}' successfully."}

    def record_live_arrival(self, session_id: int, student_id: int):
        """
        Uses the live-camera observation clock to decide lateness.
        A group photo never calls this, because a still image has no arrival time.
        """
        session = fetch_one("SELECT * FROM attendance_sessions WHERE id = %s", (session_id,))
        student = fetch_one("SELECT class_section FROM students WHERE id = %s", (student_id,))
        if not session or not student:
            return None

        arrival = datetime.datetime.now().replace(microsecond=0)
        start = _combine_date_time(session.get("session_date"), session.get("start_time"))
        if start is None:
            return None

        grace = _grace_minutes(student["class_section"], session["subject_id"])
        elapsed = int((arrival - start).total_seconds() // 60)
        if elapsed <= grace:
            execute_query(
                "UPDATE attendance_records SET arrival_status = %s WHERE session_id = %s AND student_id = %s",
                ("on_time", session_id, student_id)
            )
            return {"late": False, "minutes_late": 0}

        minutes_late = elapsed - grace
        execute_query(
            """
            UPDATE attendance_records
            SET status = 'late', arrival_status = %s
            WHERE session_id = %s AND student_id = %s
            """,
            (f"late_{minutes_late}m", session_id, student_id)
        )
        _upsert_late_row(
            student_id=student_id,
            class_section=student["class_section"],
            subject_id=session["subject_id"],
            session_id=session_id,
            attendance_date=str(session["session_date"])[:10],
            lecture_start=str(session["start_time"])[:8],
            arrival_time=arrival.strftime("%Y-%m-%d %H:%M:%S"),
            grace_minutes=grace,
            minutes_late=minutes_late,
            source="live_camera"
        )
        return {"late": True, "minutes_late": minutes_late}

    def get_attendance_records(self, filters: dict = None, page: int = 1, per_page: int = 15):
        """Fetches filtered, paginated attendance records with teacher audit details."""
        filters = filters or {}
        conditions = ["1=1"]
        params = []

        if filters.get("student_id"):
            conditions.append("ar.student_id = %s")
            params.append(filters["student_id"])

        if filters.get("classroom_id"):
            conditions.append("s.classroom_id = %s")
            params.append(filters["classroom_id"])

        if filters.get("subject_id"):
            conditions.append("s.subject_id = %s")
            params.append(filters["subject_id"])

        if filters.get("status"):
            conditions.append("ar.status = %s")
            params.append(filters["status"])

        if filters.get("start_date"):
            conditions.append("s.session_date >= %s")
            params.append(filters["start_date"])

        if filters.get("end_date"):
            conditions.append("s.session_date <= %s")
            params.append(filters["end_date"])

        if filters.get("search"):
            conditions.append("(st.full_name LIKE %s OR st.roll_number LIKE %s)")
            kw = f"%{filters['search']}%"
            params.extend([kw, kw])

        where_clause = " AND ".join(conditions)

        # Count total matches
        count_sql = f"""
            SELECT COUNT(*) as total
            FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            JOIN students st ON ar.student_id = st.id
            WHERE {where_clause}
        """
        total_res = fetch_one(count_sql, tuple(params))
        total_count = total_res["total"] if total_res else 0

        # Fetch records
        offset = (page - 1) * per_page
        query_sql = f"""
            SELECT ar.*, st.full_name, st.roll_number, st.class_section, st.avatar_url,
                   sub.subject_code, sub.subject_name,
                   c.room_number, s.session_date, s.session_code,
                   editor.full_name as edited_by_name
            FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            JOIN students st ON ar.student_id = st.id
            JOIN subjects sub ON s.subject_id = sub.id
            JOIN classrooms c ON s.classroom_id = c.id
            LEFT JOIN users editor ON ar.edited_by = editor.id
            WHERE {where_clause}
            ORDER BY ar.timestamp DESC
            LIMIT %s OFFSET %s
        """
        p_list = list(params) + [per_page, offset]
        rows = fetch_all(query_sql, tuple(p_list))

        return {
            "records": rows,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total_count + per_page - 1) // per_page)
        }

    def generate_csv_report(self, filters: dict = None):
        """Generates a downloadable CSV string of attendance records."""
        data = self.get_attendance_records(filters, page=1, per_page=10000)
        output = io.StringIO()
        writer = csv.writer(output)

        # Write CSV Header
        writer.writerow([
            "Record ID", "Session Code", "Date", "Time", "Student Name", "Roll Number",
            "Class / Section", "Subject", "Classroom", "Status",
            "Verification Method", "Confidence Score", "Observations", "Manually Edited", "Audit Note"
        ])

        for r in data["records"]:
            writer.writerow([
                r["id"],
                r.get("session_code", ""),
                r.get("session_date", ""),
                str(r.get("timestamp", ""))[:19],
                r.get("full_name", ""),
                r.get("roll_number", ""),
                r.get("class_section", ""),
                f"{r.get('subject_code', '')} - {r.get('subject_name', '')}",
                r.get("room_number", ""),
                r.get("status", "").upper(),
                r.get("verification_method", ""),
                f"{int(r.get('confidence_score', 0) * 100)}%",
                r.get("repeated_observations", 0),
                "YES" if r.get("is_manually_edited") else "NO",
                r.get("audit_note", "") or ""
            ])

        return output.getvalue()

    def get_analytics_summary(self):
        """Calculates comprehensive KPI numbers and trends for reports & dashboard."""
        total_students_res = fetch_one("SELECT COUNT(*) as cnt FROM students WHERE consent_given = 1")
        total_students = total_students_res["cnt"] if total_students_res else 0

        # Today's attendance
        today_str = datetime.date.today().isoformat()
        today_stats = fetch_one(
            """
            SELECT
                SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_today,
                SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_today,
                SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_today,
                COUNT(ar.id) as total_today
            FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            WHERE s.session_date = %s
            """,
            (today_str,)
        )

        present_today = (today_stats["present_today"] or 0) if today_stats else 0
        absent_today = (today_stats["absent_today"] or 0) if today_stats else 0
        total_today = (today_stats["total_today"] or 0) if today_stats else 0
        pct_today = round((present_today / total_today * 100) if total_today > 0 else 0, 1)

        # Weekly trend for chart.js (last 7 days)
        weekly_trends = []
        for i in range(6, -1, -1):
            day_d = datetime.date.today() - datetime.timedelta(days=i)
            day_str = day_d.isoformat()
            stat = fetch_one(
                """
                SELECT
                    SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as p_cnt,
                    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as a_cnt
                FROM attendance_records ar
                JOIN attendance_sessions s ON ar.session_id = s.id
                WHERE s.session_date = %s
                """,
                (day_str,)
            )
            weekly_trends.append({
                "day": day_d.strftime("%a (%d %b)"),
                "date": day_str,
                "present": (stat["p_cnt"] or 0) if stat else 0,
                "absent": (stat["a_cnt"] or 0) if stat else 0
            })

        # Subject-wise attendance
        subject_stats = fetch_all(
            """
            SELECT sub.subject_code, sub.subject_name,
                   SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_count,
                   COUNT(ar.id) as total_records
            FROM subjects sub
            LEFT JOIN attendance_sessions s ON sub.id = s.subject_id
            LEFT JOIN attendance_records ar ON s.id = ar.session_id
            GROUP BY sub.id, sub.subject_code, sub.subject_name;
            """
        )

        # Low attendance students (< 75%)
        student_performance = fetch_all(
            """
            SELECT st.id, st.full_name, st.roll_number, st.class_section, st.avatar_url,
                   SUM(CASE WHEN ar.status IN ('present', 'late') THEN 1 ELSE 0 END) as present_count,
                   SUM(CASE WHEN ar.status IN ('present', 'late', 'absent') THEN 1 ELSE 0 END) as total_classes,
                   ROUND(CAST(SUM(CASE WHEN ar.status IN ('present', 'late') THEN 1 ELSE 0 END) AS FLOAT) /
                         NULLIF(SUM(CASE WHEN ar.status IN ('present', 'late', 'absent') THEN 1 ELSE 0 END), 0) * 100, 1) as percentage
            FROM students st
            LEFT JOIN attendance_records ar ON st.id = ar.student_id
            GROUP BY st.id, st.full_name, st.roll_number, st.class_section, st.avatar_url
            HAVING total_classes > 0 AND percentage < 75.0
            ORDER BY percentage ASC;
            """
        )

        return {
            "total_students": total_students,
            "present_today": present_today,
            "absent_today": absent_today,
            "percentage_today": pct_today,
            "weekly_trends": weekly_trends,
            "subject_stats": subject_stats,
            "low_attendance_students": student_performance
        }

    def log_audit(self, user_id, action, entity_type, entity_id, details, ip_address=None):
        """Records an immutable audit trail entry."""
        try:
            execute_query(
                """
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, action, entity_type, entity_id, details, ip_address or "127.0.0.1")
            )
        except Exception as e:
            logger.error("Audit log recording error: %s", str(e))

attendance_service = AttendanceService()
