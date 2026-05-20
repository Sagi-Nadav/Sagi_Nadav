import { initCalendar } from './calendar.js';
import { initTasks } from './tasks.js';
import { initEmail } from './email.js';
import { initSettings } from './settings.js';

// ── State ────────────────────────────────────────────────────────
export const state = {
  user: null,
  currentView: null,
};

// ── API helper ───────────────────────────────────────────────────
export async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body !== null) opts.body = JSON.stringify(body);

  const resp = await fetch(path, opts);

  if (resp.status === 401) {
    window.location.href = '/auth/login';
    return null;
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || 'שגיאה בשרת');
  }

  if (resp.status === 204) return null;
  return resp.json();
}

// ── Toast ────────────────────────────────────────────────────────
export function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
  container.prepend(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Router ───────────────────────────────────────────────────────
const views = {
  dashboard: loadDashboard,
  calendar: initCalendar,
  tasks: initTasks,
  email: initEmail,
  settings: initSettings,
};

async function route() {
  const hash = window.location.hash.slice(1) || 'dashboard';
  const view = views[hash] ? hash : 'dashboard';

  document.querySelectorAll('.nav-link').forEach(l => {
    l.classList.toggle('active', l.dataset.view === view);
  });

  if (state.currentView !== view) {
    state.currentView = view;
    const fn = views[view];
    if (fn) fn();
  }
}

// ── Dashboard ────────────────────────────────────────────────────
async function loadDashboard() {
  const container = document.getElementById('view-container');
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">שלום, ${state.user?.display_name || 'משתמש'} 👋</div>
        <div class="page-subtitle">${hebrewDate()}</div>
      </div>
      <button class="btn btn-primary" onclick="window.location.hash='calendar'">
        ➕ אירוע חדש
      </button>
    </div>
    <div class="dashboard-grid">
      <div class="card" id="dash-events">
        <div class="card-title">📆 אירועים היום</div>
        <div id="dash-events-list"><span class="loading-text">⏳ טוען...</span></div>
      </div>
      <div class="card" id="dash-tasks">
        <div class="card-title">✅ משימות פתוחות השבוע</div>
        <div id="dash-tasks-list"><span class="loading-text">⏳ טוען...</span></div>
      </div>
    </div>
  `;

  // Load in parallel
  const [events, tasks] = await Promise.allSettled([
    api('GET', '/api/calendar/events/today'),
    api('GET', '/api/tasks?week_of='),
  ]);

  renderDashEvents(events.status === 'fulfilled' ? events.value : []);
  renderDashTasks(tasks.status === 'fulfilled' ? tasks.value : []);
}

function renderDashEvents(events) {
  const el = document.getElementById('dash-events-list');
  if (!events || events.length === 0) {
    el.innerHTML = '<span class="text-secondary">אין אירועים להיום 🎉</span>';
    return;
  }
  el.innerHTML = events.map(e => `
    <div class="event-item">
      <div class="event-time">${formatTime(e.start)}</div>
      <div>
        <div class="event-subject">${e.subject}</div>
        ${e.location ? `<div class="event-location">📍 ${e.location}</div>` : ''}
      </div>
    </div>
  `).join('');
}

function renderDashTasks(tasks) {
  const el = document.getElementById('dash-tasks-list');
  const open = (tasks || []).filter(t => t.status === 'open' || t.status === 'in_progress');
  if (open.length === 0) {
    el.innerHTML = '<span class="text-secondary">כל המשימות בוצעו ✨</span>';
    return;
  }
  el.innerHTML = open.slice(0, 8).map(t => `
    <div class="task-item">
      <span class="priority-dot p${t.priority}"></span>
      <span>${t.title}</span>
    </div>
  `).join('');
}

// ── Modal helpers ────────────────────────────────────────────────
export function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

export function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

// ── Utility ──────────────────────────────────────────────────────
export function formatTime(iso) {
  if (!iso) return 'כל היום';
  const d = new Date(iso);
  return d.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('he-IL', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function toLocalInputFormat(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function hebrewDate() {
  return new Date().toLocaleDateString('he-IL', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

export function getWeekStart(anchor) {
  const d = new Date(anchor);
  // Sunday = 0 in JS; adjust to keep Sunday as first day of week
  const day = d.getDay(); // 0=Sun ... 6=Sat
  const diff = d.getDate() - day;
  const start = new Date(d.setDate(diff));
  start.setHours(0, 0, 0, 0);
  return start;
}

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  const data = await api('GET', '/auth/me');
  if (!data || !data.authenticated) {
    document.getElementById('login-overlay').classList.remove('hidden');
    return;
  }

  state.user = data;
  document.getElementById('app').classList.remove('hidden');
  document.getElementById('user-info').textContent = data.display_name;

  document.getElementById('logout-btn').addEventListener('click', async () => {
    await api('POST', '/auth/logout');
    window.location.reload();
  });

  // Close modals on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(el => {
    el.addEventListener('click', () => {
      el.closest('.modal').classList.add('hidden');
    });
  });

  document.getElementById('event-modal-close').addEventListener('click', () => closeModal('event-modal'));
  document.getElementById('task-modal-close').addEventListener('click', () => closeModal('task-modal'));

  window.addEventListener('hashchange', route);
  route();
}

document.addEventListener('DOMContentLoaded', init);
