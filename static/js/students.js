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
            ? `<span class="badge badge-present"><span class="pulse-dot"></span> ${s.face_samples ? s.face_samples + ' photos' : 'Photos saved'}</span>`
            : `<span class="badge badge-absent">No photos yet</span>`}
        </td>
        <td>
          <span style="font-weight:700; color:${s.attendance_percentage < 75 ? 'var(--danger)' : 'var(--text-heading)'};">${pct}</span>
        </td>
        <td>
          <div style="display:flex; gap:0.375rem;">
            <button class="btn btn-sm btn-secondary" title="View Profile" onclick="openStudentProfile(${s.id})">Profile</button>
            <button class="btn btn-sm ${isRegistered ? 'btn-secondary' : 'btn-cyan'}" title="Face photos" onclick="openFaceEnrollmentModal(${s.id}, '${String(s.full_name).replace(/'/g, "\\'")}', ${isRegistered})">
              ${isRegistered ? 'Add photos' : 'Take photos'}
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

// Face photo registration
const FACE_STEPS = [
  { id: 'front', label: 'Front', title: 'Look straight', hint: 'Face the camera. Keep your face inside the oval.', required: true },
  { id: 'left', label: 'Left', title: 'Turn left', hint: 'Turn your head a little to your left.', required: true },
  { id: 'right', label: 'Right', title: 'Turn right', hint: 'Turn your head a little to your right.', required: true },
  { id: 'up', label: 'Up', title: 'Chin up', hint: 'Lift your chin slightly.', required: true },
  { id: 'down', label: 'Down', title: 'Chin down', hint: 'Lower your chin slightly.', required: true },
  { id: 'other', label: 'Extra', title: 'One more view', hint: 'A small smile or a slight tilt. You can skip this one.', required: false }
];

let currentEnrollMode = 'webcam';
let uploadedPhotoBase64 = null;
let currentAngleIndex = 0;
let savedAngles = {};

function requiredAnglesDone() {
  return FACE_STEPS.filter(step => step.required).every(step => savedAngles[step.id]);
}

function renderAngleSteps() {
  const wrap = document.getElementById('angle-steps');
  if (!wrap) return;
  wrap.innerHTML = FACE_STEPS.map((step, index) => {
    const done = Boolean(savedAngles[step.id]);
    const current = index === currentAngleIndex;
    return `<button type="button" class="angle-step${done ? ' is-done' : ''}${current ? ' is-current' : ''}" onclick="goToAngle(${index})">${done ? '✓ ' : ''}${step.label}</button>`;
  }).join('');

  const step = FACE_STEPS[currentAngleIndex];
  const title = document.getElementById('angle-title');
  const hint = document.getElementById('angle-hint');
  const skip = document.getElementById('btn-skip-angle');
  if (title) title.textContent = step.title;
  if (hint) hint.textContent = step.hint;
  if (skip) skip.style.display = step.required ? 'none' : 'inline-flex';

  const select = document.getElementById('upload-angle-select');
  if (select && select.options.length !== FACE_STEPS.length) {
    select.innerHTML = FACE_STEPS.map(item => `<option value="${item.id}">${item.title}</option>`).join('');
  }
  if (select) select.value = step.id;

  const finish = document.getElementById('btn-finish-faces');
  if (finish) {
    const doneCount = FACE_STEPS.filter(step => step.required && savedAngles[step.id]).length;
    finish.disabled = !requiredAnglesDone();
    finish.textContent = requiredAnglesDone() ? 'Finish' : `Finish (${doneCount}/5)`;
  }

  const row = document.getElementById('saved-angle-row');
  if (row) {
    const thumbs = FACE_STEPS.filter(item => savedAngles[item.id]).map(item =>
      `<img src="${savedAngles[item.id]}" alt="${item.label}" title="${item.label}">`
    );
    row.innerHTML = thumbs.join('');
  }
}

function goToAngle(index) {
  currentAngleIndex = index;
  const canvas = document.getElementById('enrollment-captured-preview');
  const video = document.getElementById('enrollment-webcam-preview');
  if (canvas) canvas.style.display = 'none';
  if (video && enrollmentWebcamStream) video.style.display = 'block';
  renderAngleSteps();
}

