/**
 * AutoAttend Dashboard Analytics Script
 * Visualizes live statistics, trends, and Chart.js graphics
 */

let weeklyChart = null;
let doughnutChart = null;

document.addEventListener('DOMContentLoaded', () => {
  setGreetingTime();
  fetchDashboardData();
});

function setGreetingTime() {
  const greetingEl = document.getElementById('greeting-heading');
  if (!greetingEl) return;
  const hour = new Date().getHours();
  let greet = 'Good morning';
  if (hour >= 12 && hour < 17) greet = 'Good afternoon';
  else if (hour >= 17) greet = 'Good evening';
  greetingEl.innerHTML = `${greet}, <span style="color: var(--accent-cyan);">Teacher</span>`;
}

async function fetchDashboardData() {
  try {
    const res = await fetch('/api/dashboard/stats');
    if (!res.ok) throw new Error('Failed to load dashboard metrics');
    const data = await res.json();

    if (data.success) {
      updateKPICards(data.kpis);
      renderCharts(data.charts);
      renderRecentActivity(data.recent_activity);
      updateActiveLectureBanner(data.active_session);
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to load dashboard metrics', 'danger');
  }
}

function updateKPICards(kpis) {
  const totalEl = document.getElementById('kpi-total-students');
  const presentEl = document.getElementById('kpi-present-today');
  const absentEl = document.getElementById('kpi-absent-today');
  const pctEl = document.getElementById('kpi-attendance-pct');

  if (totalEl) totalEl.textContent = kpis.total_students || 0;
  if (presentEl) presentEl.textContent = kpis.present_today || 0;
  if (absentEl) absentEl.textContent = kpis.absent_today || 0;
  if (pctEl) pctEl.textContent = `${kpis.percentage_today || 0}%`;
}

function updateActiveLectureBanner(active) {
  const lectureEl = document.getElementById('active-lecture-indicator');
  if (!lectureEl) return;
  if (active) {
    lectureEl.innerHTML = `
      <span class="badge badge-ai"><span class="pulse-dot"></span> Live Lecture</span>
      <span style="font-weight: 600; color: #FFFFFF;">${active.subject_name} (${active.room_number})</span>
    `;
  } else {
    lectureEl.innerHTML = `
      <span class="badge" style="background: rgba(255,255,255,0.1); color: #CBD5E1;">Schedule Ready</span>
      <span style="color: #94A3B8;">CS-601 Machine Learning • Lab 301</span>
    `;
  }
}

function renderCharts(chartsData) {
  // 1. Weekly Trends Line Chart
  const lineCtx = document.getElementById('weeklyTrendChart');
  if (lineCtx && chartsData.weekly) {
    const labels = chartsData.weekly.map(w => w.day);
    const presentData = chartsData.weekly.map(w => w.present);
    const absentData = chartsData.weekly.map(w => w.absent);

    if (weeklyChart) weeklyChart.destroy();

    weeklyChart = new Chart(lineCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Present Students',
            data: presentData,
            borderColor: '#4F46E5',
            backgroundColor: 'rgba(79, 70, 229, 0.08)',
            borderWidth: 3,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: '#4F46E5',
            pointRadius: 4,
            pointHoverRadius: 6
          },
          {
            label: 'Absent Students',
            data: absentData,
            borderColor: '#EF4444',
            backgroundColor: 'transparent',
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false,
            tension: 0.3,
            pointBackgroundColor: '#EF4444',
            pointRadius: 3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              font: { family: 'Plus Jakarta Sans', size: 12, weight: 600 },
              usePointStyle: true,
              boxWidth: 8
            }
          },
          tooltip: {
            backgroundColor: '#0F172A',
            padding: 10,
            cornerRadius: 8,
            titleFont: { family: 'Plus Jakarta Sans', weight: 700 }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: '#F1F5F9' },
            ticks: { font: { family: 'Plus Jakarta Sans' }, precision: 0 }
          },
          x: {
            grid: { display: false },
            ticks: { font: { family: 'Plus Jakarta Sans' } }
          }
        }
      }
    });
  }

  // 2. Present vs Absent Doughnut Chart
  const donutCtx = document.getElementById('attendanceDoughnutChart');
  if (donutCtx && chartsData.doughnut) {
    const p = chartsData.doughnut.present || 0;
    const a = chartsData.doughnut.absent || 0;
    const total = p + a;

    if (doughnutChart) doughnutChart.destroy();

    doughnutChart = new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels: ['Present', 'Absent'],
        datasets: [{
          data: total === 0 ? [1, 0] : [p, a],
          backgroundColor: total === 0 ? ['#E2E8F0', '#E2E8F0'] : ['#10B981', '#EF4444'],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              font: { family: 'Plus Jakarta Sans', size: 12, weight: 600 },
              usePointStyle: true,
              boxWidth: 8
            }
          }
        }
      }
    });

    const centerPct = document.getElementById('doughnut-center-percentage');
    if (centerPct) {
      const pct = total > 0 ? Math.round((p / total) * 100) : 0;
      centerPct.textContent = `${pct}%`;
    }
  }
}

function renderRecentActivity(activityList) {
  const container = document.getElementById('recent-activity-container');
  if (!container) return;

  if (!activityList || activityList.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding: 1.5rem;">
        <p class="empty-state-desc">No attendance records logged today yet.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = activityList.map(item => {
    let badgeClass = 'badge-present';
    let badgeLabel = 'Present';
    if (item.status === 'absent') { badgeClass = 'badge-absent'; badgeLabel = 'Absent'; }
    else if (item.status === 'late') { badgeClass = 'badge-late'; badgeLabel = 'Late'; }

    const confScore = Math.round((item.confidence_score || 0) * 100);
    const timeFormatted = item.timestamp ? new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--';

    return `
      <div class="activity-item">
        <div class="activity-student">
          <img src="${item.avatar_url || '/static/images/avatars/default_avatar.png'}" class="activity-avatar" alt="${item.full_name}" onerror="this.src='/static/images/avatars/default_avatar.png'">
          <div class="activity-meta">
            <span class="activity-name">${item.full_name}</span>
            <span class="activity-roll">${item.roll_number} • ${item.subject_code}</span>
          </div>
        </div>
        <div class="activity-right">
          ${item.verification_method === 'ai_face_recognition' ? `<span class="badge badge-ai" title="AI Confidence: ${confScore}%">AI ${confScore}%</span>` : ''}
          <span class="badge ${badgeClass}">${badgeLabel}</span>
          <small>${timeFormatted}</small>
        </div>
      </div>
    `;
  }).join('');
}
