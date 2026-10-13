/**
 * AutoAttend Student Biometric Enrollment & Management Script
 */

let currentPage = 1;
let totalPages = 1;
let enrollmentWebcamStream = null;
let currentEnrollStudentId = null;

document.addEventListener('DOMContentLoaded', () => {
  fetchStudents(1);
  setupFilterListeners();
});

function setupFilterListeners() {
  const searchInput = document.getElementById('student-search-input');
  const sectionFilter = document.getElementById('filter-section');
  const faceFilter = document.getElementById('filter-face-status');

  let debounceTimer;
  searchInput?.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      currentPage = 1;
      fetchStudents(1);
    }, 300);
  });

  sectionFilter?.addEventListener('change', () => {
    currentPage = 1;
    fetchStudents(1);
  });

  faceFilter?.addEventListener('change', () => {
    currentPage = 1;
    fetchStudents(1);
  });
}

async function fetchStudents(page = 1) {
  currentPage = page;
  const search = document.getElementById('student-search-input')?.value.trim() || '';
  const section = document.getElementById('filter-section')?.value || '';
  const faceStatus = document.getElementById('filter-face-status')?.value || '';

  const url = `/api/students?page=${page}&per_page=10&search=${encodeURIComponent(search)}&class_section=${encodeURIComponent(section)}&face_status=${encodeURIComponent(faceStatus)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (data.success) {
      totalPages = data.total_pages;
      renderStudentsTable(data.students);
      renderPagination(data.total, data.page, data.total_pages);
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to load students list', 'danger');
  }
}

function renderStudentsTable(students) {
  const tbody = document.getElementById('students-table-body');
  if (!tbody) return;

  if (students.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7">
          <div class="empty-state">
            <h4 class="empty-state-title">No Students Found</h4>
            <p class="empty-state-desc">Try adjusting your filters or search keywords, or add a new student.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = students.map(s => {
    const pct = s.attendance_percentage !== null ? `${s.attendance_percentage}%` : 'N/A';
    const isRegistered = s.face_registered == 1;

    return `
      <tr>
        <td>
          <div style="display:flex; align-items:center; gap:0.75rem;">
            <img src="${s.avatar_url || '/static/images/avatars/default_avatar.png'}"
                 style="width:38px; height:38px; border-radius:50%; object-fit:cover; border:1px solid var(--border-subtle);"
                 onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <div style="font-weight:700; color:var(--text-heading); cursor:pointer;" onclick="openStudentProfile(${s.id})">${s.full_name}</div>
              <small style="color:var(--text-muted);">${s.email}</small>
            </div>
          </div>
        </td>
        <td><code>${s.roll_number}</code></td>
        <td>${s.class_section}</td>
        <td>${s.department}</td>
        <td>
          ${isRegistered
            ? `<span class="badge badge-present"><span class="pulse-dot"></span> Enrolled</span>`
            : `<span class="badge badge-absent">Pending Biometrics</span>`}
        </td>
        <td>
          <span style="font-weight:700; color:${s.attendance_percentage < 75 ? 'var(--danger)' : 'var(--text-heading)'};">${pct}</span>
        </td>
        <td>
          <div style="display:flex; gap:0.375rem;">
            <button class="btn btn-sm btn-secondary" title="View Profile" onclick="openStudentProfile(${s.id})">Profile</button>
            <button class="btn btn-sm ${isRegistered ? 'btn-secondary' : 'btn-cyan'}" title="Face Biometrics" onclick="openFaceEnrollmentModal(${s.id}, '${s.full_name}', ${isRegistered})">
              ${isRegistered ? 'Retake Face' : 'Register Face'}
            </button>
            <button class="btn btn-sm btn-icon btn-secondary" title="Edit Student" onclick="openEditStudentModal(${s.id}, '${s.full_name}', '${s.roll_number}', '${s.email}', '${s.department}', '${s.class_section}')">✎</button>
            <button class="btn btn-sm btn-icon btn-danger" title="Delete Student" onclick="confirmDeleteStudent(${s.id}, '${s.full_name}')">✕</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderPagination(total, page, pages) {
  const container = document.getElementById('pagination-container');
  if (!container) return;

  container.innerHTML = `
    <span style="font-size:0.875rem; color:var(--text-muted);">Showing page <b>${page}</b> of <b>${pages}</b> (${total} total students)</span>
    <div style="display:flex; gap:0.5rem;">
      <button class="pagination-btn" ${page <= 1 ? 'disabled' : ''} onclick="fetchStudents(${page - 1})">Previous</button>
      <button class="pagination-btn" ${page >= pages ? 'disabled' : ''} onclick="fetchStudents(${page + 1})">Next</button>
    </div>
  `;
}

// Add Student Modal Logic
function openAddStudentModal() {
  document.getElementById('add-student-form')?.reset();
  document.getElementById('add-student-modal')?.classList.add('active');
}

function closeAddStudentModal() {
  document.getElementById('add-student-modal')?.classList.remove('active');
}

async function handleAddStudentSubmit(e) {
  e.preventDefault();
  const full_name = document.getElementById('add-fullname').value.trim();
  const roll_number = document.getElementById('add-roll').value.trim().toUpperCase();
  const email = document.getElementById('add-email').value.trim().toLowerCase();
  const department = document.getElementById('add-dept').value.trim();
  const class_section = document.getElementById('add-section').value.trim();

  try {
    const res = await fetch('/api/students', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name, roll_number, email, department, class_section })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeAddStudentModal();
      fetchStudents(1);
    } else {
      showToast(data.message || 'Error creating student', 'danger');
    }
  } catch (err) {
    showToast('Network error adding student', 'danger');
  }
}

