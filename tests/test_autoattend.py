import unittest
import json
import numpy as np
from app import app
from database.db_manager import db, execute_query, fetch_one, fetch_all, init_db
from services.face_recognition_service import face_service
from services.attendance_service import attendance_service

class AutoAttendTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        init_db()

    def test_database_initialization(self):
        """Verifies students, subjects, classrooms, and users exist."""
        students = fetch_all("SELECT * FROM students;")
        self.assertGreaterEqual(len(students), 1)
        users = fetch_all("SELECT * FROM users;")
        self.assertGreaterEqual(len(users), 1)

    def test_authentication_flow(self):
        """Tests login with valid and invalid credentials."""
        # 1. Invalid login
        res = self.client.post('/api/auth/login', json={
            'email': 'teacher@autoattend.ai',
            'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data['success'])

        # 2. Valid login
        res = self.client.post('/api/auth/login', json={
            'email': 'teacher@autoattend.ai',
            'password': 'password123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('user', data)

    def test_student_management_crud(self):
        """Tests adding, updating, and preventing duplicate roll numbers."""
        # Log in first
        self.client.post('/api/auth/login', json={
            'email': 'teacher@autoattend.ai',
            'password': 'password123'
        })

        # Add a student
        res = self.client.post('/api/students', json={
            'full_name': 'Test Student',
            'roll_number': '0827TEST999',
            'email': 'test.student@piemr.edu.in',
            'department': 'Computer Science & Engineering',
            'class_section': 'CSE-A'
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        stu_id = data['student_id']

        # Duplicate roll number rejection
        dup_res = self.client.post('/api/students', json={
            'full_name': 'Duplicate Person',
            'roll_number': '0827TEST999',
            'email': 'another@piemr.edu.in',
            'department': 'Computer Science & Engineering',
            'class_section': 'CSE-A'
        })
        self.assertEqual(dup_res.status_code, 409)

        # Delete test student
        del_res = self.client.delete(f'/api/students/{stu_id}')
        self.assertEqual(del_res.status_code, 200)

    def test_face_recognition_cosine_math(self):
        """Tests cosine similarity calculations between identical and distinct vectors."""
        vec_a = [1.0, 0.0, 0.5, 0.2]
        vec_b = [1.0, 0.0, 0.5, 0.2]
        sim_identical = face_service.calculate_similarity(vec_a, vec_b)
        self.assertAlmostEqual(sim_identical, 1.0, places=2)

        vec_c = [-1.0, 0.0, -0.5, -0.2]
        sim_opposite = face_service.calculate_similarity(vec_a, vec_c)
        self.assertLess(sim_opposite, 0.2)

    def test_attendance_session_and_record_workflow(self):
        """Tests session creation, multi-frame observation, and single-record enforcement."""
        self.client.post('/api/auth/login', json={
            'email': 'teacher@autoattend.ai',
            'password': 'password123'
        })

        # Create session
        res = self.client.post('/api/attendance/sessions', json={
            'classroom_id': 1,
            'subject_id': 1,
            'is_demo_mode': True
        })
        self.assertEqual(res.status_code, 201)
        session_id = res.get_json()['session']['session_id']
        test_student = fetch_one("SELECT id FROM students LIMIT 1")
        target_student_id = test_student['id'] if test_student else 1

        # Accumulate observations for student
        marked_1, obs_1, _ = face_service.accumulate_observation(session_id, target_student_id, 0.92, min_observations=3)
        self.assertFalse(marked_1) # 1st observation

        marked_2, obs_2, _ = face_service.accumulate_observation(session_id, target_student_id, 0.91, min_observations=3)
        self.assertFalse(marked_2) # 2nd observation

        marked_3, obs_3, _ = face_service.accumulate_observation(session_id, target_student_id, 0.94, min_observations=3)
        self.assertTrue(marked_3) # 3rd observation triggers attendance!

        # 4th observation should not duplicate attendance entry
        marked_4, obs_4, _ = face_service.accumulate_observation(session_id, target_student_id, 0.90, min_observations=3)
        self.assertFalse(marked_4)

        # Verify only 1 record exists in DB for this student in this session
        records = fetch_all("SELECT * FROM attendance_records WHERE session_id = %s AND student_id = %s;", (session_id, target_student_id))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['status'], 'present')

        # Conclude session
        stop_res = self.client.post(f'/api/attendance/sessions/{session_id}/stop')
        self.assertEqual(stop_res.status_code, 200)

    def test_csv_export_endpoint(self):
        """Tests that CSV export returns 200 and text/csv mimetype."""
        self.client.post('/api/auth/login', json={
            'email': 'teacher@autoattend.ai',
            'password': 'password123'
        })
        res = self.client.get('/api/reports/export')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.content_type)
        self.assertIn(b'Record ID,Session Code', res.data)

if __name__ == '__main__':
    unittest.main()
