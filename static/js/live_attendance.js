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

document.addEventListener('DOMContentLoaded', () => {
  loadClassroomsAndSubjects();
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
  try {
    const res = await fetch('/api/camera/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_index: 0, demo_mode: isDemoMode })
    });
    const data = await res.json();

    if (data.success) {
      updateCameraUI(true, data.is_demo_mode);
      showToast(data.is_demo_mode ? 'Demo Simulation Mode Activated' : 'Classroom Camera Connected', 'success');
      startEventsPolling();
    } else {
      // Fallback to browser webcam via getUserMedia
      initBrowserWebcamFallback();
    }
  } catch (err) {
    console.warn('Backend camera connection error. Initializing browser camera fallback...', err);
    initBrowserWebcamFallback();
  }
}

async function initBrowserWebcamFallback() {
  try {
    const videoEl = document.getElementById('browser-video-element');
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    browserCamStream = stream;
    if (videoEl) {
      videoEl.srcObject = stream;
      videoEl.play();
      videoEl.style.display = 'block';
      document.getElementById('camera-stream-img').style.display = 'none';
    }
    updateCameraUI(true, false);
    showToast('Browser Webcam Activated for AI Recognition', 'success');
    startBrowserFrameStreaming();
  } catch (camErr) {
    showToast('No physical camera accessible. Launching Demo Simulation Mode.', 'warning');
    // Launch demo mode
    startCameraCapture(true);
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
        updateStatsHUD({
          detected: result.detections.length,
          recognized: result.detections.filter(d => d.status === 'recognized').length,
          pending: result.detections.filter(d => d.status === 'low_confidence').length
        });
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
      showToast('Attendance Session Started! AI Face Matching active.', 'success');
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
        updateStatsHUD(data.stats);
        renderLiveEvents(data.events);
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
      renderSessionStudentTable(data.records);
      const presEl = document.getElementById('stat-present-count');
      if (presEl && data.metrics) presEl.textContent = data.metrics.present;
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