// Edit Student Modal Logic
function openEditStudentModal(id, name, roll, email, dept, section) {
  document.getElementById('edit-student-id').value = id;
  document.getElementById('edit-fullname').value = name;
  document.getElementById('edit-roll').value = roll;
  document.getElementById('edit-email').value = email;
  document.getElementById('edit-dept').value = dept;
  document.getElementById('edit-section').value = section;
  document.getElementById('edit-student-modal')?.classList.add('active');
}

function closeEditStudentModal() {
  document.getElementById('edit-student-modal')?.classList.remove('active');
}

async function handleEditStudentSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('edit-student-id').value;
  const full_name = document.getElementById('edit-fullname').value.trim();
  const roll_number = document.getElementById('edit-roll').value.trim().toUpperCase();
  const email = document.getElementById('edit-email').value.trim().toLowerCase();
  const department = document.getElementById('edit-dept').value.trim();
  const class_section = document.getElementById('edit-section').value.trim();

  try {
    const res = await fetch(`/api/students/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name, roll_number, email, department, class_section })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeEditStudentModal();
      fetchStudents(currentPage);
    } else {
      showToast(data.message || 'Failed to update student', 'danger');
    }
  } catch (err) {
    showToast('Network error updating student', 'danger');
  }
}

// Delete Student
function confirmDeleteStudent(id, name) {
  confirmDialog('Delete Student', `Are you sure you want to delete ${name}? All associated attendance and biometric templates will be permanently removed.`, 'Delete', async () => {
    try {
      const res = await fetch(`/api/students/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        fetchStudents(currentPage);
      } else {
        showToast(data.message || 'Failed to delete student', 'danger');
      }
    } catch (e) {
      showToast('Error deleting student', 'danger');
    }
  });
}

// Face Biometric Registration Variables
let currentEnrollMode = 'webcam';
let uploadedPhotoBase64 = null;
let capturedSnapshotBase64 = null;

async function openFaceEnrollmentModal(studentId, studentName, isRegistered) {
  currentEnrollStudentId = studentId;
  uploadedPhotoBase64 = null;
  capturedSnapshotBase64 = null;

  document.getElementById('enroll-student-name').textContent = studentName;
  const removeBtn = document.getElementById('btn-remove-face-data');
  if (removeBtn) removeBtn.style.display = isRegistered ? 'inline-flex' : 'none';

  // Reset file upload inputs and states
  const fileInput = document.getElementById('enroll-file-input');
  if (fileInput) fileInput.value = '';
  const uploadEmptyState = document.getElementById('upload-empty-state');
  const uploadPreviewState = document.getElementById('upload-preview-state');
  const btnSubmitUpload = document.getElementById('btn-submit-upload');
  if (uploadEmptyState) uploadEmptyState.style.display = 'flex';
  if (uploadPreviewState) uploadPreviewState.style.display = 'none';
  if (btnSubmitUpload) btnSubmitUpload.disabled = true;

  // Setup drag and drop for upload zone
  setupUploadDropzone();

  const modal = document.getElementById('face-enrollment-modal');
  modal?.classList.add('active');

  // Switch to webcam tab by default
  switchEnrollTab('webcam');
}

