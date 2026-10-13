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
