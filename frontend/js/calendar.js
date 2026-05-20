import { api, toast, openModal, closeModal, formatTime, toLocalInputFormat, getWeekStart } from './app.js';

let weekAnchor = new Date();
let allEvents = [];

const DAY_NAMES = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
const HOUR_START = 7;
const HOUR_END = 21;
const PX_PER_HOUR = 60;

export function initCalendar() {
  weekAnchor = new Date();
  renderCalendarPage();
}

function renderCalendarPage() {
  const container = document.getElementById('view-container');
  container.innerHTML = `
    <div class="page-header">
      <div class="calendar-nav">
        <button class="btn btn-ghost btn-small" id="cal-prev">‹ הקודם</button>
        <span class="week-label" id="week-label"></span>
        <button class="btn btn-ghost btn-small" id="cal-next">הבא ›</button>
        <button class="btn btn-ghost btn-small" id="cal-today">היום</button>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-ghost btn-small" id="cal-suggest-slots">🕐 הצע זמנים פנויים</button>
        <button class="btn btn-primary" id="cal-new-event">➕ אירוע חדש</button>
      </div>
    </div>

    <!-- Natural language input -->
    <div class="natural-input-bar">
      <input type="text" id="natural-event-input" placeholder='כתוב בחופשי: "פגישה עם דוד מחר ב-14:00 שעה"' />
      <button class="btn btn-primary btn-small" id="natural-parse-btn">✨ צור אירוע</button>
    </div>

    <div id="week-view" style="overflow-x:auto;"></div>

    <!-- Slots modal -->
    <div id="slots-modal" class="modal hidden">
      <div class="modal-backdrop"></div>
      <div class="modal-box">
        <div class="modal-header">
          <h2>🕐 זמנים פנויים</h2>
          <button class="modal-close" id="slots-modal-close">✕</button>
        </div>
        <div style="padding:16px;">
          <div class="form-row" style="margin-bottom:16px;">
            <div class="form-group">
              <label>משך (דקות)</label>
              <select id="slots-duration">
                <option value="30">30 דקות</option>
                <option value="60" selected>שעה</option>
                <option value="90">שעה וחצי</option>
                <option value="120">שעתיים</option>
              </select>
            </div>
            <div class="form-group">
              <label>חיפוש בטווח</label>
              <select id="slots-days">
                <option value="5">5 ימים</option>
                <option value="7" selected>שבוע</option>
                <option value="14">שבועיים</option>
              </select>
            </div>
          </div>
          <button class="btn btn-primary" id="slots-search-btn">חפש זמנים</button>
          <div id="slots-results" style="margin-top:16px;"></div>
        </div>
      </div>
    </div>
  `;

  document.getElementById('cal-prev').onclick = () => { weekAnchor.setDate(weekAnchor.getDate() - 7); loadWeek(); };
  document.getElementById('cal-next').onclick = () => { weekAnchor.setDate(weekAnchor.getDate() + 7); loadWeek(); };
  document.getElementById('cal-today').onclick = () => { weekAnchor = new Date(); loadWeek(); };
  document.getElementById('cal-new-event').onclick = () => openEventModal(null);
  document.getElementById('cal-suggest-slots').onclick = () => {
    document.getElementById('slots-modal').classList.remove('hidden');
  };
  document.getElementById('slots-modal-close').onclick = () => {
    document.getElementById('slots-modal').classList.add('hidden');
  };
  document.querySelector('#slots-modal .modal-backdrop').onclick = () => {
    document.getElementById('slots-modal').classList.add('hidden');
  };
  document.getElementById('slots-search-btn').onclick = searchFreeSlots;
  document.getElementById('natural-parse-btn').onclick = parseNaturalEvent;
  document.getElementById('natural-event-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') parseNaturalEvent();
  });

  loadWeek();
}

async function searchFreeSlots() {
  const btn = document.getElementById('slots-search-btn');
  const results = document.getElementById('slots-results');
  const duration = parseInt(document.getElementById('slots-duration').value);
  const days = parseInt(document.getElementById('slots-days').value);

  btn.textContent = '⏳ מחפש...';
  btn.disabled = true;
  results.innerHTML = '';

  try {
    const slots = await api('POST', '/api/calendar/free-slots', { duration_minutes: duration, days_ahead: days });
    if (!slots || slots.length === 0) {
      results.innerHTML = '<p style="color:var(--text-secondary)">לא נמצאו זמנים פנויים בטווח זה.</p>';
      return;
    }
    results.innerHTML = slots.map(s => `
      <div class="slot-card" onclick="window._useSlot('${s.start}', '${s.end}')">
        <div class="slot-label">${s.label}</div>
        <span class="btn btn-primary btn-small">+ קבע פגישה</span>
      </div>
    `).join('');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  } finally {
    btn.textContent = 'חפש זמנים';
    btn.disabled = false;
  }
}