function switchEnrollTab(mode) {
  currentEnrollMode = mode;
  const btnWebcam = document.getElementById('tab-btn-webcam');
  const btnUpload = document.getElementById('tab-btn-upload');
  const paneWebcam = document.getElementById('tab-pane-webcam');
  const paneUpload = document.getElementById('tab-pane-upload');

  if (mode === 'webcam') {
    if (btnWebcam) {
      btnWebcam.style.background = 'var(--bg-card)';
      btnWebcam.style.color = 'var(--primary)';
      btnWebcam.style.border = '1px solid var(--border-subtle)';
      btnWebcam.style.borderBottomColor = 'var(--bg-card)';
    }
    if (btnUpload) {
      btnUpload.style.background = 'transparent';
      btnUpload.style.color = 'var(--text-muted)';
      btnUpload.style.border = '1px solid transparent';
    }
    if (paneWebcam) paneWebcam.style.display = 'block';
    if (paneUpload) paneUpload.style.display = 'none';

    startEnrollmentWebcam();
  } else {
    if (btnUpload) {
      btnUpload.style.background = 'var(--bg-card)';
      btnUpload.style.color = 'var(--primary)';
      btnUpload.style.border = '1px solid var(--border-subtle)';
      btnUpload.style.borderBottomColor = 'var(--bg-card)';
    }
    if (btnWebcam) {
      btnWebcam.style.background = 'transparent';
      btnWebcam.style.color = 'var(--text-muted)';
      btnWebcam.style.border = '1px solid transparent';
    }
    if (paneWebcam) paneWebcam.style.display = 'none';
    if (paneUpload) paneUpload.style.display = 'block';

    // Stop webcam while on upload tab to free camera device
    stopEnrollmentWebcam();
  }
}

async function startEnrollmentWebcam() {
  const loadingOverlay = document.getElementById('camera-loading-overlay');
  const errorOverlay = document.getElementById('camera-error-overlay');
  const errorMsg = document.getElementById('camera-error-message');
  const video = document.getElementById('enrollment-webcam-preview');
  const canvas = document.getElementById('enrollment-captured-preview');
  const actionsLive = document.getElementById('webcam-actions-live');
  const actionsReview = document.getElementById('webcam-actions-review');

  if (loadingOverlay) loadingOverlay.style.display = 'flex';
  if (errorOverlay) errorOverlay.style.display = 'none';
  if (video) video.style.display = 'block';
  if (canvas) canvas.style.display = 'none';
  if (actionsLive) actionsLive.style.display = 'flex';
  if (actionsReview) actionsReview.style.display = 'none';

  // Stop any lingering stream
  stopEnrollmentWebcam();

  try {
    let stream;
    try {
      // First attempt with ideal 640x480 resolution
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user'
        }
      });
    } catch (constraintErr) {
      console.warn('Initial webcam constraint failed, trying basic video constraint:', constraintErr);
      // Fallback to basic constraint
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
    }

    enrollmentWebcamStream = stream;

    if (video) {
      video.srcObject = stream;
      video.onloadeddata = () => {
        if (loadingOverlay) loadingOverlay.style.display = 'none';
        video.play().catch(e => console.warn('Video play error:', e));
      };
    }
  } catch (err) {
    console.error('Camera access error:', err);
    if (loadingOverlay) loadingOverlay.style.display = 'none';
    if (errorOverlay) {
      errorOverlay.style.display = 'flex';
      if (errorMsg) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          errorMsg.textContent = 'Camera permission was denied. Click the camera icon in your browser address bar to allow access, then click Retry.';
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          errorMsg.textContent = 'Camera is currently in use by another application (Zoom, Teams, or Python). Close other apps and click Retry, or upload a photo.';
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          errorMsg.textContent = 'No camera device found. Please switch to the "Upload Photo" tab to enroll using an image.';
        } else {
          errorMsg.textContent = `Camera error: ${err.message || 'Unable to open camera'}. Switch to "Upload Photo" to continue.`;
        }
      }
    }
    showToast('Camera not accessible. You can upload a student photo instead.', 'warning');
  }
}

function stopEnrollmentWebcam() {
  if (enrollmentWebcamStream) {
    enrollmentWebcamStream.getTracks().forEach(t => t.stop());
    enrollmentWebcamStream = null;
  }
  const video = document.getElementById('enrollment-webcam-preview');
  if (video) {
    video.srcObject = null;
  }
}

function closeFaceEnrollmentModal() {
  stopEnrollmentWebcam();
  capturedSnapshotBase64 = null;
  uploadedPhotoBase64 = null;
  document.getElementById('face-enrollment-modal')?.classList.remove('active');
}

