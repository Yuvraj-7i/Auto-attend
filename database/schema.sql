-- =======================================================
-- AutoAttend: AI-Powered Classroom Attendance System
-- MySQL Database Schema
-- Designed for College Minor Project - Phase I
-- =======================================================

CREATE DATABASE IF NOT EXISTS autoattend_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE autoattend_db;

-- 1. Users / Faculty Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'teacher',
    department VARCHAR(100) DEFAULT 'Computer Science & Engineering',
    avatar_url VARCHAR(255) DEFAULT '/static/images/teacher_avatar.png',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Classrooms Table
CREATE TABLE IF NOT EXISTS classrooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_number VARCHAR(50) NOT NULL UNIQUE,
    building VARCHAR(100) DEFAULT 'Block A - Engineering Wing',
    capacity INT DEFAULT 60,
    camera_ip VARCHAR(100) DEFAULT '0',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Subjects Table
CREATE TABLE IF NOT EXISTS subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject_code VARCHAR(30) NOT NULL UNIQUE,
    subject_name VARCHAR(100) NOT NULL,
    department VARCHAR(100) DEFAULT 'Computer Science & Engineering',
    semester INT DEFAULT 6,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Students Table
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    roll_number VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    department VARCHAR(100) DEFAULT 'Computer Science & Engineering',
    class_section VARCHAR(50) DEFAULT 'CSE-A',
    face_registered BOOLEAN DEFAULT FALSE,
    avatar_url VARCHAR(255) DEFAULT '/static/images/default_avatar.png',
    consent_given BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_roll_number (roll_number),
    INDEX idx_class_section (class_section)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Face Templates / Biometrics Table (Secure Embeddings Storage)
CREATE TABLE IF NOT EXISTS face_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL UNIQUE,
    embedding_data LONGTEXT NOT NULL,
    model_name VARCHAR(100) DEFAULT 'OpenCV-DNN-FaceEmbedder',
    samples_count INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_face_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Attendance Sessions Table
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_code VARCHAR(64) NOT NULL UNIQUE,
    classroom_id INT NOT NULL,
    subject_id INT NOT NULL,
    teacher_id INT NOT NULL,
    session_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NULL,
    status VARCHAR(20) DEFAULT 'active',
    total_detected INT DEFAULT 0,
    total_present INT DEFAULT 0,
    capture_interval_sec FLOAT DEFAULT 1.5,
    min_confidence FLOAT DEFAULT 0.65,
    min_observations INT DEFAULT 3,
    is_demo_mode BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_date (session_date),
    CONSTRAINT fk_session_classroom FOREIGN KEY (classroom_id) REFERENCES classrooms(id),
    CONSTRAINT fk_session_subject FOREIGN KEY (subject_id) REFERENCES subjects(id),
    CONSTRAINT fk_session_teacher FOREIGN KEY (teacher_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. Attendance Records Table
CREATE TABLE IF NOT EXISTS attendance_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    student_id INT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'present',
    verification_method VARCHAR(50) DEFAULT 'ai_face_recognition',
    confidence_score FLOAT DEFAULT 0.0,
    repeated_observations INT DEFAULT 1,
    is_manually_edited BOOLEAN DEFAULT FALSE,
    audit_note TEXT NULL,
    edited_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_student_session (session_id, student_id),
    INDEX idx_record_status (status),
    CONSTRAINT fk_rec_session FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_rec_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_rec_editor FOREIGN KEY (edited_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. Audit Logs Table (Accountability for Manual Teacher Edits)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    details TEXT NULL,
    ip_address VARCHAR(50) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. System Settings Table
CREATE TABLE IF NOT EXISTS system_settings (
    key_name VARCHAR(50) PRIMARY KEY,
    value_text TEXT NOT NULL,
    description VARCHAR(255) NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. Lecture slots (class timetable used by live and group-photo attendance)
CREATE TABLE IF NOT EXISTS lecture_slots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_section VARCHAR(50) NOT NULL,
    subject_id INT NOT NULL,
    classroom_id INT NOT NULL,
    title VARCHAR(120) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    grace_minutes INT DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slot_class (class_section),
    CONSTRAINT fk_slot_subject FOREIGN KEY (subject_id) REFERENCES subjects(id),
    CONSTRAINT fk_slot_classroom FOREIGN KEY (classroom_id) REFERENCES classrooms(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. Group photo batches (review before attendance is saved)
CREATE TABLE IF NOT EXISTS group_photo_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_id INT NOT NULL,
    class_section VARCHAR(50) NOT NULL,
    subject_id INT NOT NULL,
    lecture_slot_id INT NULL,
    session_id INT NULL,
    attendance_date DATE NOT NULL,
    observation_time TIME NULL,
    photo_path VARCHAR(255) NOT NULL,
    annotated_path VARCHAR(255) NULL,
    upload_timestamp DATETIME NOT NULL,
    processing_timestamp DATETIME NULL,
    status VARCHAR(20) DEFAULT 'draft',
    faces_detected INT DEFAULT 0,
    matched_count INT DEFAULT 0,
    unmatched_count INT DEFAULT 0,
    review_count INT DEFAULT 0,
    existing_warning TEXT NULL,
    confirmed_by INT NULL,
    confirmation_timestamp DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_batch_lookup (class_section, subject_id, attendance_date),
    CONSTRAINT fk_batch_teacher FOREIGN KEY (teacher_id) REFERENCES users(id),
    CONSTRAINT fk_batch_subject FOREIGN KEY (subject_id) REFERENCES subjects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 12. Faces found in a group photo, plus enrolled students not seen in the photo
CREATE TABLE IF NOT EXISTS group_photo_faces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT NOT NULL,
    student_id INT NULL,
    bbox VARCHAR(80) NULL,
    confidence FLOAT DEFAULT 0,
    match_result VARCHAR(30) NOT NULL,
    attendance_status VARCHAR(30) NOT NULL,
    arrival_status VARCHAR(60) DEFAULT 'unknown',
    verification_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_face_batch (batch_id),
    CONSTRAINT fk_face_batch FOREIGN KEY (batch_id) REFERENCES group_photo_batches(id) ON DELETE CASCADE,
    CONSTRAINT fk_face_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 13. Leave applications (kept separate from physical attendance)
CREATE TABLE IF NOT EXISTS leave_applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT NOT NULL,
    attachment_path VARCHAR(255) NULL,
    status VARCHAR(20) DEFAULT 'pending',
    teacher_comment TEXT NULL,
    reviewed_by INT NULL,
    reviewed_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_leave_student (student_id),
    INDEX idx_leave_status (status),
    CONSTRAINT fk_leave_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_leave_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 14. Late arrivals that have a reliable timestamp
CREATE TABLE IF NOT EXISTS late_arrivals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    class_section VARCHAR(50) NOT NULL,
    subject_id INT NOT NULL,
    session_id INT NULL,
    attendance_date DATE NOT NULL,
    lecture_start TIME NOT NULL,
    arrival_time DATETIME NOT NULL,
    grace_minutes INT DEFAULT 10,
    minutes_late INT NOT NULL,
    source VARCHAR(30) NOT NULL,
    correction_note TEXT NULL,
    corrected_by INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_late_mark (student_id, subject_id, attendance_date, source),
    INDEX idx_late_date (attendance_date),
    CONSTRAINT fk_late_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_late_subject FOREIGN KEY (subject_id) REFERENCES subjects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 15. In-app notifications
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    kind VARCHAR(40) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_note_user (user_id, is_read),
    CONSTRAINT fk_note_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
