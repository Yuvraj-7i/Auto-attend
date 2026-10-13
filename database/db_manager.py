import os
import sqlite3
import re
import logging
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AutoAttend-DB")

# Check if mysql.connector is available
try:
    import mysql.connector
    from mysql.connector import errorcode
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    logger.warning("mysql-connector-python not found. SQLite will be used as default.")

class DatabaseManager:
    """
    Robust Database Manager for AutoAttend.
    Prioritizes MySQL as required by project specifications.
    Gracefully falls back to local SQLite if MySQL server is not currently running,
    ensuring zero crash-on-start in local VS Code environments.
    """
    _instance = None
    _active_mode = None # 'mysql' or 'sqlite'

    def __init__(self):
        self.config = Config
        self.determine_active_driver()

    def determine_active_driver(self):
        """Test MySQL connection; if unavailable, seamlessly fall back to SQLite."""
        if not MYSQL_AVAILABLE or self.config.DB_TYPE != "mysql":
            self._active_mode = "sqlite"
            logger.info("Using SQLite database engine: %s", self.config.SQLITE_PATH)
            return

        try:
            # Test direct connection to MySQL server
            conn = mysql.connector.connect(
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                connection_timeout=2
            )
            conn.close()
            self._active_mode = "mysql"
            logger.info("Connected to MySQL server on %s:%s successfully.", self.config.DB_HOST, self.config.DB_PORT)
        except Exception as e:
            logger.warning(
                "Could not connect to MySQL server (%s). "
                "AutoAttend is activating standalone SQLite database (%s) for zero-friction local run.",
                str(e), self.config.SQLITE_PATH
            )
            self._active_mode = "sqlite"

    @property
    def is_mysql(self):
        return self._active_mode == "mysql"

    def get_connection(self):
        """Returns a connection based on the active driver."""
        if self._active_mode == "mysql":
            try:
                return mysql.connector.connect(
                    host=self.config.DB_HOST,
                    port=self.config.DB_PORT,
                    user=self.config.DB_USER,
                    password=self.config.DB_PASSWORD,
                    database=self.config.DB_NAME,
                    autocommit=False
                )
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_BAD_DB_ERROR:
                    # Database does not exist yet; connect to server to create it
                    server_conn = mysql.connector.connect(
                        host=self.config.DB_HOST,
                        port=self.config.DB_PORT,
                        user=self.config.DB_USER,
                        password=self.config.DB_PASSWORD
                    )
                    cursor = server_conn.cursor()
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                    server_conn.commit()
                    cursor.close()
                    server_conn.close()
                    return self.get_connection()
                raise err
        else:
            # SQLite connection
            os.makedirs(os.path.dirname(self.config.SQLITE_PATH), exist_ok=True)
            conn = sqlite3.connect(self.config.SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            # Enable foreign keys in SQLite
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn

    def format_query(self, query: str) -> str:
        """Adapts parameter placeholders and syntax between MySQL (%s) and SQLite (?)."""
        if self._active_mode == "sqlite":
            # Replace %s placeholders with ? for SQLite
            # Care not to replace in string literals if any
            query = query.replace("%s", "?")
            # Replace MySQL specific syntax if present
            query = re.sub(r'AUTO_INCREMENT', 'AUTOINCREMENT', query, flags=re.IGNORECASE)
            query = re.sub(r'INT\s+AUTOINCREMENT', 'INTEGER AUTOINCREMENT', query, flags=re.IGNORECASE)
            query = re.sub(r'NOW\(\)', "datetime('now', 'localtime')", query, flags=re.IGNORECASE)
            query = re.sub(r'CURRENT_DATE\(\)', "date('now', 'localtime')", query, flags=re.IGNORECASE)
            query = re.sub(r'ON DUPLICATE KEY UPDATE.*?;', ';', query, flags=re.IGNORECASE)
        return query

    def execute(self, query: str, params: tuple = None, commit: bool = True):
        """Executes an INSERT, UPDATE, or DELETE query with parameterized inputs."""
        conn = self.get_connection()
        formatted_query = self.format_query(query)
        try:
            cursor = conn.cursor()
            cursor.execute(formatted_query, params or ())
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
            if commit:
                conn.commit()
            cursor.close()
            return {"last_id": last_id, "row_count": row_count, "success": True}
        except Exception as e:
            if commit:
                conn.rollback()
            logger.error("DB Execution Error: %s | Query: %s", str(e), query)
            raise e
        finally:
            conn.close()

    def fetch_one(self, query: str, params: tuple = None):
        """Fetches a single row as a dictionary."""
        conn = self.get_connection()
        formatted_query = self.format_query(query)
        try:
            if self._active_mode == "mysql":
                cursor = conn.cursor(dictionary=True)
                cursor.execute(formatted_query, params or ())
                row = cursor.fetchone()
                cursor.close()
                return row
            else:
                cursor = conn.cursor()
                cursor.execute(formatted_query, params or ())
                row = cursor.fetchone()
                cursor.close()
                return dict(row) if row else None
        except Exception as e:
            logger.error("DB fetch_one Error: %s | Query: %s", str(e), query)
            raise e
        finally:
            conn.close()

    def fetch_all(self, query: str, params: tuple = None):
        """Fetches all matching rows as a list of dictionaries."""
        conn = self.get_connection()
        formatted_query = self.format_query(query)
        try:
            if self._active_mode == "mysql":
                cursor = conn.cursor(dictionary=True)
                cursor.execute(formatted_query, params or ())
                rows = cursor.fetchall()
                cursor.close()
                return rows
            else:
                cursor = conn.cursor()
                cursor.execute(formatted_query, params or ())
                rows = cursor.fetchall()
                cursor.close()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("DB fetch_all Error: %s | Query: %s", str(e), query)
            raise e
        finally:
            conn.close()

    def init_database(self):
        """Initializes tables and seeds initial data if tables are empty."""
        logger.info("Initializing AutoAttend Database (%s mode)...", self._active_mode)
        conn = self.get_connection()
        cursor = conn.cursor()

        if self._active_mode == "mysql":
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            seed_path = os.path.join(os.path.dirname(__file__), "seed_data.sql")
            self._run_sql_script(cursor, schema_path)
            conn.commit()
            # Check if students table is empty, then seed
            cursor.execute("SELECT COUNT(*) AS cnt FROM students;")
            count = cursor.fetchone()
            if count and (count[0] if isinstance(count, tuple) else count['cnt']) == 0:
                self._run_sql_script(cursor, seed_path)
                conn.commit()
        else:
            # SQLite Schema Initialization
            self._create_sqlite_tables(cursor)
            conn.commit()
            self._seed_sqlite_data(cursor)
            conn.commit()

        cursor.close()
        conn.close()
        logger.info("Database initialized successfully!")

    def _create_sqlite_tables(self, cursor):
        """Creates tables in SQLite with compatible schema."""
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'teacher',
            department TEXT DEFAULT 'Computer Science & Engineering',
            avatar_url TEXT DEFAULT '/static/images/avatars/teacher_avatar.png',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS classrooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT NOT NULL UNIQUE,
            building TEXT DEFAULT 'Block A - Engineering Wing',
            capacity INTEGER DEFAULT 60,
            camera_ip TEXT DEFAULT '0',
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT NOT NULL UNIQUE,
            subject_name TEXT NOT NULL,
            department TEXT DEFAULT 'Computer Science & Engineering',
            semester INTEGER DEFAULT 6,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            roll_number TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            department TEXT DEFAULT 'Computer Science & Engineering',
            class_section TEXT DEFAULT 'CSE-A',
            face_registered INTEGER DEFAULT 0,
            avatar_url TEXT DEFAULT '/static/images/avatars/default_avatar.png',
            consent_given INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS face_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL UNIQUE,
            embedding_data TEXT NOT NULL,
            model_name TEXT DEFAULT 'OpenCV-DNN-FaceEmbedder',
            samples_count INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT NOT NULL UNIQUE,
            classroom_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            session_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NULL,
            status TEXT DEFAULT 'active',
            total_detected INTEGER DEFAULT 0,
            total_present INTEGER DEFAULT 0,
            capture_interval_sec REAL DEFAULT 1.5,
            min_confidence REAL DEFAULT 0.65,
            min_observations INTEGER DEFAULT 3,
            is_demo_mode INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (classroom_id) REFERENCES classrooms(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'present',
            verification_method TEXT DEFAULT 'ai_face_recognition',
            confidence_score REAL DEFAULT 0.0,
            repeated_observations INTEGER DEFAULT 1,
            is_manually_edited INTEGER DEFAULT 0,
            audit_note TEXT NULL,
            edited_by INTEGER NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (edited_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NULL,
            details TEXT NULL,
            ip_address TEXT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            key_name TEXT PRIMARY KEY,
            value_text TEXT NOT NULL,
            description TEXT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

    def _seed_sqlite_data(self, cursor):
        """Seeds initial data into SQLite if not present."""
        cursor.execute("SELECT COUNT(*) FROM students;")
        row = cursor.fetchone()
        if row and row[0] > 0:
            return # Already seeded

        # Password hash for 'password123'
        pw_hash = 'scrypt:32768:8:1$EV8IWDpWLBKqpZJq$54e4637a301258343f758663bfe30b3d710de764524b4b52b780dd24e18a112ae33f4b016329a1cad5817428e659840f583f4b744b0688e5accff1b4456eb3db'

        # Seed Users
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, full_name, email, password_hash, role, department, avatar_url) VALUES
            (1, 'Dr. Ajay Jaiswal', 'ajay.jaiswal@piemr.edu.in', ?, 'admin', 'Computer Science & Engineering', '/static/images/avatars/teacher_ajay.png'),
            (2, 'Prof. Neha Sharma', 'teacher@autoattend.ai', ?, 'teacher', 'Computer Science & Engineering', '/static/images/avatars/teacher_neha.png');
        """, (pw_hash, pw_hash))

        # Seed Classrooms
        cursor.executescript("""
            INSERT OR IGNORE INTO classrooms (id, room_number, building, capacity, camera_ip, is_active) VALUES
            (1, 'Lab 301 - AI & Vision Lab', 'Block A - 3rd Floor', 60, '0', 1),
            (2, 'Room 302 - CSE Seminar Hall', 'Block A - 3rd Floor', 120, '0', 1),
            (3, 'Room 204 - Smart Classroom', 'Block B - 2nd Floor', 75, '0', 1),
            (4, 'Lab 405 - HPC Computing', 'Block A - 4th Floor', 45, '0', 1);

            INSERT OR IGNORE INTO subjects (id, subject_code, subject_name, department, semester) VALUES
            (1, 'CS-601', 'Machine Learning & Deep Learning', 'Computer Science & Engineering', 6),
            (2, 'CS-602', 'Computer Vision & Image Processing', 'Computer Science & Engineering', 6),
            (3, 'CS-603', 'Database Management & Cloud Systems', 'Computer Science & Engineering', 6),
            (4, 'CS-604', 'Software Engineering & Agile Practices', 'Computer Science & Engineering', 6);

            INSERT OR IGNORE INTO students (id, student_id, full_name, roll_number, email, department, class_section, face_registered, avatar_url, consent_given) VALUES
            (1, 'STU-0827-01', 'Yuvraj Soni', '0827CS211180', 'yuvraj.soni@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_1.png', 1),
            (2, 'STU-0827-02', 'Tanishk Jain', '0827CS211165', 'tanishk.jain@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_2.png', 1),
            (3, 'STU-0827-03', 'Umesh Dhakad', '0827CS211172', 'umesh.dhakad@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_3.png', 1),
            (4, 'STU-0827-04', 'Vinayak Sahu', '0827CS211178', 'vinayak.sahu@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_4.png', 1),
            (5, 'STU-0827-05', 'Aarav Sharma', '0827CS211002', 'aarav.sharma@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_5.png', 1),
            (6, 'STU-0827-06', 'Ananya Verma', '0827CS211015', 'ananya.verma@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_6.png', 1),
            (7, 'STU-0827-07', 'Rohan Mehta', '0827CS211088', 'rohan.mehta@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_7.png', 1),
            (8, 'STU-0827-08', 'Priya Patel', '0827CS211074', 'priya.patel@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 0, '/static/images/avatars/avatar_8.png', 1),
            (9, 'STU-0827-09', 'Aditya Singh', '0827CS211009', 'aditya.singh@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-B', 1, '/static/images/avatars/avatar_9.png', 1),
            (10, 'STU-0827-10', 'Sneha Kapoor', '0827CS211150', 'sneha.kapoor@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-B', 1, '/static/images/avatars/avatar_10.png', 1),
            (11, 'STU-0827-11', 'Ishaan Joshi', '0827CS211052', 'ishaan.joshi@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-B', 0, '/static/images/avatars/avatar_11.png', 1),
            (12, 'STU-0827-12', 'Diya Nair', '0827CS211041', 'diya.nair@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-B', 1, '/static/images/avatars/avatar_12.png', 1),
            (13, 'STU-0827-13', 'Kabir Gupta', '0827CS211060', 'kabir.gupta@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_13.png', 1),
            (14, 'STU-0827-14', 'Riya Sen', '0827CS211095', 'riya.sen@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 1, '/static/images/avatars/avatar_14.png', 1),
            (15, 'STU-0827-15', 'Aryan Choudhary', '0827CS211022', 'aryan.c@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 0, '/static/images/avatars/avatar_15.png', 1);

            INSERT OR IGNORE INTO system_settings (key_name, value_text, description) VALUES
            ('face_match_threshold', '0.65', 'Cosine similarity threshold for accepting face identity match'),
            ('min_observations', '3', 'Minimum repeated observations required before marking present'),
            ('frame_capture_interval', '1.5', 'Time interval in seconds between backend AI frames'),
            ('camera_source', '0', 'Default camera index (0 = default webcam) or RTSP stream URL'),
            ('enable_anti_spoofing', 'false', 'Enable liveness and anti-spoofing verification'),
            ('attendance_grace_period_mins', '15', 'Minutes from lecture start after which student is considered late');
        """)

        # Seed sample past attendance sessions and records for realistic analytics
        self._seed_sample_attendance_history(cursor)

    def _seed_sample_attendance_history(self, cursor):
        """Adds historical attendance sessions and records for rich dashboard analytics."""
        import datetime
        today = datetime.date.today()

        sessions_data = [
            (today - datetime.timedelta(days=4), "09:00:00", "10:00:00", 1, 1, 14, 13),
            (today - datetime.timedelta(days=3), "10:15:00", "11:15:00", 2, 2, 13, 12),
            (today - datetime.timedelta(days=2), "11:30:00", "12:30:00", 1, 1, 15, 14),
            (today - datetime.timedelta(days=1), "14:00:00", "15:00:00", 3, 3, 14, 13),
            (today, "09:00:00", "10:00:00", 1, 1, 14, 13),
        ]

        for idx, (sess_date, s_time, e_time, room_id, subj_id, detected, present) in enumerate(sessions_data, 1):
            sess_code = f"SES-{sess_date.strftime('%Y%m%d')}-{subj_id:02d}"
            cursor.execute("""
                INSERT OR IGNORE INTO attendance_sessions
                (id, session_code, classroom_id, subject_id, teacher_id, session_date, start_time, end_time, status, total_detected, total_present, is_demo_mode)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'completed', ?, ?, 0);
            """, (idx, sess_code, room_id, subj_id, sess_date.isoformat(), s_time, e_time, detected, present))

            # Add records for students (present for first 12, late for 1, absent for rest)
            for stu_id in range(1, 16):
                if stu_id <= 11:
                    status = 'present'
                    conf = 0.88 + (stu_id % 7) * 0.015
                    rep = 4 + (stu_id % 3)
                elif stu_id in (12, 13):
                    status = 'present' if (idx + stu_id) % 2 == 0 else 'late'
                    conf = 0.79
                    rep = 3
                else:
                    status = 'absent'
                    conf = 0.0
                    rep = 0

                cursor.execute("""
                    INSERT OR IGNORE INTO attendance_records
                    (session_id, student_id, timestamp, status, verification_method, confidence_score, repeated_observations, is_manually_edited)
                    VALUES (?, ?, ?, ?, 'ai_face_recognition', ?, ?, 0);
                """, (idx, stu_id, f"{sess_date.isoformat()} {s_time}", status, conf, rep))

    def _run_sql_script(self, cursor, filepath):
        """Executes multi-statement SQL script."""
        with open(filepath, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        statements = sql_script.split(';')
        for stmt in statements:
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    cursor.execute(stmt)
                except Exception as e:
                    logger.warning("SQL statement notice: %s", str(e))

# Singleton instance
db = DatabaseManager()

# Export common functions for beginner-friendly usage across routes
def execute_query(query: str, params: tuple = None, commit: bool = True):
    return db.execute(query, params, commit)

def fetch_one(query: str, params: tuple = None):
    return db.fetch_one(query, params)

def fetch_all(query: str, params: tuple = None):
    return db.fetch_all(query, params)

def init_db():
    db.init_database()
