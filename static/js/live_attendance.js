/**
 * AutoAttend Live AI Recognition Studio
 * Controls camera capture, AI session state, live HUD metrics,
 * and multi-frame student attendance synchronization.
 */

let activeSessionId = null;
let sessionTimerInterval = null;
let sessionSeconds = 0;
let eventsPollingInterval = null;
let browserCamStream = null;
let browserFrameInterval = null;
let isDemoMode = false;
let enrolledStudents = [];
let savedRecords = [];
let latestDetections = [];

document.addEventListener('DOMContentLoaded', () => {
  loadClassroomsAndSubjects();
  loadEnrolledRoster();
  setupEventListeners();
  checkCurrentCameraState();
});

async function loadClassroomsAndSubjects() {
  try {
    const [roomsRes, subsRes] = await Promise.all([
      fetch('/api/classrooms'),
      fetch('/api/subjects')
    ]);

    const roomsData = await roomsRes.json();
    const subsData = await subsRes.json();

    const roomSelect = document.getElementById('session-classroom-select');
    const subSelect = document.getElementById('session-subject-select');

    if (roomSelect && roomsData.classrooms) {
      roomSelect.innerHTML = roomsData.classrooms.map(r =>
        `<option value="${r.id}">${r.room_number} (${r.building})</option>`
      ).join('');
    }

    if (subSelect && subsData.subjects) {
      subSelect.innerHTML = subsData.subjects.map(s =>
        `<option value="${s.id}">${s.subject_code} - ${s.subject_name}</option>`
      ).join('');
    }
  } catch (err) {
    console.error('Failed to load classrooms/subjects:', err);
  }
}

function setupEventListeners() {
  // Start Camera
  document.getElementById('btn-start-camera')?.addEventListener('click', () => {
    startCameraCapture(false);
  });

  // Start Demo Mode
  document.getElementById('btn-start-demo')?.addEventListener('click', () => {
    startCameraCapture(true);
  });

  // Stop Camera
  document.getElementById('btn-stop-camera')?.addEventListener('click', () => {
    stopCameraCapture();
  });

  // Start Attendance Session
  document.getElementById('btn-start-session')?.addEventListener('click', () => {
    startAttendanceSession();
  });
  document.getElementById('btn-start-session-inline')?.addEventListener('click', () => {
    startAttendanceSession();
  });

  // End Attendance Session
  document.getElementById('btn-end-session')?.addEventListener('click', () => {
    endAttendanceSession();
  });
}

async function checkCurrentCameraState() {
  try {
    const res = await fetch('/api/camera/events');
    const data = await res.json();
    if (data.is_running) {
      updateCameraUI(true, data.is_demo_mode);
      if (data.active_session_id) {
        activeSessionId = data.active_session_id;
        startSessionTimer();
        startEventsPolling();
      }
    }
  } catch (e) {}
}

async function startCameraCapture(demoModeRequested = false) {
  isDemoMode = demoModeRequested;
  if (!demoModeRequested) {
    const opened = await initBrowserWebcamFallback();
    if (opened === true || opened === 'denied') return;
    showToast('Camera did not start. Opening the practice view instead.', 'warning');
    isDemoMode = true;
  }

  try {
    const res = await fetch('/api/camera/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_index: 0, demo_mode: true })
    });
    const data = await res.json();
    if (data.success) {
      updateCameraUI(true, true);
      showToast(demoModeRequested ? 'Practice view is on.' : 'Practice camera is on.', 'info');
      startEventsPolling();
    }
  } catch (err) {
    showToast('Camera could not start.', 'danger');
  }
}

async function initBrowserWebcamFallback() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Open http://127.0.0.1:5000 to use the camera.');
    }
    const videoEl = document.getElementById('browser-video-element');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    } catch (firstErr) {
      if (firstErr && (firstErr.name === 'NotAllowedError' || firstErr.name === 'PermissionDeniedError')) throw firstErr;
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }
    browserCamStream = stream;
    if (videoEl) {
      videoEl.srcObject = stream;
      await videoEl.play();
      videoEl.style.display = 'block';
      const feed = document.getElementById('camera-stream-img');
      if (feed) feed.style.display = 'none';
    }
    updateCameraUI(true, false);
    showToast('Camera is on. Choose Allow if the browser asks.', 'success');
    startBrowserFrameStreaming();
    return true;
  } catch (camErr) {
    console.warn('Browser camera failed', camErr);
    if (camErr && (camErr.name === 'NotAllowedError' || camErr.name === 'PermissionDeniedError')) {
      showToast('Camera permission was blocked. Click the camera icon in the address bar and choose Allow.', 'danger');
      return 'denied';
    }
    return false;
  }
}

