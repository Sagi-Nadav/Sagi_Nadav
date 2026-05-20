import { api, toast, openModal, closeModal } from './app.js';

let currentTab = 'week';
let currentTasks = [];
let draggedId = null;

const STATUS_LABELS = {
  open: '📋 פתוחות',
  in_progress: '🔄 בביצוע',
  done: '✅ בוצעו',
  deferred: '⏸ נדחו',
};

export function initTasks() {
  renderTasksPage();
}

function renderTasksPage() {
  const container = document.getElementById('view-container');
  const today = new Date();
  const isMonday = today.getDay() === 1;

  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">✅ משימות</div>
      </div>
      <button class="btn btn-primary" id="task-new-btn">➕ משימה חדשה</button>
    </div>

    ${isMonday ? `
    <div class="banner" id="week-banner">
      <span style="font-size:24px">📅</span>
      <div class="banner-text">
        <div class="banner-title">שבוע חדש — נתחיל לתכנן!</div>
        <div class="banner-sub">יצור את המשימות לשבוע הקרוב</div>
      </div>
      <button class="btn btn-primary btn-small" id="start-week-btn">תכנון שבוע</button>
    </div>` : ''}

    <div class="tasks-tabs">
      <button class="tasks-tab ${currentTab === 'week' ? 'active' : ''}" data-tab="week">השבוע</button>
      <button class="tasks-tab ${currentTab === 'today' ? 'active' : ''}" data-tab="today">היום</button>
      <button class="tasks-tab ${currentTab === 'eod' ? 'active' : ''}" data-tab="eod">סיכום יום 🌙</button>
    </div>

    <div id="tasks-content"></div>
  `;

  document.getElementById('task-new-btn').onclick = () => openTaskModal(null);

  document.querySelectorAll('.tasks-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      currentTab = btn.dataset.tab;
      document.querySelectorAll('.tasks-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === currentTab));
      loadTabContent();
    });
  });

  if (isMonday) {
    document.getElementById('start-week-btn').onclick = () => openTaskModal(null);
  }

  // Task modal submit
  document.getElementById('task-form').onsubmit = handleTaskSubmit;
  document.getElementById('task-delete-btn').onclick = handleTaskDelete;

  loadTabContent();
}

async function loadTabContent() {
  const content = document.getElementById('tasks-content');

  if (currentTab === 'week') {
    content.innerHTML = '<span class="loading-text">⏳ טוען...</span>';
    currentTasks = await api('GET', '/api/tasks') || [];
    renderKanban(currentTasks);
  } else if (currentTab === 'today') {
    content.innerHTML = '<span class="loading-text">⏳ טוען...</span>';
    currentTasks = await api('GET', '/api/tasks/today') || [];
    renderTodayList(currentTasks);
  } else if (currentTab === 'eod') {
    renderEOD();
  }
}

// ── Kanban ───────────────────────────────────────────────────────

function renderKanban(tasks) {
  const content = document.getElementById('tasks-content');
  const statuses = ['open', 'in_progress', 'done', 'deferred'];

  const cols = statuses.map(status => {
    const colTasks = tasks.filter(t => t.status === status);
    const cards = colTasks.map(t => taskCard(t)).join('');
    return `
      <div class="kanban-col" data-status="${status}"
        ondragover="event.preventDefault();this.classList.add('drag-over')"
        ondragleave="this.classList.remove('drag-over')"
        ondrop="window._taskDrop(event, '${status}')">
        <div class="kanban-col-header">
          ${STATUS_LABELS[status]}
          <span class="kanban-count">${colTasks.length}</span>
        </div>
        ${cards}
      </div>
    `;
  }).join('');

  content.innerHTML = `<div class="kanban-board">${cols}</div>`;
}

function taskCard(t) {
  const dueClass = t.due_date && new Date(t.due_date) < new Date() && t.status !== 'done' ? 'overdue' : '';
  const dueText = t.due_date ? new Date(t.due_date).toLocaleDateString('he-IL') : '';
  return `
    <div class="task-card" draggable="true"
      ondragstart="window._taskDragStart(event, ${t.id})"
      ondragend="event.currentTarget.classList.remove('dragging')"
      onclick="window._taskEdit(${t.id})">
      <div class="task-card-title">${t.title}</div>
      <div class="task-card-meta">
        <span class="priority-dot p${t.priority}"></span>
        ${dueText ? `<span class="task-due ${dueClass}">${dueText}</span>` : ''}
      </div>
    </div>
  `;
}

// Drag handlers
window._taskDragStart = (e, id) => {
  draggedId = id;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
};

window._taskDrop = async (e, newStatus) => {
  e.currentTarget.classList.remove('drag-over');
  if (!draggedId) return;
  try {
    await api('PATCH', `/api/tasks/${draggedId}`, { status: newStatus });
    toast('סטטוס עודכן', 'success');
    currentTasks = await api('GET', '/api/tasks') || [];
    renderKanban(currentTasks);
  } catch (err) {
    toast('שגיאה: ' + err.message, 'error');
  }
  draggedId = null;
};

// ── Today list ───────────────────────────────────────────────────

function renderTodayList(tasks) {
  const content = document.getElementById('tasks-content');
  if (tasks.length === 0) {
    content.innerHTML = `<div class="card"><span class="text-secondary">אין משימות ליום זה 🎉</span></div>`;
    return;
  }
  const items = tasks.map(t => `
    <div class="task-item" style="cursor:pointer" onclick="window._taskEdit(${t.id})">
      <span class="priority-dot p${t.priority}" style="margin-top:5px"></span>
      <div style="flex:1">
        <div style="font-weight:500">${t.title}</div>
        ${t.description ? `<div class="text-secondary text-small">${t.description}</div>` : ''}
      </div>
      <button class="btn btn-success btn-small" onclick="event.stopPropagation();window._taskComplete(${t.id})">✓ בוצע</button>
    </div>
  `).join('');
  content.innerHTML = `<div class="card">${items}</div>`;
}

window._taskComplete = async (id) => {
  try {
    await api('POST', `/api/tasks/${id}/complete`);
    toast('משימה סומנה כבוצעה', 'success');
    loadTabContent();
  } catch (err) {
    toast('שגיאה: ' + err.message, 'error');
  }
};

// ── EOD Review ───────────────────────────────────────────────────

function renderEOD() {
  const content = document.getElementById('tasks-content');
  content.innerHTML = `
    <div class="eod-panel">
      <h3 style="margin-bottom:16px">🌙 סיכום יום + הכנה למחר</h3>

      <div style="margin-bottom:20px">
        <div class="card-title">סיכום היום</div>
        <div class="eod-summary loading-text" id="eod-summary">⏳ מייצר סיכום...</div>
      </div>

      <div style="margin-bottom:20px">
        <div class="card-title">תוכנית למחר</div>
        <div class="eod-summary loading-text" id="eod-plan">⏳ מכין תוכנית...</div>
      </div>

      <div>
        <div class="card-title">משימות פתוחות</div>
        <div id="eod-incomplete"><span class="loading-text">⏳ טוען...</span></div>
      </div>
    </div>
  `;

  // Load in parallel
  api('GET', '/api/ai/day-summary').then(r => {
    const el = document.getElementById('eod-summary');
    if (el) el.textContent = r?.summary || 'לא הצלחתי לייצר סיכום';
  }).catch(e => {
    const el = document.getElementById('eod-summary');
    if (el) el.textContent = 'שגיאה: ' + e.message;
  });

  api('GET', '/api/ai/tomorrow-plan').then(r => {
    const el = document.getElementById('eod-plan');
    if (el) el.textContent = r?.plan || 'לא הצלחתי לייצר תוכנית';
  }).catch(e => {
    const el = document.getElementById('eod-plan');
    if (el) el.textContent = 'שגיאה: ' + e.message;
  });

  api('GET', '/api/tasks/incomplete').then(tasks => {
    const el = document.getElementById('eod-incomplete');
    if (!el) return;
    if (!tasks || tasks.length === 0) {
      el.innerHTML = '<span class="text-secondary">כל המשימות בוצעו! 🎉</span>';
      return;
    }
    el.innerHTML = tasks.map(t => `
      <div class="task-item">
        <span class="priority-dot p${t.priority}"></span>
        <span>${t.title}</span>
        <span class="text-small text-secondary" style="margin-right:auto">${t.status}</span>
      </div>
    `).join('');
  });
}

// ── Task Modal ───────────────────────────────────────────────────

export function openTaskModal(task) {
  const form = document.getElementById('task-form');
  form.reset();

  const titleEl = document.getElementById('task-modal-title');
  const deleteBtn = document.getElementById('task-delete-btn');
  const idEl = document.getElementById('task-id');

  if (task) {
    titleEl.textContent = 'עריכת משימה';
    idEl.value = task.id;
    document.getElementById('task-title').value = task.title;
    document.getElementById('task-description').value = task.description || '';
    document.getElementById('task-priority').value = task.priority;
    document.getElementById('task-due-date').value = task.due_date?.slice(0, 10) || '';
    deleteBtn.classList.remove('hidden');
  } else {
    titleEl.textContent = 'משימה חדשה';
    idEl.value = '';
    deleteBtn.classList.add('hidden');
  }

  openModal('task-modal');
}

window._taskEdit = (id) => {
  const task = currentTasks.find(t => t.id === id);
  if (task) openTaskModal(task);
};

async function handleTaskSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('task-id').value;
  const data = {
    title: document.getElementById('task-title').value,
    description: document.getElementById('task-description').value || null,
    priority: parseInt(document.getElementById('task-priority').value),
    due_date: document.getElementById('task-due-date').value || null,
  };

  try {
    if (id) {
      await api('PATCH', `/api/tasks/${id}`, data);
      toast('משימה עודכנה', 'success');
    } else {
      await api('POST', '/api/tasks', data);
      toast('משימה נוצרה', 'success');
    }
    closeModal('task-modal');
    loadTabContent();
  } catch (err) {
    toast('שגיאה: ' + err.message, 'error');
  }
}

async function handleTaskDelete() {
  const id = document.getElementById('task-id').value;
  if (!id) return;
  if (!confirm('למחוק את המשימה הזו?')) return;
  try {
    await api('DELETE', `/api/tasks/${id}`);
    toast('המשימה נמחקה', 'success');
    closeModal('task-modal');
    loadTabContent();
  } catch (err) {
    toast('שגיאה: ' + err.message, 'error');
  }
}