function takeSnapshot() {
  const video = document.getElementById('enrollment-webcam-preview');
  const canvas = document.getElementById('enrollment-captured-preview');
  if (!video || !enrollmentWebcamStream || video.videoWidth === 0 || video.readyState < 2) {
    showToast('Camera is not ready yet. Please wait for camera preview or retry.', 'warning');
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');

  // Draw mirrored to match the user's live mirror view
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  // Check luminance to ensure frame isn't pitch black
  const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  let totalLum = 0;
  const sampleStep = 40;
  let sampleCount = 0;
  for (let i = 0; i < imgData.length; i += sampleStep * 4) {
    totalLum += (imgData[i] * 0.299 + imgData[i + 1] * 0.587 + imgData[i + 2] * 0.114);
    sampleCount++;
  }
  const avgLum = sampleCount > 0 ? (totalLum / sampleCount) : 0;

  if (avgLum < 8) {
    showToast('Captured frame is completely dark. Please ensure camera lens cover is open and room is lit.', 'danger');
    return;
  }

  capturedSnapshotBase64 = canvas.toDataURL('image/jpeg', 0.95);

  // Switch to review mode
  video.style.display = 'none';
  canvas.style.display = 'block';
  document.getElementById('webcam-actions-live').style.display = 'none';
  document.getElementById('webcam-actions-review').style.display = 'flex';
}

function retakeSnapshot() {
  capturedSnapshotBase64 = null;
  const video = document.getElementById('enrollment-webcam-preview');
  const canvas = document.getElementById('enrollment-captured-preview');

  if (canvas) canvas.style.display = 'none';
  if (video) video.style.display = 'block';
  document.getElementById('webcam-actions-live').style.display = 'flex';
  document.getElementById('webcam-actions-review').style.display = 'none';
}

async function saveCapturedSnapshot() {
  if (!capturedSnapshotBase64 || !currentEnrollStudentId) {
    showToast('No snapshot captured to register.', 'warning');
    return;
  }

  const btn = document.getElementById('btn-confirm-face');
  const originalHtml = btn.innerHTML;
  btn.textContent = 'Analyzing & Registering...';
  btn.disabled = true;

  try {
    const res = await fetch(`/api/students/${currentEnrollStudentId}/register-face`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: capturedSnapshotBase64 })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      closeFaceEnrollmentModal();
      fetchStudents(currentPage);
    } else {
      showToast(data.message || 'Face enrollment failed. Ensure a single face is clearly visible.', 'danger');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error during face registration', 'danger');
  } finally {
    btn.innerHTML = originalHtml;
    btn.disabled = false;
  }
}

// Upload Tab Functions
function handlePhotoFileSelected(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    showToast('Please select a valid image file (JPG, PNG, WEBP)', 'warning');
    return;
  }

  const reader = new FileReader();
  reader.onload = function(evt) {
    uploadedPhotoBase64 = evt.target.result;
    const previewImg = document.getElementById('upload-image-preview');
    if (previewImg) previewImg.src = uploadedPhotoBase64;

    const emptyState = document.getElementById('upload-empty-state');
    const previewState = document.getElementById('upload-preview-state');
    const submitBtn = document.getElementById('btn-submit-upload');

    if (emptyState) emptyState.style.display = 'none';
    if (previewState) previewState.style.display = 'block';
    if (submitBtn) submitBtn.disabled = false;
  };
  reader.readAsDataURL(file);
}

function setupUploadDropzone() {
  const dropzone = document.getElementById('upload-dropzone');
  if (!dropzone || dropzone.dataset.hasDropListeners) return;

  dropzone.dataset.hasDropListeners = 'true';

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = 'var(--primary)';
      dropzone.style.background = '#EEF2FF';
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = 'var(--border-subtle)';
      dropzone.style.background = '#F8FAFC';
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const file = dt?.files?.[0];
    if (file) {
      const fileInput = document.getElementById('enroll-file-input');
      if (fileInput) fileInput.files = dt.files;
      handlePhotoFileSelected({ target: { files: [file] } });
    }
  });
}

async function submitUploadedPhoto() {
  if (!uploadedPhotoBase64 || !currentEnrollStudentId) {
    showToast('Please select or upload a student photo first.', 'warning');
    return;
  }

  const btn = document.getElementById('btn-submit-upload');
  const originalHtml = btn.innerHTML;
  btn.textContent = 'Analyzing Facial Features...';
  btn.disabled = true;

  try {
    const res = await fetch(`/api/students/${currentEnrollStudentId}/register-face`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: uploadedPhotoBase64 })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      closeFaceEnrollmentModal();
      fetchStudents(currentPage);
    } else {
      showToast(data.message || 'Face registration failed. Please ensure the photo has a clear frontal face.', 'danger');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error during face registration', 'danger');
  } finally {
    btn.innerHTML = originalHtml;
    btn.disabled = false;
  }
}

