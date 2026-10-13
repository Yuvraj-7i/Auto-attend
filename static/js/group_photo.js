let selectedFile = null;
let currentBatch = null;
const statuses = [
  ['present', 'Present'],
  ['late', 'Late'],
  ['absent', 'Absent'],
  ['needs_review', 'Needs Review'],
  ['approved_leave', 'Approved Leave'],
  ['unmarked', 'Not marked']
];

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('attendance-date').value = new Date().toISOString().slice(0, 10);
  await loadOptions();
  bindUpload();
  document.getElementById('detect-btn').addEventListener('click', analyzePhoto);
  document.getElementById('confirm-btn').addEventListener('click', confirmAttendance);
  loadHistory();
});

async function loadOptions() {
  const res = await fetch('/api/meta/options');
  const data = await res.json();
  const params = new URLSearchParams(location.search);
  fillSelect('class-section', data.class_sections.map(v => ({ id: v, label: v })), params.get('class'));
  fillSelect('subject-id', data.subjects.map(s => ({ id: s.id, label: `${s.subject_code} — ${s.subject_name}` })), params.get('subject'));
  fillSelect('lecture-slot', data.lecture_slots.map(s => ({
    id: s.id,
    label: `${(s.start_time || '').slice(0, 5)} · ${s.class_section} · ${s.title}`
  })), params.get('slot'));
}

function fillSelect(id, items, selected) {
  const el = document.getElementById(id);
  el.innerHTML = items.map(item => `<option value="${item.id}">${item.label}</option>`).join('');
  if (selected) el.value = selected;
}

function bindUpload() {
  const zone = document.getElementById('dropzone');
  const gallery = document.getElementById('gallery-input');
  const camera = document.getElementById('camera-input');
  document.getElementById('gallery-btn').onclick = () => gallery.click();
  document.getElementById('camera-btn').onclick = () => camera.click();
  gallery.onchange = () => takeFile(gallery.files[0]);
  camera.onchange = () => takeFile(camera.files[0]);
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    takeFile(e.dataTransfer.files[0]);
  });
}

function takeFile(file) {
  const error = document.getElementById('upload-error');
  error.textContent = '';
  if (!file) return;
  const ok = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp'];
  if (file.type && !ok.includes(file.type)) {
    error.textContent = 'Use a JPG, JPEG, PNG, WEBP, or BMP image.';
    return;
  }
  selectedFile = file;
  const img = document.getElementById('preview-image');
  img.src = URL.createObjectURL(file);
  img.style.display = 'block';
  document.getElementById('preview-empty').style.display = 'none';
  document.getElementById('detect-btn').disabled = false;
}

function analyzePhoto() {
  const error = document.getElementById('upload-error');
  error.textContent = '';
  if (!selectedFile) {
    error.textContent = 'Add a class photo first.';
    return;
  }
  const body = new FormData();
  body.append('photo', selectedFile);
  body.append('class_section', document.getElementById('class-section').value);
  body.append('subject_id', document.getElementById('subject-id').value);
  body.append('lecture_slot_id', document.getElementById('lecture-slot').value);
  body.append('attendance_date', document.getElementById('attendance-date').value);
  body.append('observation_time', document.getElementById('observation-time').value);
  const wrap = document.getElementById('progress-wrap');
  const bar = document.getElementById('progress-bar');
  wrap.style.display = 'block';
  bar.style.width = '8%';
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/group-photo/analyze');
  xhr.upload.onprogress = (event) => {
    if (event.lengthComputable) bar.style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
  };
  xhr.onload = () => {
    wrap.style.display = 'none';
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = { message: 'The server could not read this photo.' }; }
    if (xhr.status >= 400 || !data.success) {
      error.textContent = data.message || 'Face detection failed.';
      return;
    }
    currentBatch = data;
    renderReview(data);
  };
  xhr.onerror = () => {
    wrap.style.display = 'none';
    error.textContent = 'Upload failed. Check the connection and try again.';
  };
  xhr.send(body);
}

function renderReview(data) {
  document.getElementById('review-panel').style.display = 'block';
  const warning = document.getElementById('existing-warning');
  if (data.batch.existing_warning) {
    warning.style.display = 'block';
    warning.textContent = data.batch.existing_warning;
  } else {
    warning.style.display = 'none';
  }
  const summary = data.summary;
  document.getElementById('summary-pills').innerHTML = [
    ['Enrolled', summary.enrolled],
    ['Faces detected', summary.faces_detected],
    ['Matched', summary.matched],
    ['Unmatched', summary.unmatched],
    ['Needs review', summary.needs_review]
  ].map(([label, value]) => `<div class="pill-card"><span>${label}</span><strong>${value}</strong></div>`).join('');
  const annotated = document.getElementById('annotated-image');
  annotated.src = `${data.batch.annotated_path}?t=${Date.now()}`;
  const rows = data.faces.filter(face => face.student_id && face.match_result !== 'duplicate');
  document.getElementById('review-body').innerHTML = rows.map(face => `
    <tr data-face="${face.id}">
      <td>${face.full_name || '—'}</td>
      <td>${face.roll_number || face.enrollment_no || '—'}</td>
      <td>${face.match_result === 'not_in_photo' ? 'Not in photo' : `${Math.round((face.confidence || 0) * 100)}%`}</td>
      <td><select class="status-select">${statuses.map(([value, label]) => `<option value="${value}" ${face.attendance_status === value ? 'selected' : ''}>${label}</option>`).join('')}</select></td>
      <td>${arrivalLabel(face.arrival_status)}</td>
      <td>${face.verification_status === 'verified' ? 'Verified' : 'Pending'}</td>
    </tr>
  `).join('');
  const unmatched = data.faces.filter(face => face.match_result === 'unmatched' || face.match_result === 'duplicate');
  document.getElementById('unmatched-list').innerHTML = unmatched.map(face => `
    <div class="lecture-row"><div><strong>${face.match_result === 'duplicate' ? 'Duplicate detection' : 'Unmatched face'}</strong><div>Confidence ${Math.round((face.confidence || 0) * 100)}%</div></div></div>
  `).join('') || '<p>Every detected face was matched to this class, or no face was found.</p>';
  document.getElementById('review-panel').scrollIntoView({ behavior: 'smooth' });
}

function arrivalLabel(value) {
  const labels = {
    present_at_observation: 'Seen at the observation time',
    present_time_unknown: 'Present — arrival time unknown',
    not_observed: 'Not observed in this photo',
    unknown: 'Unknown',
    teacher_marked_without_timestamp: 'Marked late by teacher, time not recorded'
  };
  return labels[value] || value || 'Unknown';
}

async function confirmAttendance() {
  if (!currentBatch) return;
  const updates = [...document.querySelectorAll('#review-body tr')].map(row => ({
    id: Number(row.dataset.face),
    attendance_status: row.querySelector('select').value
  }));
  const res = await fetch(`/api/group-photo/${currentBatch.batch.id}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates })
  });
  const data = await res.json();
  showToast(data.message || 'Saved', data.success ? 'success' : 'danger');
  if (data.success) loadHistory();
}

async function loadHistory() {
  const res = await fetch('/api/group-photo/history');
  const data = await res.json();
  document.getElementById('photo-history').innerHTML = (data.history || []).map(item => `
    <div class="lecture-row">
      <div><strong>${item.attendance_date} · ${item.class_section}</strong><div>${item.subject_name} · ${item.matched_count}/${item.faces_detected} matched · ${item.status}</div></div>
    </div>
  `).join('') || '<p>No class photos yet.</p>';
}
