/**
 * AutoAttend Core Application Utilities
 * Modern 2026 SaaS Dashboard Engine
 */

// Initialize Toast System
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  // Icon based on type
  let iconSvg = '';
  if (type === 'success') {
    iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
  } else if (type === 'danger') {
    iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
  } else if (type === 'warning') {
    iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
  } else {
    iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4F46E5" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
  }

  toast.innerHTML = `${iconSvg} <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Confirmation Dialog Utility
function confirmDialog(title, message, confirmBtnText = 'Confirm', onConfirm) {
  let modal = document.getElementById('global-confirm-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'global-confirm-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3 id="confirm-title" class="card-title">Confirm Action</h3>
          <button class="btn btn-icon btn-secondary" onclick="closeConfirmModal()">✕</button>
        </div>
        <div class="modal-body">
          <p id="confirm-message" style="color: var(--text-muted);"></p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="closeConfirmModal()">Cancel</button>
          <button id="confirm-action-btn" class="btn btn-danger">Confirm</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-message').textContent = message;
  const btn = document.getElementById('confirm-action-btn');
  btn.textContent = confirmBtnText;

  // Replace event listener
  const newBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(newBtn, btn);
  newBtn.addEventListener('click', () => {
    closeConfirmModal();
    if (typeof onConfirm === 'function') onConfirm();
  });

  modal.classList.add('active');
}

function closeConfirmModal() {
  const modal = document.getElementById('global-confirm-modal');
  if (modal) modal.classList.remove('active');
}

// Sidebar Collapse / Expand
document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      sidebar.classList.toggle('mobile-open');
    });
  }

  // Set current date in navbar if present
  const dateEl = document.getElementById('current-date-display');
  if (dateEl) {
    const options = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };
    dateEl.textContent = new Date().toLocaleDateString('en-US', options);
  }

  // Load User details in topbar
  fetch('/api/auth/me')
    .then(r => r.json())
    .then(data => {
      if (data.authenticated && data.user) {
        const nameEl = document.getElementById('topbar-user-name');
        const roleEl = document.getElementById('topbar-user-role');
        const avatarEl = document.getElementById('topbar-user-avatar');
        if (nameEl) nameEl.textContent = data.user.name;
        if (roleEl) roleEl.textContent = data.user.role === 'admin' ? 'Faculty Admin' : 'Teacher';
        if (avatarEl && data.user.avatar) avatarEl.src = data.user.avatar;
      }
    })
    .catch(() => {});
});

// Logout handler
async function handleLogout() {
  confirmDialog('Log Out', 'Are you sure you want to log out of AutoAttend?', 'Log Out', async () => {
    try {
      const res = await fetch('/api/auth/logout', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        window.location.href = '/login';
      }
    } catch (e) {
      window.location.href = '/login';
    }
  });
}
