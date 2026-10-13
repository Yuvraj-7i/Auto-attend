/**
 * AutoAttend Attendance Records & Audit Management
 */

let currentRecordsPage = 1;
let totalRecordsPages = 1;
let currentEditRecordId = null;

document.addEventListener('DOMContentLoaded', () => {
  loadFilterDropdowns();
  fetchAttendanceRecords(1);
  setupFilterListeners();
});

async function loadFilterDropdowns() {
  try {
    const [roomsRes, subsRes] = await Promise.all([
      fetch('/api/classrooms'),
      fetch('/api/subjects')
    ]);
    const rooms = await roomsRes.json();
    const subs = await subsRes.json();

    const roomSelect = document.getElementById('filter-record-classroom');
    const subSelect = document.getElementById('filter-record-subject');

    if (roomSelect && rooms.classrooms) {
      roomSelect.innerHTML = '<option value="">All Classrooms</option>' +
        rooms.classrooms.map(r => `<option value="${r.id}">${r.room_number}</option>`).join('');
    }

    if (subSelect && subs.subjects) {
      subSelect.innerHTML = '<option value="">All Subjects</option>' +
        subs.subjects.map(s => `<option value="${s.id}">${s.subject_code} - ${s.subject_name}</option>`).join('');
    }
  } catch (e) {}
}

function setupFilterListeners() {
  const searchInput = document.getElementById('record-search-input');
  const statusFilter = document.getElementById('filter-record-status');
  const classroomFilter = document.getElementById('filter-record-classroom');
  const subjectFilter = document.getElementById('filter-record-subject');
  const startDate = document.getElementById('filter-start-date');
  const endDate = document.getElementById('filter-end-date');

  let debounceTimer;
  searchInput?.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      fetchAttendanceRecords(1);
    }, 300);
  });

  [statusFilter, classroomFilter, subjectFilter, startDate, endDate].forEach(el => {
    el?.addEventListener('change', () => fetchAttendanceRecords(1));
  });

  document.getElementById('btn-export-csv')?.addEventListener('click', () => {
    exportCSV();
  });

  document.getElementById('btn-print-report')?.addEventListener('click', () => {
    window.print();
  });
}