function startBrowserFrameStreaming() {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  const video = document.getElementById('browser-video-element');

  if (browserFrameInterval) clearInterval(browserFrameInterval);

  browserFrameInterval = setInterval(async () => {
    if (!video || video.paused || video.ended) return;
    ctx.drawImage(video, 0, 0, 640, 480);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.8);

    try {
      const res = await fetch('/api/camera/process-frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: dataUrl, session_id: activeSessionId })
      });
      const result = await res.json();
      if (result.success && result.detections) {
        latestDetections = result.detections;
        updateStatsHUD({
          detected: result.detections.length,
          recognized: result.detections.filter(d => d.status === 'recognized').length,
          pending: result.detections.filter(d => d.status === 'low_confidence' || d.status === 'unknown').length
        });
        renderRecognitionFeed(result.detections);
        renderLiveRoster();
        if (activeSessionId) loadSessionRecords();
      }
    } catch (e) {}
  }, 1500);
}

async function stopCameraCapture() {
  if (browserCamStream) {
    browserCamStream.getTracks().forEach(t => t.stop());
    browserCamStream = null;
  }
  if (browserFrameInterval) clearInterval(browserFrameInterval);

  try {
    await fetch('/api/camera/stop', { method: 'POST' });
  } catch (e) {}

  updateCameraUI(false);
  stopEventsPolling();
  showToast('Camera feed stopped', 'info');
}

function updateCameraUI(isRunning, isDemo = false) {
  const feedImg = document.getElementById('camera-stream-img');
  const placeholder = document.getElementById('camera-placeholder');
  const browserVideo = document.getElementById('browser-video-element');
  const statusPill = document.getElementById('ai-status-pill');
  const btnStartCam = document.getElementById('btn-start-camera');
  const btnStartDemo = document.getElementById('btn-start-demo');
  const btnStopCam = document.getElementById('btn-stop-camera');
  const btnStartSess = document.getElementById('btn-start-session');

  if (isRunning) {
    if (!browserCamStream && feedImg) {
      feedImg.src = '/api/camera/stream?' + Date.now();
      feedImg.style.display = 'block';
    }
    if (placeholder) placeholder.style.display = 'none';
    if (btnStartCam) btnStartCam.style.display = 'none';
    if (btnStartDemo) btnStartDemo.style.display = 'none';
    if (btnStopCam) btnStopCam.style.display = 'inline-flex';
    if (btnStartSess && !activeSessionId) btnStartSess.disabled = false;

    if (statusPill) {
      statusPill.innerHTML = isDemo
        ? `<span class="pulse-dot" style="background:#06B6D4"></span> DEMO AI SIMULATION`
        : `<span class="pulse-dot" style="background:#10B981"></span> AI ENGINE LIVE`;
      statusPill.className = 'badge ' + (isDemo ? 'badge-ai' : 'badge-present');
    }
  } else {
    if (feedImg) {
      feedImg.src = '';
      feedImg.style.display = 'none';
    }
    if (browserVideo) browserVideo.style.display = 'none';
    if (placeholder) placeholder.style.display = 'flex';
    if (btnStartCam) btnStartCam.style.display = 'inline-flex';
    if (btnStartDemo) btnStartDemo.style.display = 'inline-flex';
    if (btnStopCam) btnStopCam.style.display = 'none';
    if (btnStartSess) btnStartSess.disabled = true;

    if (statusPill) {
      statusPill.innerHTML = `<span class="pulse-dot" style="background:#64748B"></span> CAMERA STANDBY`;
      statusPill.className = 'badge badge-secondary';
    }
  }
}

async function startAttendanceSession() {
  const roomId = document.getElementById('session-classroom-select')?.value;
  const subId = document.getElementById('session-subject-select')?.value;

  if (!roomId || !subId) {
    showToast('Please select Classroom and Subject.', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/attendance/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ classroom_id: roomId, subject_id: subId, is_demo_mode: isDemoMode })
    });
    const data = await res.json();

    if (data.success) {
      activeSessionId = data.session.session_id;
      document.getElementById('btn-start-session').style.display = 'none';
      document.getElementById('btn-end-session').style.display = 'inline-flex';
      document.getElementById('session-code-display').textContent = data.session.session_code;
      document.getElementById('session-classroom-select').disabled = true;
      document.getElementById('session-subject-select').disabled = true;

      startSessionTimer();
      showToast('Attendance session started. Recognized students are saved after 3 frames.', 'success');
      document.getElementById('session-needed-note').style.display = 'none';
      loadSessionRecords();
    } else {
      showToast(data.message || 'Failed to start session', 'danger');
    }
  } catch (err) {
    showToast('Network error starting session', 'danger');
  }
}

