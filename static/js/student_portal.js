document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('leave-form').onsubmit = submitLeave;
  document.getElementById('mark-read').onclick = markRead;
  refresh();
});

async function refresh() {
  const [leaves, notes] = await Promise.all([
    fetch('/api/leaves').then(r => r.json()),
    fetch('/api/notifications').then(r => r.json())
  ]);
  document.getElementById('my-leaves').innerHTML = (leaves.applications || []).map(item => `
    <div class="lecture-row">
      <div><strong>${item.start_date} to ${item.end_date}</strong><div>${item.reason}</div>${item.teacher_comment ? `<div>Teacher: ${item.teacher_comment}</div>` : ''}</div>
      <span class="badge">${item.status}</span>
    </div>
  `).join('') || '<p>You have not applied yet.</p>';
  document.getElementById('note-list').innerHTML = (notes.notifications || []).map(note => `
    <div class="lecture-row"><div><strong>${note.title}</strong><div>${note.body}</div></div></div>
  `).join('') || '<p>No notifications yet.</p>';
  const mine = await fetch('/api/me/attendance').then(r => r.json());
  const box = document.getElementById('my-attendance');
  if (mine.success) {
    const rate = mine.percentage === null ? 'No decided sessions yet' : `${mine.percentage}%`;
    box.textContent = `${rate}. Attended ${mine.attended} of ${mine.counted_sessions} counted sessions. Approved leave is excluded and is not counted as Present.`;
  }
}

async function submitLeave(event) {
  event.preventDefault();
  const res = await fetch('/api/leaves', { method: 'POST', body: new FormData(event.target) });
  const data = await res.json();
  showToast(data.message || 'Submitted', data.success ? 'success' : 'danger');
  if (data.success) {
    event.target.reset();
    refresh();
  }
}

async function markRead() {
  await fetch('/api/notifications/read', { method: 'POST' });
  refresh();
}