window._useSlot = (start, end) => {
  document.getElementById('slots-modal').classList.add('hidden');
  openEventModal(null, null, start, end);
};

async function parseNaturalEvent() {
  const input = document.getElementById('natural-event-input');
  const text = input.value.trim();
  if (!text) return;

  const btn = document.getElementById('natural-parse-btn');
  btn.textContent = '⏳';
  btn.disabled = true;

  try {
    const result = await api('POST', '/api/calendar/parse-natural', { text });
    if (!result || !result.subject) {
      toast('לא הצלחתי להבין. נסה לנסח אחרת.', 'warning');
      return;
    }
    input.value = '';
    openEventModal(result);
    toast('פרטי האירוע חולצו — בדוק ואשר', 'info');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  } finally {
    btn.textContent = '✨ צור אירוע';
    btn.disabled = false;
  }
}

async function loadWeek() {
  const weekStart = getWeekStart(weekAnchor);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);

  document.getElementById('week-label').textContent = weekRangeLabel(weekStart, weekEnd);

  const startStr = weekStart.toISOString().slice(0, 19);
  const endStr = weekEnd.toISOString().slice(0, 19);

  try {
    allEvents = await api('GET', `/api/calendar/events?start=${startStr}&end=${endStr}`);
    renderWeekGrid(weekStart, allEvents);
  } catch (e) {
    toast('שגיאה בטעינת היומן: ' + e.message, 'error');
  }
}

function weekRangeLabel(start, end) {
  const s = start.toLocaleDateString('he-IL', { day: 'numeric', month: 'long' });
  const endDay = new Date(end); endDay.setDate(endDay.getDate() - 1);
  const e = endDay.toLocaleDateString('he-IL', { day: 'numeric', month: 'long', year: 'numeric' });
  return `${s} – ${e}`;
}

function renderWeekGrid(weekStart, events) {
  const container = document.getElementById('week-view');
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Split all-day vs timed
  const allDay = events.filter(e => e.is_all_day);
  const timed = events.filter(e => !e.is_all_day);

  // Build day columns
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  });

  const totalH = (HOUR_END - HOUR_START) * PX_PER_HOUR;

  // Header row HTML
  const headerCells = days.map((d, i) => {
    const isToday = d.getTime() === today.getTime();
    return `<div class="day-header${isToday ? ' today' : ''}">
      <div>${DAY_NAMES[d.getDay()]}</div>
      <div class="day-num">${d.getDate()}</div>
    </div>`;
  }).join('');

  // All-day row
  const allDayCells = days.map(d => {
    const dayEvents = allDay.filter(e => sameDay(new Date(e.start), d));
    return `<div class="all-day-row" style="grid-column:auto;">
      ${dayEvents.map(e => `<div class="all-day-event" onclick='window._calEdit(${JSON.stringify(e.id)})'>${e.subject}</div>`).join('')}
    </div>`;
  }).join('');

  // Day columns with timed events
  const dayCols = days.map(d => {
    const isToday = d.getTime() === today.getTime();
    const dayEvents = timed.filter(e => {
      const es = new Date(e.start);
      return sameDay(es, d);
    });

    const hourLines = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => {
      return `<div class="hour-line" style="top:${i * PX_PER_HOUR}px"></div>`;
    }).join('');

    const evCards = dayEvents.map(e => {
      const start = new Date(e.start);
      const end = new Date(e.end);
      const startMins = (start.getHours() - HOUR_START) * 60 + start.getMinutes();
      const endMins = (end.getHours() - HOUR_START) * 60 + end.getMinutes();
      const top = Math.max(0, (startMins / 60) * PX_PER_HOUR);
      const height = Math.max(20, ((endMins - startMins) / 60) * PX_PER_HOUR);
      return `<div class="cal-event" style="top:${top}px;height:${height}px"
        onclick='event.stopPropagation();window._calEdit(${JSON.stringify(e.id)})'>
        <div class="ev-title">${e.subject}</div>
        <div class="ev-time">${formatTime(e.start)}</div>
      </div>`;
    }).join('');

    const isoDate = d.toISOString().slice(0, 10);
    return `<div class="day-col${isToday ? ' today' : ''}" data-date="${isoDate}"
      onclick="window._calNewOnDay('${isoDate}')">
      ${hourLines}${evCards}
    </div>`;
  }).join('');

  // Time column
  const timeLabels = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => {
    return `<div class="time-col" style="height:${PX_PER_HOUR}px;line-height:${PX_PER_HOUR}px">${HOUR_START + i}:00</div>`;
  }).join('');

  container.innerHTML = `
    <div class="week-grid" style="grid-template-rows:auto auto ${totalH}px;">
      <div class="time-col-header"></div>
      ${headerCells}
      <div class="time-col-header"></div>
      ${allDayCells}
      <div style="display:flex;flex-direction:column">${timeLabels}</div>
      ${dayCols}
    </div>
  `;
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
}