async function endAttendanceSession() {
  if (!activeSessionId) return;

  confirmDialog('End Attendance Session', 'Are you sure you want to conclude attendance? Remaining unverified students will be marked absent.', 'End Session', async () => {
    try {
      const res = await fetch(`/api/attendance/sessions/${activeSessionId}/stop`, { method: 'POST' });
      const data = await res.json();

      if (data.success) {
        stopSessionTimer();
        document.getElementById('btn-start-session').style.display = 'inline-flex';
        document.getElementById('btn-end-session').style.display = 'none';
        document.getElementById('session-classroom-select').disabled = false;
        document.getElementById('session-subject-select').disabled = false;

        showSessionSummaryModal(data);
        activeSessionId = null;
        savedRecords = [];
        renderLiveRoster();
      }
    } catch (e) {
      showToast('Error ending session', 'danger');
    }
  });
}

function startSessionTimer() {
  sessionSeconds = 0;
  if (sessionTimerInterval) clearInterval(sessionTimerInterval);
  const timerEl = document.getElementById('session-timer-display');
  sessionTimerInterval = setInterval(() => {
    sessionSeconds++;
    const mins = String(Math.floor(sessionSeconds / 60)).padStart(2, '0');
    const secs = String(sessionSeconds % 60).padStart(2, '0');
    if (timerEl) timerEl.textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopSessionTimer() {
  if (sessionTimerInterval) clearInterval(sessionTimerInterval);
  sessionTimerInterval = null;
}

function startEventsPolling() {
  if (eventsPollingInterval) clearInterval(eventsPollingInterval);
  eventsPollingInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/camera/events');
      const data = await res.json();
      if (data.success) {
        if (!browserCamStream) {
          updateStatsHUD(data.stats);
          renderLiveEvents(data.events);
        }
        if (activeSessionId) {
          loadSessionRecords();
        }
      }
    } catch (e) {}
  }, 1500);
}

function stopEventsPolling() {
  if (eventsPollingInterval) clearInterval(eventsPollingInterval);
  eventsPollingInterval = null;
}

function updateStatsHUD(stats) {
  if (!stats) return;
  const detEl = document.getElementById('stat-detected-count');
  const recEl = document.getElementById('stat-recognized-count');
  const pendEl = document.getElementById('stat-pending-count');

  if (detEl) detEl.textContent = stats.detected || 0;
  if (recEl) recEl.textContent = stats.recognized || 0;
  if (pendEl) pendEl.textContent = stats.pending || 0;
}

async function loadEnrolledRoster() {
  try {
    const res = await fetch('/api/students?per_page=100&face_status=registered');
    const data = await res.json();
    enrolledStudents = data.students || [];
    renderLiveRoster();
  } catch (err) {
    console.error('Failed to load enrolled students', err);
  }
}

function renderRecognitionFeed(detections) {
  const container = document.getElementById('live-events-scroll');
  const note = document.getElementById('session-needed-note');
  if (!container) return;
  const recognized = (detections || []).filter(d => d.student_id);
  if (note) note.style.display = recognized.length && !activeSessionId ? 'block' : 'none';
  if (!detections || detections.length === 0) {
    container.innerHTML = `<div class="empty-state" style="padding: 1rem;"><small>No face in this frame yet.</small></div>`;
    return;
  }
  container.innerHTML = detections.map(det => {
    const name = det.full_name || 'Unknown face';
    const roll = det.roll_number && det.roll_number !== 'N/A' ? det.roll_number : '';
    const confidence = Math.round((det.confidence || 0) * 100);
    let detail = 'Not enrolled';
    if (det.status === 'recognized') {
      detail = det.is_marked
        ? 'Marked present'
        : (activeSessionId ? `Saving attendance · frame ${det.observations || 1} of 3` : 'Recognized · start the session to save attendance');
    } else if (det.status === 'low_confidence') {
      detail = 'Uncertain match · needs review';
    }
    return `
      <div class="event-entry ${det.status === 'recognized' ? 'success' : 'warning'}">
        <div style="display:flex; justify-content:space-between; margin-bottom: 2px;">
          <strong style="color:var(--text-heading);">${name}${roll ? ` · ${roll}` : ''}</strong>
          <small style="color:var(--text-muted);">${confidence}%</small>
        </div>
        <span style="font-size:0.75rem; color:var(--text-muted);">${detail}</span>
      </div>
    `;
  }).join('');
}