async function removeFaceData() {
  if (!currentEnrollStudentId) return;
  confirmDialog('Remove Biometric Face Template', 'Are you sure you want to delete this student’s registered facial template? The AI camera will no longer recognize them.', 'Remove Face Data', async () => {
    try {
      const res = await fetch(`/api/students/${currentEnrollStudentId}/face`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeFaceEnrollmentModal();
        fetchStudents(currentPage);
      }
    } catch (e) {
      showToast('Error removing face template', 'danger');
    }
  });
}

// Student Profile Drawer/Modal
async function openStudentProfile(studentId) {
  try {
    const res = await fetch(`/api/students/${studentId}`);
    const data = await res.json();
    if (!data.success) return;

    const s = data.student;
    const st = data.attendance_stats;

    let modal = document.getElementById('student-profile-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'student-profile-modal';
      modal.className = 'modal-overlay';
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="modal-content" style="max-width: 600px;">
        <div class="modal-header">
          <h3 class="card-title">Student Profile</h3>
          <button class="btn btn-icon btn-secondary" onclick="document.getElementById('student-profile-modal').classList.remove('active')">✕</button>
        </div>
        <div class="modal-body">
          <div style="display:flex; align-items:center; gap:1.25rem; margin-bottom:1.5rem;">
            <img src="${s.avatar_url || '/static/images/avatars/default_avatar.png'}" style="width:72px; height:72px; border-radius:50%; object-fit:cover; border:2px solid var(--border-subtle);" onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <h2 style="font-size:1.25rem; font-weight:800; color:var(--text-heading);">${s.full_name}</h2>
              <div style="color:var(--text-muted); font-size:0.875rem;">Roll: <b>${s.roll_number}</b> • ${s.class_section}</div>
              <div style="color:var(--text-muted); font-size:0.8125rem;">${s.email}</div>
            </div>
          </div>
          <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:0.75rem; text-align:center; margin-bottom:1.5rem;">
            <div style="background:#F8FAFC; border:1px solid var(--border-subtle); padding:0.75rem; border-radius:var(--radius-md);">
              <small style="color:var(--text-muted);">Lectures</small>
              <div style="font-size:1.25rem; font-weight:800;">${st.total_lectures}</div>
            </div>
            <div style="background:#ECFDF5; border:1px solid var(--success-border); padding:0.75rem; border-radius:var(--radius-md);">
              <small style="color:var(--success);">Present</small>
              <div style="font-size:1.25rem; font-weight:800; color:var(--success);">${st.present}</div>
            </div>
            <div style="background:#FEF2F2; border:1px solid var(--danger-border); padding:0.75rem; border-radius:var(--radius-md);">
              <small style="color:var(--danger);">Absent</small>
              <div style="font-size:1.25rem; font-weight:800; color:var(--danger);">${st.absent}</div>
            </div>
            <div style="background:#EEF2FF; border:1px solid var(--primary-border); padding:0.75rem; border-radius:var(--radius-md);">
              <small style="color:var(--primary);">Rate</small>
              <div style="font-size:1.25rem; font-weight:800; color:var(--primary);">${st.percentage}%</div>
            </div>
          </div>
          <h4 style="font-size:0.9375rem; margin-bottom:0.75rem;">Recent Attendance History</h4>
          <div class="table-responsive" style="max-height: 200px; overflow-y:auto;">
            <table class="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Method</th>
                </tr>
              </thead>
              <tbody>
                ${data.recent_records && data.recent_records.length > 0 ? data.recent_records.map(r => `
                  <tr>
                    <td>${r.session_date}</td>
                    <td>${r.subject_code}</td>
                    <td><span class="badge ${r.status === 'present' ? 'badge-present' : (r.status === 'late' ? 'badge-late' : 'badge-absent')}">${r.status.toUpperCase()}</span></td>
                    <td><small>${r.verification_method}</small></td>
                  </tr>
                `).join('') : `<tr><td colspan="4" style="text-align:center;">No records available.</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" onclick="document.getElementById('student-profile-modal').classList.remove('active')">Close</button>
        </div>
      </div>
    `;
    modal.classList.add('active');
  } catch (e) {
    showToast('Failed to load student profile', 'danger');
  }
}