function advanceAngle() {
  const nextMissing = FACE_STEPS.findIndex((step, index) => index > currentAngleIndex && step.required && !savedAngles[step.id]);
  if (nextMissing >= 0) {
    goToAngle(nextMissing);
    return;
  }
  const anyMissing = FACE_STEPS.findIndex(step => step.required && !savedAngles[step.id]);
  if (anyMissing >= 0) {
    goToAngle(anyMissing);
    return;
  }
  if (currentAngleIndex < FACE_STEPS.length - 1) goToAngle(currentAngleIndex + 1);
  else renderAngleSteps();
}

function skipCurrentAngle() {
  if (FACE_STEPS[currentAngleIndex].required) return;
  advanceAngle();
}

async function openFaceEnrollmentModal(studentId, studentName, isRegistered) {
  currentEnrollStudentId = studentId;
  uploadedPhotoBase64 = null;
  currentAngleIndex = 0;
  savedAngles = {};

  document.getElementById('enroll-student-name').textContent = studentName;
  const removeBtn = document.getElementById('btn-remove-face-data');
  if (removeBtn) removeBtn.style.display = isRegistered ? 'inline-flex' : 'none';

  const fileInput = document.getElementById('enroll-file-input');
  if (fileInput) fileInput.value = '';
  const uploadEmptyState = document.getElementById('upload-empty-state');
  const uploadPreviewState = document.getElementById('upload-preview-state');
  const btnSubmitUpload = document.getElementById('btn-submit-upload');
  if (uploadEmptyState) uploadEmptyState.style.display = 'block';
  if (uploadPreviewState) uploadPreviewState.style.display = 'none';
  if (btnSubmitUpload) btnSubmitUpload.disabled = true;

  setupUploadDropzone();
  renderAngleSteps();
  showCameraPanel('permission');

  document.getElementById('face-enrollment-modal')?.classList.add('active');
  switchEnrollTab('webcam');

  try {
    const res = await fetch(`/api/students/${studentId}/faces`);
    const data = await res.json();
    if (data.success && Array.isArray(data.angles)) {
      data.angles.forEach(item => {
        if (item.photo_url) savedAngles[item.angle] = item.photo_url + '?t=' + Date.now();
      });
      const firstMissing = FACE_STEPS.findIndex(step => step.required && !savedAngles[step.id]);
      currentAngleIndex = firstMissing >= 0 ? firstMissing : 0;
      renderAngleSteps();
    }
  } catch (err) {
    console.warn('Could not load saved face photos', err);
  }
}

function showCameraPanel(which) {
  const permission = document.getElementById('camera-permission-overlay');
  const loading = document.getElementById('camera-loading-overlay');
  const error = document.getElementById('camera-error-overlay');
  [permission, loading, error].forEach(el => el?.classList.add('is-hidden'));
  if (which === 'permission') permission?.classList.remove('is-hidden');
  if (which === 'loading') loading?.classList.remove('is-hidden');
  if (which === 'error') error?.classList.remove('is-hidden');
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
    stopEnrollmentWebcam();
    showCameraPanel('permission');
  }
}

async function openEnrollmentCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    const error = new Error('Open the app at http://127.0.0.1:5000 so the browser can use the camera.');
    error.name = 'SecurityError';
    throw error;
  }

  const attempts = [
    { video: { facingMode: 'user' }, audio: false },
    { video: true, audio: false }
  ];

  let lastError = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      lastError = err;
      if (err && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')) break;
    }
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter(device => device.kind === 'videoinput' && device.deviceId);
    for (const camera of cameras) {
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: camera.deviceId } },
          audio: false
        });
      } catch (err) {
        lastError = err;
      }
    }
  } catch (err) {
    lastError = lastError || err;
  }

  throw lastError || new Error('No camera found');
}

async function startEnrollmentWebcam() {
  const video = document.getElementById('enrollment-webcam-preview');
  const canvas = document.getElementById('enrollment-captured-preview');
  const errorMsg = document.getElementById('camera-error-message');

  showCameraPanel('loading');
  if (video) video.style.display = 'block';
  if (canvas) canvas.style.display = 'none';
  stopEnrollmentWebcam();

  try {
    const stream = await openEnrollmentCamera();
    enrollmentWebcamStream = stream;
    if (video) {
      video.srcObject = stream;
      await video.play();
    }
    showCameraPanel(null);
  } catch (err) {
    console.error('Camera access error:', err);
    showCameraPanel('error');
    if (errorMsg) {
      if (!window.isSecureContext) {
        errorMsg.textContent = 'The camera only works at http://127.0.0.1:5000. Close this tab and open that address.';
      } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        errorMsg.textContent = 'Camera permission was blocked. Click the camera icon in the address bar, choose Allow, then press Try camera again.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        errorMsg.textContent = 'Another app is using the camera. Close Zoom, Teams, or the camera app, then try again.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        errorMsg.textContent = 'No camera was found. Use Upload photos instead.';
      } else {
        errorMsg.textContent = err.message || 'The camera could not start. Use Upload photos instead.';
      }
    }
    showToast('Camera did not start. You can upload photos instead.', 'warning');
  }
}