function renderLiveRoster() {
  const tbody = document.getElementById('live-student-table-body');
  if (!tbody) return;
  const rows = new Map();
  enrolledStudents.forEach(student => {
    rows.set(student.id, {
      id: student.id,
      record_id: null,
      full_name: student.full_name,
      roll_number: student.roll_number,
      avatar_url: student.avatar_url,
      status: 'not_seen',
      confidence_score: 0,
      repeated_observations: 0
    });
  });
  latestDetections.forEach(det => {
    if (!det.student_id) return;
    const row = rows.get(det.student_id) || {
      id: det.student_id,
      record_id: null,
      full_name: det.full_name,
      roll_number: det.roll_number,
      avatar_url: det.avatar_url,
      status: 'not_seen',
      confidence_score: 0,
      repeated_observations: 0
    };
    row.full_name = det.full_name || row.full_name;
    row.roll_number = det.roll_number || row.roll_number;
    row.confidence_score = det.confidence || 0;
    row.repeated_observations = det.observations || row.repeated_observations || 1;
    if (det.status === 'recognized') row.status = det.is_marked ? 'present' : 'scanning';
    else if (det.status === 'low_confidence') row.status = 'needs_review';
    rows.set(det.student_id, row);
  });
  savedRecords.forEach(record => {
    const row = rows.get(record.student_id) || {
      id: record.student_id,
      full_name: record.full_name,
      roll_number: record.roll_number,
      avatar_url: record.avatar_url,
      confidence_score: 0,
      repeated_observations: 0
    };
    row.record_id = record.id;
    row.full_name = record.full_name || row.full_name;
    row.roll_number = record.roll_number || row.roll_number;
    row.confidence_score = record.confidence_score || row.confidence_score;
    row.repeated_observations = record.repeated_observations || row.repeated_observations;
    if (['present', 'late', 'absent', 'approved_leave'].includes(record.status)) row.status = record.status;
    rows.set(record.student_id, row);
  });

  const order = { present: 0, late: 1, scanning: 2, needs_review: 3, not_seen: 4, absent: 5, approved_leave: 6 };
  const list = [...rows.values()].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || a.full_name.localeCompare(b.full_name));
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:2rem; color:var(--text-muted);">No enrolled students have a registered face yet.</td></tr>`;
    return;
  }
  const labels = {
    present: ['badge-present', 'PRESENT'],
    late: ['badge-late', 'LATE'],
    scanning: ['badge-ai', 'IN FRAME'],
    needs_review: ['badge-late', 'REVIEW'],
    not_seen: ['badge-secondary', 'NOT IN FRAME'],
    absent: ['badge-absent', 'ABSENT'],
    approved_leave: ['badge-primary', 'LEAVE']
  };
  tbody.innerHTML = list.map(row => {
    const [badge, label] = labels[row.status] || ['badge-secondary', row.status];
    const confidence = row.confidence_score ? `${Math.round(row.confidence_score * 100)}%` : '—';
    const frames = row.repeated_observations ? `${row.repeated_observations} frames` : '—';
    const edit = row.record_id
      ? `<button class="btn btn-sm btn-secondary" onclick="openManualEditModal(${row.record_id}, '${row.status}', '${row.full_name.replace(/'/g, '')}')">Edit</button>`
      : '—';
    return `
      <tr>
        <td>
          <div style="display:flex; align-items:center; gap:0.625rem;">
            <img src="${row.avatar_url || '/static/images/avatars/default_avatar.png'}" style="width:32px; height:32px; border-radius:50%; object-fit:cover;" onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <div style="font-weight:600; color:var(--text-heading);">${row.full_name}</div>
              <small>${row.roll_number || ''}</small>
            </div>
          </div>
        </td>
        <td><span class="badge ${badge}">${label}</span></td>
        <td><b>${confidence}</b></td>
        <td>${frames}</td>
        <td>${edit}</td>
      </tr>
    `;
  }).join('');
  const presentCount = list.filter(row => row.status === 'present' || row.status === 'late').length;
  const presentEl = document.getElementById('stat-present-count');
  if (presentEl) presentEl.textContent = presentCount;
}

function renderLiveEvents(events) {
  const container = document.getElementById('live-events-scroll');
  if (!container || !events) return;

  if (events.length === 0) {
    container.innerHTML = `<div class="empty-state" style="padding: 1rem;"><small>Awaiting camera detections...</small></div>`;
    return;
  }

  container.innerHTML = events.slice(0, 15).map(ev => {
    return `
      <div class="event-entry ${ev.type}">
        <div style="display:flex; justify-content:space-between; margin-bottom: 2px;">
          <strong style="color:var(--text-heading);">${ev.message}</strong>
          <small style="color:var(--text-muted);">${ev.time}</small>
        </div>
        ${ev.data && ev.data.confidence ? `<span style="font-size:0.75rem; color:var(--text-muted);">Confidence: <b>${Math.round(ev.data.confidence * 100)}%</b></span>` : ''}
      </div>
    `;
  }).join('');
}

