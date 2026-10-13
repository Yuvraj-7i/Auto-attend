-- Seed data for AutoAttend AI Attendance System
USE autoattend_db;

-- 1. Faculty / Teachers
INSERT INTO users (id, full_name, email, password_hash, role, department, avatar_url) VALUES
(1, 'Dr. Ajay Jaiswal', 'ajay.jaiswal@piemr.edu.in', 'scrypt:32768:8:1$EV8IWDpWLBKqpZJq$54e4637a301258343f758663bfe30b3d710de764524b4b52b780dd24e18a112ae33f4b016329a1cad5817428e659840f583f4b744b0688e5accff1b4456eb3db', 'admin', 'Computer Science & Engineering', '/static/images/avatars/teacher_ajay.png'),
(2, 'Prof. Neha Sharma', 'teacher@autoattend.ai', 'scrypt:32768:8:1$EV8IWDpWLBKqpZJq$54e4637a301258343f758663bfe30b3d710de764524b4b52b780dd24e18a112ae33f4b016329a1cad5817428e659840f583f4b744b0688e5accff1b4456eb3db', 'teacher', 'Computer Science & Engineering', '/static/images/avatars/teacher_neha.png')
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);

-- 2. Classrooms
INSERT INTO classrooms (id, room_number, building, capacity, camera_ip, is_active) VALUES
(1, 'Lab 301 - AI & Vision Lab', 'Block A - 3rd Floor', 60, '0', 1),
(2, 'Room 302 - CSE Seminar Hall', 'Block A - 3rd Floor', 120, '0', 1),
(3, 'Room 204 - Smart Classroom', 'Block B - 2nd Floor', 75, '0', 1),
(4, 'Lab 405 - High Performance Computing', 'Block A - 4th Floor', 45, '0', 1)
ON DUPLICATE KEY UPDATE room_number=VALUES(room_number);

-- 3. Subjects
INSERT INTO subjects (id, subject_code, subject_name, department, semester) VALUES
(1, 'CS-601', 'Machine Learning & Deep Learning', 'Computer Science & Engineering', 6),
(2, 'CS-602', 'Computer Vision & Image Processing', 'Computer Science & Engineering', 6),
(3, 'CS-603', 'Database Management & Cloud Systems', 'Computer Science & Engineering', 6),
(4, 'CS-604', 'Software Engineering & Agile Practices', 'Computer Science & Engineering', 6)
ON DUPLICATE KEY UPDATE subject_name=VALUES(subject_name);

-- 4. Registered Students (Featuring Minor Project Team + Classmates)
INSERT INTO students (id, student_id, full_name, roll_number, email, department, class_section, face_registered, avatar_url, consent_given) VALUES
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
(15, 'STU-0827-15', 'Aryan Choudhary', '0827CS211022', 'aryan.c@student.piemr.edu.in', 'Computer Science & Engineering', 'CSE-A', 0, '/static/images/avatars/avatar_15.png', 1)
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);

-- 5. System Settings
INSERT INTO system_settings (key_name, value_text, description) VALUES
('face_match_threshold', '0.65', 'Cosine similarity threshold for accepting face identity match'),
('min_observations', '3', 'Minimum consecutive frames a face must be identified before marking attendance'),
('frame_capture_interval', '1.5', 'Time interval in seconds between backend AI processing passes'),
('camera_source', '0', 'Default camera index (0 = default webcam) or RTSP stream URL'),
('enable_anti_spoofing', 'false', 'Enable liveness and anti-spoofing verification'),
('attendance_grace_period_mins', '15', 'Minutes from lecture start after which student is considered late')
ON DUPLICATE KEY UPDATE value_text=VALUES(value_text);
