let slots = [];
let queue = 'waiting';
let records = [];

document.addEventListener('DOMContentLoaded', async () => {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('checkin-date').value = today;

  const res = await fetch('/api/meta/options');
  const data = await res.json();
  slots = data.lecture_slots || [];
  fillSelect('slot-id', slots.map(s => `<option value="${s.id}">${esc(s.class_section)} · ${esc(s.title)}</option>`));
  fillSelect('checkin-student', (data.students || []).map(s => `<option value="${s.id}">${esc(s.full_name)} · ${esc(s.roll_number)}</option>`));
  fillSelect('checkin-subject', (data.subjects || []).map(s => `<option value="${s.id}">${esc(s.subject_name || s.subject_code)}</option>`));
  document.getElementById('filter-class').insertAdjacentHTML('beforeend', (data.class_sections || []).map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join(''));
  document.getElementById('filter-subject').insertAdjacentHTML('beforeend', (data.subjects || []).map(s => `<option value="${s.id}">${esc(s.subject_name || s.subject_code)}</option>`).join(''));

  applySlot();
  document.getElementById('slot-id').onchange = applySlot;
  document.getElementById('slot-form').onsubmit = saveSlot;
  document.getElementById('checkin-form').onsubmit = checkIn;
  document.getElementById('open-add').onclick = () => {
    const panel = document.getElementById('add-panel');
    panel.hidden = !panel.hidden;
    if (!panel.hidden) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  document.querySelectorAll('.stat-chip').forEach(chip => {
    chip.onclick = () => {
      queue = chip.dataset.queue;
      document.querySelectorAll('.stat-chip').forEach(item => item.classList.toggle('is-active', item === chip));
      render();
    };
  });
  ['filter-date', 'filter-class', 'filter-subject'].forEach(id => {
    document.getElementById(id).onchange = loadLate;
  });
  document.getElementById('clear-date').onclick = () => {
    document.getElementById('filter-date').value = '';
    loadLate();
  };
  loadLate();
});

function fillSelect(id, html) {
  document.getElementById(id).innerHTML = html.join('');
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function applySlot() {
  const slot = slots.find(item => String(item.id) === document.getElementById('slot-id').value);
  if (!slot) return;
  document.getElementById('slot-start').value = (slot.start_time || '').slice(0, 5);
  document.getElementById('slot-grace').value = slot.grace_minutes;
}

async function saveSlot(event) {
  event.preventDefault();
  const id = document.getElementById('slot-id').value;
  const res = await fetch(`/api/lecture-slots/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      start_time: document.getElementById('slot-start').value,
      grace_minutes: document.getElementById('slot-grace').value
    })
  });
  const data = await res.json();
  showToast(data.success ? 'Class timing saved' : (data.message || 'Could not save'), data.success ? 'success' : 'danger');
}

async function checkIn(event) {
  event.preventDefault();
  const res = await fetch('/api/late/checkin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      student_id: document.getElementById('checkin-student').value,
      subject_id: document.getElementById('checkin-subject').value,
      attendance_date: document.getElementById('checkin-date').value,
      arrival_time: document.getElementById('checkin-arrival').value
    })
  });
  const data = await res.json();
  showToast(data.message || (data.late ? 'Student flagged as late' : 'Not flagged'), data.success ? 'success' : 'danger');
  if (data.success && data.late) {
    queue = 'waiting';
    document.querySelectorAll('.stat-chip').forEach(item => item.classList.toggle('is-active', item.dataset.queue === 'waiting'));
    loadLate();
  }
}

async function loadLate() {
  const params = new URLSearchParams({ queue: 'all' });
  const date = document.getElementById('filter-date').value;
  if (date) params.set('date', date);
  const classSection = document.getElementById('filter-class').value;
  const subject = document.getElementById('filter-subject').value;
  if (classSection) params.set('class_section', classSection);
  if (subject) params.set('subject_id', subject);
  const res = await fetch(`/api/late?${params}`);
  const data = await res.json();
  records = data.records || [];
  document.getElementById('count-waiting').textContent = records.filter(isWaiting).length;
  document.getElementById('count-done').textContent = records.filter(row => !isWaiting(row)).length;
  render();
}

function isWaiting(row) {
  return !row.review_status || row.review_status === 'pending';
}

function render() {
  const list = document.getElementById('late-list');
  const shown = records.filter(row => queue === 'done' ? !isWaiting(row) : isWaiting(row));
  if (!shown.length) {
    list.innerHTML = `
      <div class="late-empty">
        <h2>${queue === 'waiting' ? 'No late students waiting' : 'No decisions yet'}</h2>
        <p>${queue === 'waiting' ? 'When a student arrives after the grace time, they show up here with a flag.' : 'Decisions you make will stay in this list.'}</p>
      </div>`;
    return;
  }
  list.innerHTML = shown.map(cardHtml).join('');
}

function cardHtml(row) {
  const waiting = isWaiting(row);
  const status = statusLabel(row.review_status);
  const when = formatWhen(row.arrival_time);
  return `
    <article class="late-card ${waiting ? 'is-flagged' : 'is-done'}">
      <div class="late-card-top">
        ${waiting ? '<span class="flag">Flagged</span>' : `<span class="decision decision-${esc(row.review_status)}">${esc(status)}</span>`}
        <span class="late-minutes">${esc(lateLabel(row.minutes_late))}</span>
      </div>
      <h2>${esc(row.full_name)}</h2>
      <p class="late-meta">${esc(row.roll_number)} · ${esc(row.class_section)} · ${esc(row.subject_name || row.subject_code)}</p>
      <p class="late-time">Arrived ${esc(when)} · class started ${esc(String(row.lecture_start || '').slice(0, 5))} · grace ${row.grace_minutes} min</p>
      ${waiting ? actions(row.id) : `<p class="late-note">Saved as ${esc(status)}. ${esc(row.decision_note || '')}</p>${actions(row.id, true)}`}
    </article>`;
}

function actions(id, compact) {
  const size = compact ? ' btn-sm' : '';
  return `
    <div class="late-actions">
      <button class="btn btn-present${size}" type="button" onclick="decideLate(${id}, 'present')">Present</button>
      <button class="btn btn-absent${size}" type="button" onclick="decideLate(${id}, 'absent')">Absent</button>
      <button class="btn btn-leave${size}" type="button" onclick="decideLate(${id}, 'leave')">Leave</button>
    </div>`;
}

function statusLabel(status) {
  if (status === 'present') return 'Present';
  if (status === 'absent') return 'Absent';
  if (status === 'approved_leave') return 'Leave';
  return 'Waiting';
}

function lateLabel(minutes) {
  const value = Number(minutes) || 0;
  if (value < 60) return `${value} min late`;
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  return rest ? `${hours} hr ${rest} min late` : `${hours} hr late`;
}

function formatWhen(value) {
  if (!value) return 'unknown time';
  const text = String(value).replace('T', ' ');
  return text.length > 16 ? text.slice(0, 16) : text;
}

async function decideLate(id, status) {
  const words = { present: 'present', absent: 'absent', leave: 'on leave' };
  const row = records.find(item => item.id === id);
  const name = row ? row.full_name : 'this student';
  confirmDialog('Save attendance', `Mark ${name} as ${words[status]}?`, 'Save', async () => {
    const res = await fetch(`/api/late/${id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const data = await res.json();
    showToast(data.message || 'Saved', data.success ? 'success' : 'danger');
    if (data.success) loadLate();
  });
}