async function loadSessionRecords() {
  if (!activeSessionId) return;
  try {
    const res = await fetch(`/api/attendance/sessions/${activeSessionId}`);
    const data = await res.json();
    if (data.success && data.records) {
      savedRecords = data.records;
      renderLiveRoster();
    }
  } catch (e) {}
}

function renderSessionStudentTable(records) {
  const tbody = document.getElementById('live-student-table-body');
  if (!tbody) return;

  if (records.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color:var(--text-muted);">No students recognized yet in this session.</td></tr>`;
    return;
  }

  tbody.innerHTML = records.map(r => {
    let badge = 'badge-present';
    if (r.status === 'absent') badge = 'badge-absent';
    else if (r.status === 'late') badge = 'badge-late';

    return `
      <tr>
        <td>
          <div style="display:flex; align-items:center; gap:0.625rem;">
            <img src="${r.avatar_url || '/static/images/avatars/default_avatar.png'}" style="width:32px; height:32px; border-radius:50%; object-fit:cover;" onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <div style="font-weight:600; color:var(--text-heading);">${r.full_name}</div>
              <small>${r.roll_number}</small>
            </div>
          </div>
        </td>
        <td><span class="badge ${badge}">${r.status.toUpperCase()}</span></td>
        <td><b>${Math.round(r.confidence_score * 100)}%</b></td>
        <td>${r.repeated_observations} frames</td>
        <td>
          <button class="btn btn-sm btn-secondary" onclick="openManualEditModal(${r.id}, '${r.status}', '${r.full_name}')">Edit</button>
        </td>
      </tr>
    `;
  }).join('');
}

function showSessionSummaryModal(summaryData) {
  const m = summaryData.metrics || {};
  let modal = document.getElementById('session-summary-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'session-summary-modal';
    modal.className = 'modal-overlay';
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="modal-content" style="max-width: 580px;">
      <div class="modal-header">
        <h3 class="card-title">Session Concluded</h3>
        <button class="btn btn-icon btn-secondary" onclick="document.getElementById('session-summary-modal').classList.remove('active')">✕</button>
      </div>
      <div class="modal-body">
        <div style="background:#F8FAFC; border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1rem; margin-bottom:1.25rem;">
          <h4 style="margin-bottom:0.25rem;">${summaryData.session?.subject_name}</h4>
          <p style="color:var(--text-muted); font-size:0.875rem;">Room: ${summaryData.session?.room_number} • Code: ${summaryData.session?.session_code}</p>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:0.75rem; text-align:center; margin-bottom:1.5rem;">
          <div style="background:#EEF2FF; padding:0.75rem; border-radius:var(--radius-md);">
            <small style="color:var(--primary); font-weight:700;">TOTAL</small>
            <div style="font-size:1.5rem; font-weight:800; color:var(--primary);">${m.total || 0}</div>
          </div>
          <div style="background:#ECFDF5; padding:0.75rem; border-radius:var(--radius-md);">
            <small style="color:var(--success); font-weight:700;">PRESENT</small>
            <div style="font-size:1.5rem; font-weight:800; color:var(--success);">${m.present || 0}</div>
          </div>
          <div style="background:#FEF2F2; padding:0.75rem; border-radius:var(--radius-md);">
            <small style="color:var(--danger); font-weight:700;">ABSENT</small>
            <div style="font-size:1.5rem; font-weight:800; color:var(--danger);">${m.absent || 0}</div>
          </div>
          <div style="background:#ECFEFF; padding:0.75rem; border-radius:var(--radius-md);">
            <small style="color:var(--accent-cyan); font-weight:700;">PERCENT</small>
            <div style="font-size:1.5rem; font-weight:800; color:#0284C7;">${m.percentage || 0}%</div>
          </div>
        </div>
        <p style="font-size:0.875rem; color:var(--text-muted);">
          All attendance records have been securely committed to the database. You can review audit logs or export CSV reports at any time.
        </p>
      </div>
      <div class="modal-footer">
        <a href="/attendance" class="btn btn-secondary">View Records</a>
        <button class="btn btn-primary" onclick="document.getElementById('session-summary-modal').classList.remove('active')">Done</button>
      </div>
    </div>
  `;

  modal.classList.add('active');
}