// ── Event Modal ──────────────────────────────────────────────────

export function openEventModal(event, defaultDate = null, preStart = null, preEnd = null) {
  const form = document.getElementById('event-form');
  form.reset();

  const titleEl = document.getElementById('event-modal-title');
  const deleteBtn = document.getElementById('event-delete-btn');
  const idEl = document.getElementById('event-id');

  if (event) {
    titleEl.textContent = 'עריכת אירוע';
    idEl.value = event.id;
    document.getElementById('event-subject').value = event.subject;
    document.getElementById('event-start').value = toLocalInputFormat(event.start);
    document.getElementById('event-end').value = toLocalInputFormat(event.end);
    document.getElementById('event-location').value = event.location || '';
    document.getElementById('event-body').value = event.body ? event.body.replace(/<[^>]+>/g, '') : '';
    document.getElementById('event-attendees').value = (event.attendees || [])
      .map(a => a.name ? `${a.name} <${a.email}>` : a.email).join('\n');
    deleteBtn.classList.remove('hidden');
  } else {
    titleEl.textContent = 'אירוע חדש';
    idEl.value = '';
    deleteBtn.classList.add('hidden');
    if (preStart) {
      document.getElementById('event-subject').value = event?.subject || '';
      document.getElementById('event-start').value = toLocalInputFormat(preStart);
      document.getElementById('event-end').value = toLocalInputFormat(preEnd || preStart);
      document.getElementById('event-location').value = event?.location || '';
    } else if (defaultDate) {
      const d = new Date(defaultDate + 'T09:00');
      const e = new Date(defaultDate + 'T10:00');
      document.getElementById('event-start').value = toLocalInputFormat(d.toISOString());
      document.getElementById('event-end').value = toLocalInputFormat(e.toISOString());
    }
  }

  openModal('event-modal');
}

// Global callbacks for inline onclick
window._calEdit = async (id) => {
  const ev = allEvents.find(e => e.id === id);
  if (ev) openEventModal(ev);
};

window._calNewOnDay = (dateStr) => {
  openEventModal(null, dateStr);
};

// ── Form submit ──────────────────────────────────────────────────

document.getElementById('event-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = document.getElementById('event-id').value;

  const attendeesRaw = document.getElementById('event-attendees').value.trim();
  const attendees = attendeesRaw ? parseAttendees(attendeesRaw) : [];

  const data = {
    subject: document.getElementById('event-subject').value,
    start: document.getElementById('event-start').value + ':00',
    end: document.getElementById('event-end').value + ':00',
    location: document.getElementById('event-location').value || null,
    body: document.getElementById('event-body').value || null,
    attendees,
    is_online: document.getElementById('event-online').checked,
  };

  try {
    if (id) {
      await api('PATCH', `/api/calendar/events/${id}`, data);
      toast('האירוע עודכן בהצלחה', 'success');
    } else {
      await api('POST', '/api/calendar/events', data);
      toast('האירוע נוצר בהצלחה', 'success');
    }
    closeModal('event-modal');
    loadWeek();
  } catch (err) {
    toast('שגיאה: ' + err.message, 'error');
  }
});

document.getElementById('event-delete-btn').addEventListener('click', async () => {
  const id = document.getElementById('event-id').value;
  if (!id) return;
  if (!confirm('למחוק את האירוע הזה?')) return;
  try {
    await api('DELETE', `/api/calendar/events/${id}`);
    toast('האירוע נמחק', 'success');
    closeModal('event-modal');
    loadWeek();
  } catch (err) {
    toast('שגיאה במחיקה: ' + err.message, 'error');
  }
});

function parseAttendees(raw) {
  return raw.split('\n').filter(Boolean).map(line => {
    const match = line.match(/^(.*?)\s*<(.+)>$/);
    if (match) return { name: match[1].trim(), email: match[2].trim() };
    return { name: line.trim(), email: line.trim() };
  });
}
