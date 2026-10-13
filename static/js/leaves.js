document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-status]').forEach(btn => {
    btn.onclick = () => loadLeaves(btn.dataset.status);
  });
  loadLeaves('pending');
});

async function loadLeaves(status) {
  const res = await fetch(`/api/leaves${status ? `?status=${status}` : ''}`);
  const data = await res.json();
  const box = document.getElementById('leave-list');
  box.innerHTML = (data.applications || []).map(item => `
    <article class="card" id="leave-${item.id}">
      <div class="card-header">
        <div>
          <h3 class="card-title">${item.full_name}</h3>
          <small>${item.roll_number} · ${item.class_section} · ${item.start_date} to ${item.end_date}</small>
        </div>
        <span class="badge">${item.status}</span>
      </div>
      <p>${item.reason}</p>
      ${item.attachment_path ? `<p><a href="${item.attachment_path}" target="_blank">Supporting document</a></p>` : ''}
      ${item.teacher_comment ? `<p><strong>Comment:</strong> ${item.teacher_comment}</p>` : ''}
      <div id="context-${item.id}"></div>
      ${item.status === 'pending' ? `
        <div class="ops-form">
          <textarea id="comment-${item.id}" placeholder="Decision comment"></textarea>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-primary btn-sm" type="button" onclick="decide(${item.id}, 'approved')">Approve</button>
            <button class="btn btn-secondary btn-sm" type="button" onclick="decide(${item.id}, 'rejected')">Reject</button>
            <button class="btn btn-secondary btn-sm" type="button" onclick="showContext(${item.id})">Attendance context</button>
          </div>
        </div>` : ''}
    </article>
  `).join('') || '<p>No applications in this list.</p>';
}

async function showContext(id) {
  const res = await fetch(`/api/leaves/${id}/context`);
  const data = await res.json();
  const policy = data.policy || {};
  document.getElementById(`context-${id}`).innerHTML = `
    <p>Attendance used for context: ${policy.percentage === null ? 'not enough decided sessions' : policy.percentage + '%'} (${policy.attended || 0} attended of ${policy.counted_sessions || 0} counted). Approved leave is excluded.</p>
  `;
}

async function decide(id, status) {
  const res = await fetch(`/api/leaves/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, comment: document.getElementById(`comment-${id}`).value })
  });
  const data = await res.json();
  showToast(data.message || 'Updated', data.success ? 'success' : 'danger');
  if (data.success) loadLeaves('pending');
}
