let slots = [];

document.addEventListener('DOMContentLoaded', async () => {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('checkin-date').value = today;
  document.getElementById('filter-date').value = today;
  const res = await fetch('/api/meta/options');
  const data = await res.json();
  slots = data.lecture_slots || [];
  document.getElementById('slot-id').innerHTML = slots.map(s => `<option value="${s.id}">${s.class_section} · ${s.title}</option>`).join('');
  document.getElementById('checkin-student').innerHTML = data.students.map(s => `<option value="${s.id}">${s.full_name} · ${s.roll_number}</option>`).join('');
  document.getElementById('checkin-subject').innerHTML = data.subjects.map(s => `<option value="${s.id}">${s.subject_code}</option>`).join('');
  document.getElementById('filter-class').innerHTML += data.class_sections.map(c => `<option value="${c}">${c}</option>`).join('');
  document.getElementById('filter-subject').innerHTML += data.subjects.map(s => `<option value="${s.id}">${s.subject_code}</option>`).join('');
  document.getElementById('filter-student').innerHTML += data.students.map(s => `<option value="${s.id}">${s.full_name}</option>`).join('');
  applySlot();
  document.getElementById('slot-id').onchange = applySlot;
  document.getElementById('slot-form').onsubmit = saveSlot;
  document.getElementById('checkin-form').onsubmit = checkIn;
  document.getElementById('filter-btn').onclick = () => loadLate();
  document.getElementById('daily-report').onclick = (e) => { e.preventDefault(); document.getElementById('filter-month').value = ''; loadLate(); };
  document.getElementById('monthly-report').onclick = (e) => {
    e.preventDefault();
    document.getElementById('filter-date').value = '';
    if (!document.getElementById('filter-month').value) document.getElementById('filter-month').value = today.slice(0, 7);
    loadLate();
  };
  loadLate();
});

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
  showToast(data.success ? 'Lecture timing saved' : (data.message || 'Could not save'), data.success ? 'success' : 'danger');
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
  showToast(data.message || (data.late ? `${data.minutes_late} minutes late` : 'Recorded'), data.success ? 'success' : 'danger');
  if (data.success) loadLate();
}

async function loadLate() {
  const params = new URLSearchParams();
  const date = document.getElementById('filter-date').value;
  const month = document.getElementById('filter-month').value;
  if (date) params.set('date', date);
  if (month) params.set('month', month);
  ['class', 'subject', 'student'].forEach(key => {
    const value = document.getElementById(`filter-${key}`).value;
    if (value) params.set(key === 'class' ? 'class_section' : key === 'subject' ? 'subject_id' : 'student_id', value);
  });
  const res = await fetch(`/api/late?${params}`);
  const data = await res.json();
  document.getElementById('late-body').innerHTML = (data.records || []).map(row => `
    <tr>
      <td>${row.full_name}<br><small>${row.roll_number}</small></td>
      <td>${row.class_section}</td>
      <td>${row.subject_code}</td>
      <td>${row.arrival_time}</td>
      <td>${row.minutes_late}</td>
      <td>
        <input type="datetime-local" id="fix-${row.id}">
        <input placeholder="Why this change" id="note-${row.id}">
        <button class="btn btn-sm btn-secondary" type="button" onclick="correctLate(${row.id})">Save</button>
        <small>${row.correction_note || ''}</small>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="6">No late arrivals for this filter.</td></tr>';
}

async function correctLate(id) {
  const res = await fetch(`/api/late/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arrival_time: document.getElementById(`fix-${id}`).value, note: document.getElementById(`note-${id}`).value })
  });
  const data = await res.json();
  showToast(data.message || 'Updated', data.success ? 'success' : 'danger');
  if (data.success) loadLate();
}
