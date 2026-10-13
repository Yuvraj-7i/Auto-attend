/**
 * AutoAttend Reports & Institutional Analytics Script
 */

let subjectChart = null;

document.addEventListener('DOMContentLoaded', () => {
  fetchReportsData();
});

async function fetchReportsData() {
  try {
    const res = await fetch('/api/reports/summary');
    const data = await res.json();
    if (data.success) {
      renderSummaryCards(data);
      renderSubjectChart(data.subject_stats);
      renderLowAttendanceList(data.low_attendance_students);
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to load reporting data', 'danger');
  }
}

function renderSummaryCards(data) {
  const totEl = document.getElementById('report-total-students');
  const presEl = document.getElementById('report-present-today');
  const absEl = document.getElementById('report-absent-today');
  const rateEl = document.getElementById('report-overall-rate');

  if (totEl) totEl.textContent = data.total_students || 0;
  if (presEl) presEl.textContent = data.present_today || 0;
  if (absEl) absEl.textContent = data.absent_today || 0;
  if (rateEl) rateEl.textContent = `${data.percentage_today || 0}%`;
}

function renderSubjectChart(subjectStats) {
  const ctx = document.getElementById('subjectAttendanceChart');
  if (!ctx || !subjectStats) return;

  const labels = subjectStats.map(s => s.subject_code);
  const dataVals = subjectStats.map(s => {
    const tot = s.total_records || 0;
    const pres = s.present_count || 0;
    return tot > 0 ? Math.round((pres / tot) * 100) : 0;
  });

  if (subjectChart) subjectChart.destroy();

  subjectChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Attendance Rate (%)',
        data: dataVals,
        backgroundColor: '#4F46E5',
        borderRadius: 8,
        barThickness: 28
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { callback: v => `${v}%` }
        },
        x: {
          grid: { display: false }
        }
      }
    }
  });
}

function renderLowAttendanceList(students) {
  const tbody = document.getElementById('low-attendance-tbody');
  if (!tbody) return;

  if (!students || students.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5">
          <div class="empty-state" style="padding: 1.5rem;">
            <p class="empty-state-desc" style="color:var(--success);">Great news! All enrolled students currently maintain attendance above the 75% threshold.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = students.map(s => {
    return `
      <tr>
        <td>
          <div style="display:flex; align-items:center; gap:0.625rem;">
            <img src="${s.avatar_url || '/static/images/avatars/default_avatar.png'}" style="width:32px; height:32px; border-radius:50%; object-fit:cover;" onerror="this.src='/static/images/avatars/default_avatar.png'">
            <div>
              <div style="font-weight:700; color:var(--text-heading);">${s.full_name}</div>
              <small>${s.roll_number}</small>
            </div>
          </div>
        </td>
        <td>${s.class_section}</td>
        <td>${s.present_count} / ${s.total_classes} classes</td>
        <td>
          <span class="badge badge-absent" style="font-size:0.8125rem; font-weight:800;">${s.percentage}%</span>
        </td>
        <td>
          <span class="badge badge-late">Warning Alert</span>
        </td>
      </tr>
    `;
  }).join('');
}