function stopEnrollmentWebcam() {
  if (enrollmentWebcamStream) {
    enrollmentWebcamStream.getTracks().forEach(track => track.stop());
    enrollmentWebcamStream = null;
  }
  const video = document.getElementById('enrollment-webcam-preview');
  if (video) video.srcObject = null;
}

function closeFaceEnrollmentModal() {
  stopEnrollmentWebcam();
  uploadedPhotoBase64 = null;
  document.getElementById('face-enrollment-modal')?.classList.remove('active');
  fetchStudents(currentPage);
}

function finishFaceEnrollment() {
  if (!requiredAnglesDone()) {
    showToast('Save the front, left, right, up, and down photos first.', 'warning');
    const missing = FACE_STEPS.findIndex(step => step.required && !savedAngles[step.id]);
    if (missing >= 0) goToAngle(missing);
    return;
  }
  showToast('Face photos saved.', 'success');
  closeFaceEnrollmentModal();
}

async function saveFaceImage(imageBase64, angle) {
  const res = await fetch(`/api/students/${currentEnrollStudentId}/register-face`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: imageBase64, angle })
  });
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.message || 'This photo could not be saved.');
  }
  savedAngles[angle] = imageBase64;
  renderAngleSteps();
  return data;
}

function takeSnapshot() {
  const video = document.getElementById('enrollment-webcam-preview');
  const canvas = document.getElementById('enrollment-captured-preview');
  if (!video || !enrollmentWebcamStream || video.videoWidth === 0 || video.readyState < 2) {
    showToast('Camera is not ready. Click Allow camera first.', 'warning');
    showCameraPanel('permission');
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  ctx.restore();

  const image = canvas.toDataURL('image/jpeg', 0.92);
  const angle = FACE_STEPS[currentAngleIndex].id;
  const button = document.getElementById('btn-capture-face');
  button.disabled = true;
  button.textContent = 'Saving...';

  saveFaceImage(image, angle)
    .then(data => {
      showToast(data.message, 'success');
      advanceAngle();
    })
    .catch(err => {
      showToast(err.message || 'Could not save this photo.', 'danger');
    })
    .finally(() => {
      button.disabled = false;
      button.textContent = 'Save this photo';
    });
}

function handlePhotoFileSelected(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    showToast('Choose a JPG, PNG, or WEBP photo.', 'warning');
    return;
  }

  const reader = new FileReader();
  reader.onload = function (evt) {
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
    const file = e.dataTransfer?.files?.[0];
    if (file) handlePhotoFileSelected({ target: { files: [file] } });
  });
}

async function submitUploadedPhoto() {
  if (!uploadedPhotoBase64 || !currentEnrollStudentId) {
    showToast('Choose a photo first.', 'warning');
    return;
  }
  const angle = document.getElementById('upload-angle-select')?.value || FACE_STEPS[currentAngleIndex].id;
  const button = document.getElementById('btn-submit-upload');
  button.disabled = true;
  button.textContent = 'Saving...';
  try {
    const data = await saveFaceImage(uploadedPhotoBase64, angle);
    showToast(data.message, 'success');
    const stepIndex = FACE_STEPS.findIndex(step => step.id === angle);
    if (stepIndex >= 0) currentAngleIndex = stepIndex;
    advanceAngle();
    uploadedPhotoBase64 = null;
    document.getElementById('upload-empty-state').style.display = 'block';
    document.getElementById('upload-preview-state').style.display = 'none';
    document.getElementById('enroll-file-input').value = '';
  } catch (err) {
    showToast(err.message || 'Could not save this photo.', 'danger');
    button.disabled = false;
  } finally {
    button.textContent = 'Save uploaded photo';
  }
}

async function removeFaceData() {
  if (!currentEnrollStudentId) return;
  confirmDialog('Remove face photos', 'Delete every saved photo for this student? The camera will no longer recognize them.', 'Remove photos', async () => {
    try {
      const res = await fetch(`/api/students/${currentEnrollStudentId}/face`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeFaceEnrollmentModal();
      }
    } catch (e) {
      showToast('Could not remove the photos.', 'danger');
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