async function fetchAttendanceRecords(page = 1) {
  currentRecordsPage = page;
  const search = document.getElementById('record-search-input')?.value.trim() || '';
  const status = document.getElementById('filter-record-status')?.value || '';
  const classroom = document.getElementById('filter-record-classroom')?.value || '';
  const subject = document.getElementById('filter-record-subject')?.value || '';
  const startDate = document.getElementById('filter-start-date')?.value || '';
  const endDate = document.getElementById('filter-end-date')?.value || '';

  const params = new URLSearchParams({
    page: page,
    per_page: 15,
    search: search,
    status: status,
    classroom_id: classroom,
    subject_id: subject,
    start_date: startDate,
    end_date: endDate
  });

  try {
    const res = await fetch(`/api/attendance/records?${params.toString()}`);
    const data = await res.json();
    if (data.success) {
      totalRecordsPages = data.total_pages;
      renderRecordsTable(data.records);
      renderRecordsPagination(data.total, data.page, data.total_pages);
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to load attendance records', 'danger');
  }
}

function renderRecordsTable(records) {
  const tbody = document.getElementById('attendance-records-tbody');
  if (!tbody) return;

  if (records.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="empty-state">
            <h4 class="empty-state-title">No Records Found</h4>
            <p class="empty-state-desc">Try clearing filter conditions or check other dates.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = records.map(r => {
    let badgeClass = 'badge-present';
    if (r.status === 'absent') badgeClass = 'badge-absent';
    else if (r.status === 'late') badgeClass = 'badge-late';

    const confPct = Math.round((r.confidence_score || 0) * 100);
    const timeFormatted = r.timestamp ? new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--';

    return `
      <tr>
        <td>
          <div style="font-weight:700; color:var(--text-heading);">${r.session_date}</div>
          <small>${timeFormatted}</small>
        </td>
        <td>
          <div style="display:flex; align-items:center; gap:0.625rem;">
            <img src="${r.avatar_url || '/static/images/avatars/default_avatar.png'}" style="width:32px; height:32px; border-radius:50%; object-fit:cover;" onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <div style="font-weight:700; color:var(--text-heading);">${r.full_name}</div>
              <small><code>${r.roll_number}</code> • ${r.class_section}</small>
            </div>
          </div>
        </td>
        <td>
          <div style="font-weight:600;">${r.subject_code}</div>
          <small style="color:var(--text-muted);">${r.room_number}</small>
        </td>
        <td><span class="badge ${badgeClass}">${r.status.toUpperCase()}</span></td>
        <td>
          ${r.verification_method === 'ai_face_recognition'
            ? `<span class="badge badge-ai">AI Match (${confPct}%)</span>`
            : `<span class="badge" style="background:#F1F5F9; color:var(--text-muted);">Manual Override</span>`}
        </td>
        <td>${r.repeated_observations || 0}</td>
        <td>
          ${r.is_manually_edited
            ? `<span title="${r.audit_note || ''}" style="color:var(--warning); font-size:0.8125rem; font-weight:600; cursor:help;">Edited (${r.edited_by_name || 'Teacher'})</span>`
            : `<span style="color:var(--text-muted); font-size:0.8125rem;">Direct AI</span>`}
        </td>
        <td class="no-print">
          <button class="btn btn-sm btn-secondary" onclick="openManualEditModal(${r.id}, '${r.status}', '${r.full_name}')">Correct</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderRecordsPagination(total, page, pages) {
  const container = document.getElementById('records-pagination-container');
  if (!container) return;

  container.innerHTML = `
    <span style="font-size:0.875rem; color:var(--text-muted);">Showing <b>${page}</b> of <b>${pages}</b> (${total} total records)</span>
    <div style="display:flex; gap:0.5rem;">
      <button class="pagination-btn" ${page <= 1 ? 'disabled' : ''} onclick="fetchAttendanceRecords(${page - 1})">Previous</button>
      <button class="pagination-btn" ${page >= pages ? 'disabled' : ''} onclick="fetchAttendanceRecords(${page + 1})">Next</button>
    </div>
  `;
}

// Teacher Manual Override Modal
function openManualEditModal(recordId, currentStatus, studentName) {
  currentEditRecordId = recordId;
  document.getElementById('edit-modal-student-name').textContent = studentName;
  document.getElementById('edit-status-select').value = currentStatus;
  document.getElementById('edit-audit-note').value = '';
  document.getElementById('manual-edit-modal')?.classList.add('active');
}

function closeManualEditModal() {
  document.getElementById('manual-edit-modal')?.classList.remove('active');
}

async function handleManualEditSubmit(e) {
  e.preventDefault();
  if (!currentEditRecordId) return;

  const newStatus = document.getElementById('edit-status-select').value;
  const auditNote = document.getElementById('edit-audit-note').value.trim();

  if (!auditNote) {
    showToast('Please provide an audit note/reason for correcting attendance.', 'warning');
    return;
  }

  try {
    const res = await fetch(`/api/attendance/records/${currentEditRecordId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, audit_note: auditNote })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      closeManualEditModal();
      fetchAttendanceRecords(currentRecordsPage);
    } else {
      showToast(data.message || 'Error updating record', 'danger');
    }
  } catch (err) {
    showToast('Network error updating attendance', 'danger');
  }
}

function exportCSV() {
  const classroom = document.getElementById('filter-record-classroom')?.value || '';
  const subject = document.getElementById('filter-record-subject')?.value || '';
  const status = document.getElementById('filter-record-status')?.value || '';
  const startDate = document.getElementById('filter-start-date')?.value || '';
  const endDate = document.getElementById('filter-end-date')?.value || '';

  const params = new URLSearchParams({
    classroom_id: classroom,
    subject_id: subject,
    status: status,
    start_date: startDate,
    end_date: endDate
  });

  window.location.href = `/api/reports/export?${params.toString()}`;
}
