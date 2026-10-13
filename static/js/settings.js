/**
 * AutoAttend System Settings & Configuration Script
 */

document.addEventListener('DOMContentLoaded', () => {
  loadSystemSettings();
  setupSettingsFormListeners();
});

async function loadSystemSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.success && data.settings) {
      const s = data.settings;
      const threshInput = document.getElementById('setting-threshold');
      const threshDisplay = document.getElementById('threshold-val-display');
      const obsInput = document.getElementById('setting-min-obs');
      const intervalInput = document.getElementById('setting-interval');
      const camInput = document.getElementById('setting-cam-source');

      if (threshInput && s.face_match_threshold) {
        threshInput.value = s.face_match_threshold;
        if (threshDisplay) threshDisplay.textContent = `${Math.round(parseFloat(s.face_match_threshold) * 100)}%`;
      }
      if (obsInput && s.min_observations) obsInput.value = s.min_observations;
      if (intervalInput && s.frame_capture_interval) intervalInput.value = s.frame_capture_interval;
      if (camInput && s.camera_source) camInput.value = s.camera_source;
    }
  } catch (e) {
    console.error('Settings load error:', e);
  }
}

function setupSettingsFormListeners() {
  const threshInput = document.getElementById('setting-threshold');
  const threshDisplay = document.getElementById('threshold-val-display');

  threshInput?.addEventListener('input', (e) => {
    if (threshDisplay) threshDisplay.textContent = `${Math.round(parseFloat(e.target.value) * 100)}%`;
  });

  // Save AI Settings
  document.getElementById('ai-settings-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      face_match_threshold: document.getElementById('setting-threshold').value,
      min_observations: document.getElementById('setting-min-obs').value,
      frame_capture_interval: document.getElementById('setting-interval').value,
      camera_source: document.getElementById('setting-cam-source').value
    };

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        showToast('AI and Camera settings saved successfully!', 'success');
      } else {
        showToast('Error saving settings', 'danger');
      }
    } catch (err) {
      showToast('Network error saving settings', 'danger');
    }
  });

  // Change Password Form
  document.getElementById('password-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const currPw = document.getElementById('curr-password').value;
    const newPw = document.getElementById('new-password').value;
    const confirmPw = document.getElementById('confirm-password').value;

    if (newPw !== confirmPw) {
      showToast('New passwords do not match.', 'warning');
      return;
    }

    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currPw, new_password: newPw })
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        document.getElementById('password-form').reset();
      } else {
        showToast(data.message || 'Password update failed', 'danger');
      }
    } catch (err) {
      showToast('Network error changing password', 'danger');
    }
  });
}
