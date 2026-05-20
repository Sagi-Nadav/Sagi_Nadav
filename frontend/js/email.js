import { api, toast } from './app.js';

let currentDraftId = null;
let currentTab = 'inbox';

export function initEmail() {
  renderEmailPage();
}

function renderEmailPage() {
  const container = document.getElementById('view-container');
  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">✉️ מיילים</div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button class="btn btn-ghost btn-small" id="process-now-btn">🔄 עבד מיילים עכשיו</button>
        <button class="btn btn-ghost btn-small" id="learn-style-btn">🎓 למד סגנון</button>
      </div>
    </div>

    <div class="tab-bar">
      <button class="tab-btn active" data-tab="inbox">📥 תיבת דואר</button>
      <button class="tab-btn" data-tab="pending">⏳ ממתינים לאישור <span id="pending-badge" class="badge hidden">0</span></button>
      <button class="tab-btn" data-tab="projects">📁 פרויקטים</button>
    </div>

    <!-- INBOX TAB -->
    <div id="tab-inbox" class="tab-content">
      <div class="email-layout">
        <div class="inbox-list">
          <div class="inbox-header">📥 תיבת דואר נכנס</div>
          <div id="inbox-items"><div class="inbox-item"><span class="loading-text">⏳ טוען...</span></div></div>
          <div style="padding:8px;text-align:center">
            <button class="btn btn-ghost btn-small" id="inbox-load-more">טען עוד</button>
          </div>
        </div>

        <div class="compose-panel">
          <div class="compose-header"><span>✍️ כתיבת מייל</span></div>
          <div class="compose-form">
            <input type="text" id="compose-to" placeholder="אל: email@example.com" />
            <input type="text" id="compose-subject" placeholder="נושא" />
            <textarea id="compose-request" rows="3"
              placeholder="תאר מה לכתוב... (לדוגמה: מייל מקצועי לדחיית פגישה עם הערכה לזמנם)"></textarea>
            <button class="btn btn-primary" id="draft-btn">✨ ייצר טיוטה עם AI</button>
            <div class="draft-area" id="draft-body" contenteditable="true"
              data-placeholder="הטיוטה תופיע כאן..."></div>
          </div>
          <div class="compose-actions">
            <button class="btn btn-primary" id="send-btn" disabled>📤 שלח</button>
            <button class="btn btn-ghost btn-small" id="save-draft-btn" disabled>💾 שמור טיוטה</button>
            <button class="btn btn-ghost btn-small" id="clear-btn">🗑 נקה</button>
          </div>
        </div>

        <div class="ai-panel">
          <div class="ai-panel-header">🤖 עוזר AI</div>
          <div class="ai-chat" id="ai-chat">
            <div class="ai-message">שלום! אני כאן לעזור לך לכתוב מיילים. ייצר טיוטה ואז תוכל לבקש שינויים כאן.</div>
          </div>
          <div class="ai-input-area">
            <textarea id="ai-instruction" placeholder="שנה את הטון, קצר, הוסף..."></textarea>
            <button class="btn btn-primary btn-small" id="ai-refine-btn" disabled>⚡</button>
          </div>
        </div>
      </div>
    </div>

    <!-- PENDING TAB -->
    <div id="tab-pending" class="tab-content hidden">
      <div class="pending-list" id="pending-list">
        <div class="loading-text" style="padding:32px;text-align:center;">⏳ טוען...</div>
      </div>
    </div>

    <!-- PROJECTS TAB -->
    <div id="tab-projects" class="tab-content hidden">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 style="margin:0;">📁 פרויקטים לסיווג מיילים</h3>
        <button class="btn btn-primary btn-small" id="new-project-btn">+ פרויקט חדש</button>
      </div>
      <div id="projects-list" class="projects-grid">
        <div class="loading-text" style="padding:32px;text-align:center;">⏳ טוען...</div>
      </div>
    </div>

    <!-- Style modal -->
    <div id="style-modal" class="modal hidden">
      <div class="modal-backdrop"></div>
      <div class="modal-box">
        <div class="modal-header">
          <h2>🎓 למד את סגנון הכתיבה שלי</h2>
          <button class="modal-close" id="style-modal-close">✕</button>
        </div>
        <div class="modal-form">
          <p style="color:var(--text-secondary);margin-bottom:12px">הדבק כאן מייל שכתבת. המערכת תלמד את הסגנון שלך.</p>
          <div class="form-group">
            <label>גוף המייל שכתבת</label>
            <textarea id="style-sample" rows="10" placeholder="הדבק כאן מייל שכתבת..."></textarea>
          </div>
          <div class="modal-actions">
            <button class="btn btn-primary" id="style-save-btn">שמור וללמוד</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Project modal -->
    <div id="project-modal" class="modal hidden">
      <div class="modal-backdrop"></div>
      <div class="modal-box">
        <div class="modal-header">
          <h2 id="project-modal-title">פרויקט חדש</h2>
          <button class="modal-close" id="project-modal-close">✕</button>
        </div>
        <div class="modal-form">
          <div class="form-group">
            <label>שם הפרויקט</label>
            <input type="text" id="project-name" placeholder="לדוגמה: לקוח X" />
          </div>
          <div class="form-group">
            <label>מילות מפתח (מופרדות בפסיק)</label>
            <input type="text" id="project-keywords" placeholder="חשבונית, הצעת מחיר, לקוח X" />
          </div>
          <div class="form-group">
            <label>צבע</label>
            <input type="color" id="project-color" value="#667eea" style="width:60px;height:36px;padding:2px;border:1px solid var(--border);border-radius:6px;" />
          </div>
          <div class="modal-actions">
            <button class="btn btn-primary" id="project-save-btn">שמור</button>
            <button class="btn btn-ghost" id="project-cancel-btn">ביטול</button>
          </div>
        </div>
      </div>
    </div>
  `;

  initTabs();
  initInbox();
  initCompose();
  initStyleModal();
  initProjectModal();
  loadPendingCount();
}

// ── Tabs ─────────────────────────────────────────────────────────────────────

function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });

  document.getElementById('process-now-btn').onclick = async () => {
    const btn = document.getElementById('process-now-btn');
    btn.textContent = '⏳ מעבד...';
    btn.disabled = true;
    try {
      const r = await api('POST', '/api/email-ai/process-now');
      toast(`עובדו ${r.processed} מיילים חדשים`, 'success');
      loadPendingCount();
      if (currentTab === 'pending') loadPending();
    } catch (e) {
      toast('שגיאה: ' + e.message, 'error');
    } finally {
      btn.textContent = '🔄 עבד מיילים עכשיו';
      btn.disabled = false;
    }
  };
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
  document.getElementById(`tab-${tab}`).classList.remove('hidden');

  if (tab === 'pending') loadPending();
  if (tab === 'projects') loadProjects();
}

async function loadPendingCount() {
  try {
    const items = await api('GET', '/api/email-ai/pending') || [];
    const badge = document.getElementById('pending-badge');
    if (items.length > 0) {
      badge.textContent = items.length;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  } catch (e) { /* ignore */ }
}

// ── Inbox ─────────────────────────────────────────────────────────────────────

let inboxSkip = 0;

async function initInbox() {
  inboxSkip = 0;
  await loadInbox(false);
  document.getElementById('inbox-load-more').onclick = () => loadInbox(true);
}

async function loadInbox(append = false) {
  if (!append) inboxSkip = 0;
  try {
    const msgs = await api('GET', `/api/mail/inbox?top=20&skip=${inboxSkip}`) || [];
    inboxSkip += msgs.length;
    const container = document.getElementById('inbox-items');
    if (!append) container.innerHTML = '';
    if (msgs.length === 0 && !append) {
      container.innerHTML = '<div class="inbox-item text-secondary">תיבת הדואר ריקה</div>';
      return;
    }
    msgs.forEach(msg => {
      const el = document.createElement('div');
      el.className = 'inbox-item' + (msg.is_read ? '' : ' unread');
      el.innerHTML = `
        <div class="inbox-from">${esc(msg.from_name || msg.from_email)}</div>
        <div class="inbox-subject">${esc(msg.subject)}</div>
        <div class="inbox-preview">${esc(msg.body_preview)}</div>
      `;
      el.onclick = () => loadMessage(msg.id, el);
      container.appendChild(el);
    });
  } catch (e) {
    toast('שגיאה בטעינת תיבת הדואר: ' + e.message, 'error');
  }
}

async function loadMessage(id, clickedEl) {
  document.querySelectorAll('.inbox-item.selected').forEach(el => el.classList.remove('selected'));
  clickedEl.classList.add('selected');
  try {
    const msg = await api('GET', `/api/mail/${id}`);
    document.getElementById('compose-to').value = msg.from_email;
    document.getElementById('compose-subject').value = `Re: ${msg.subject}`;
    document.getElementById('compose-request').value = '';
    addAiMessage(`נטענה הודעה מ-${msg.from_name || msg.from_email}: "${msg.subject}". תוכל לבקש ממני לכתוב תגובה.`);
  } catch (e) {
    toast('שגיאה בטעינת ההודעה: ' + e.message, 'error');
  }
}

// ── Pending approvals ─────────────────────────────────────────────────────────

async function loadPending() {
  const container = document.getElementById('pending-list');
  container.innerHTML = '<div class="loading-text" style="padding:32px;text-align:center;">⏳ טוען...</div>';
  try {
    const items = await api('GET', '/api/email-ai/pending') || [];
    if (items.length === 0) {
      container.innerHTML = `
        <div style="text-align:center;padding:48px;color:var(--text-secondary);">
          <div style="font-size:48px;margin-bottom:16px;">✅</div>
          <div>אין מיילים הממתינים לאישור</div>
        </div>`;
      return;
    }
    container.innerHTML = '';
    items.forEach(item => container.appendChild(renderPendingCard(item)));
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
    container.innerHTML = '<div style="padding:32px;color:var(--danger);">שגיאה בטעינה</div>';
  }
}

function renderPendingCard(item) {
  const card = document.createElement('div');
  card.className = 'pending-card';
  card.dataset.id = item.id;
  card.innerHTML = `
    <div class="pending-card-header">
      <div>
        <div class="pending-from">${esc(item.from_name || item.from_email)}</div>
        <div class="pending-subject">${esc(item.subject)}</div>
        <div class="pending-time">${formatDate(item.received_at)}</div>
      </div>
      <div class="pending-actions">
        <button class="btn btn-success btn-small pending-approve" data-id="${item.id}">✅ שלח</button>
        <button class="btn btn-danger btn-small pending-reject" data-id="${item.id}">❌ דחה</button>
      </div>
    </div>
    <div class="pending-draft-label">הצעת תגובה:</div>
    <div class="pending-draft" contenteditable="true" data-id="${item.id}">${item.draft_reply_html || ''}</div>
    <div style="margin-top:8px;">
      <button class="btn btn-ghost btn-small pending-save-edit" data-id="${item.id}">💾 שמור עריכה</button>
    </div>
  `;

  card.querySelector('.pending-approve').onclick = () => approvePending(item.id, card);
  card.querySelector('.pending-reject').onclick = () => rejectPending(item.id, card);
  card.querySelector('.pending-save-edit').onclick = () => saveEditPending(item.id, card);

  return card;
}

async function approvePending(id, card) {
  const btn = card.querySelector('.pending-approve');
  btn.textContent = '⏳';
  btn.disabled = true;
  try {
    await api('POST', `/api/email-ai/${id}/approve`);
    toast('התגובה נשלחה! 📨', 'success');
    card.remove();
    loadPendingCount();
  } catch (e) {
    toast('שגיאה בשליחה: ' + e.message, 'error');
    btn.textContent = '✅ שלח';
    btn.disabled = false;
  }
}

async function rejectPending(id, card) {
  try {
    await api('POST', `/api/email-ai/${id}/reject`);
    toast('נדחה', 'success');
    card.remove();
    loadPendingCount();
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  }
}

async function saveEditPending(id, card) {
  const draftEl = card.querySelector(`.pending-draft[data-id="${id}"]`);
  const html = draftEl.innerHTML;
  try {
    await api('PATCH', `/api/email-ai/${id}`, { draft_reply_html: html });
    toast('נשמר', 'success');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  }
}

// ── Projects ──────────────────────────────────────────────────────────────────

async function loadProjects() {
  const container = document.getElementById('projects-list');
  container.innerHTML = '<div class="loading-text" style="padding:32px;">⏳ טוען...</div>';
  try {
    const projects = await api('GET', '/api/email-projects') || [];
    if (projects.length === 0) {
      container.innerHTML = `
        <div style="text-align:center;padding:48px;color:var(--text-secondary);">
          <div style="font-size:48px;margin-bottom:16px;">📁</div>
          <div>אין פרויקטים עדיין. צור פרויקט חדש כדי לסווג מיילים אוטומטית.</div>
        </div>`;
      return;
    }
    container.innerHTML = '';
    projects.forEach(p => container.appendChild(renderProjectCard(p)));
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  }
}

function renderProjectCard(p) {
  const card = document.createElement('div');
  card.className = 'project-card';
  card.style.borderRightColor = p.color;
  const kw = Array.isArray(p.keywords) ? p.keywords : [];
  card.innerHTML = `
    <div class="project-color-dot" style="background:${p.color}"></div>
    <div class="project-info">
      <div class="project-name">${esc(p.name)}</div>
      <div class="project-keywords">${kw.map(k => `<span class="keyword-tag">${esc(k)}</span>`).join('')}</div>
      ${p.folder_id ? '<div class="project-folder-badge">📁 תיקייה ב-Outlook</div>' : ''}
    </div>
    <button class="btn btn-ghost btn-small project-delete" data-id="${p.id}">🗑</button>
  `;
  card.querySelector('.project-delete').onclick = () => deleteProject(p.id, card);
  return card;
}

async function deleteProject(id, card) {
  if (!confirm('למחוק את הפרויקט?')) return;
  try {
    await api('DELETE', `/api/email-projects/${id}`);
    card.remove();
    toast('נמחק', 'success');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  }
}

// ── Project modal ─────────────────────────────────────────────────────────────

function initProjectModal() {
  const modal = document.getElementById('project-modal');
  document.getElementById('new-project-btn').onclick = () => modal.classList.remove('hidden');
  document.getElementById('project-modal-close').onclick = () => modal.classList.add('hidden');
  document.getElementById('project-cancel-btn').onclick = () => modal.classList.add('hidden');
  modal.querySelector('.modal-backdrop').onclick = () => modal.classList.add('hidden');

  document.getElementById('project-save-btn').onclick = async () => {
    const name = document.getElementById('project-name').value.trim();
    if (!name) { toast('נא להזין שם', 'warning'); return; }
    const kw = document.getElementById('project-keywords').value
      .split(',').map(s => s.trim()).filter(Boolean);
    const color = document.getElementById('project-color').value;

    const btn = document.getElementById('project-save-btn');
    btn.textContent = '⏳ שומר...';
    btn.disabled = true;
    try {
      await api('POST', '/api/email-projects', { name, keywords: kw, color });
      toast('פרויקט נוצר! תיקייה ב-Outlook תיווצר אוטומטית.', 'success');
      modal.classList.add('hidden');
      document.getElementById('project-name').value = '';
      document.getElementById('project-keywords').value = '';
      loadProjects();
    } catch (e) {
      toast('שגיאה: ' + e.message, 'error');
    } finally {
      btn.textContent = 'שמור';
      btn.disabled = false;
    }
  };
}

// ── Compose ───────────────────────────────────────────────────────────────────

function initCompose() {
  document.getElementById('draft-btn').onclick = generateDraft;
  document.getElementById('send-btn').onclick = sendEmail;
  document.getElementById('save-draft-btn').onclick = saveDraftToOutlook;
  document.getElementById('clear-btn').onclick = clearCompose;
  document.getElementById('ai-refine-btn').onclick = refineDraft;
}

async function generateDraft() {
  const request = document.getElementById('compose-request').value.trim();
  if (!request) { toast('נא לתאר מה לכתוב', 'warning'); return; }

  const btn = document.getElementById('draft-btn');
  btn.textContent = '⏳ מייצר...';
  btn.disabled = true;
  try {
    const to = parseRecipients(document.getElementById('compose-to').value);
    const subject = document.getElementById('compose-subject').value;
    const result = await api('POST', '/api/mail/draft', { request, to, subject, context: '' });
    if (!result) return;
    currentDraftId = result.id;
    document.getElementById('draft-body').innerHTML = result.body_html;
    document.getElementById('send-btn').disabled = false;
    document.getElementById('save-draft-btn').disabled = false;
    document.getElementById('ai-refine-btn').disabled = false;
    addAiMessage('הטיוטה מוכנה! תוכל לערוך ישירות, או לבקש ממני שינויים.');
    toast('טיוטה נוצרה', 'success');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  } finally {
    btn.textContent = '✨ ייצר טיוטה עם AI';
    btn.disabled = false;
  }
}

async function refineDraft() {
  if (!currentDraftId) return;
  const instruction = document.getElementById('ai-instruction').value.trim();
  if (!instruction) return;
  const btn = document.getElementById('ai-refine-btn');
  btn.textContent = '⏳';
  btn.disabled = true;
  addAiMessage(`אני: ${instruction}`, true);
  try {
    const result = await api('PATCH', `/api/mail/draft/${currentDraftId}`, { instruction });
    if (result) {
      document.getElementById('draft-body').innerHTML = result.body_html;
      addAiMessage('עדכנתי את הטיוטה לפי הבקשה שלך.');
      document.getElementById('ai-instruction').value = '';
    }
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  } finally {
    btn.textContent = '⚡';
    btn.disabled = false;
  }
}

async function sendEmail() {
  if (!currentDraftId) { toast('אין טיוטה לשליחה', 'warning'); return; }
  const bodyHtml = document.getElementById('draft-body').innerHTML;
  try {
    await api('PATCH', `/api/mail/draft/${currentDraftId}`, { body_html: bodyHtml });
    await api('POST', `/api/mail/draft/${currentDraftId}/send`);
    toast('המייל נשלח בהצלחה! 📨', 'success');
    clearCompose();
    addAiMessage('המייל נשלח! רוצה לכתוב מייל נוסף?');
  } catch (e) {
    toast('שגיאה בשליחה: ' + e.message, 'error');
  }
}

async function saveDraftToOutlook() {
  if (!currentDraftId) return;
  const bodyHtml = document.getElementById('draft-body').innerHTML;
  try {
    await api('PATCH', `/api/mail/draft/${currentDraftId}`, { body_html: bodyHtml });
    toast('טיוטה נשמרה ב-Outlook', 'success');
  } catch (e) {
    toast('שגיאה: ' + e.message, 'error');
  }
}

function clearCompose() {
  currentDraftId = null;
  document.getElementById('compose-to').value = '';
  document.getElementById('compose-subject').value = '';
  document.getElementById('compose-request').value = '';
  document.getElementById('draft-body').innerHTML = '';
  document.getElementById('send-btn').disabled = true;
  document.getElementById('save-draft-btn').disabled = true;
  document.getElementById('ai-refine-btn').disabled = true;
}

// ── Style modal ───────────────────────────────────────────────────────────────

function initStyleModal() {
  document.getElementById('learn-style-btn').onclick = () =>
    document.getElementById('style-modal').classList.remove('hidden');
  document.getElementById('style-modal-close').onclick = () =>
    document.getElementById('style-modal').classList.add('hidden');
  document.querySelector('#style-modal .modal-backdrop').onclick = () =>
    document.getElementById('style-modal').classList.add('hidden');
  document.getElementById('style-save-btn').onclick = async () => {
    const sample = document.getElementById('style-sample').value.trim();
    if (!sample) { toast('נא להדביק מייל לדוגמה', 'warning'); return; }
    try {
      await api('POST', '/api/mail/learn-style', { email_body: sample });
      toast('הסגנון נלמד ונשמר! ✨', 'success');
      document.getElementById('style-modal').classList.add('hidden');
      document.getElementById('style-sample').value = '';
    } catch (e) {
      toast('שגיאה: ' + e.message, 'error');
    }
  };
}

// ── AI Chat ───────────────────────────────────────────────────────────────────

function addAiMessage(text, isUser = false) {
  const chat = document.getElementById('ai-chat');
  if (!chat) return;
  const el = document.createElement('div');
  el.className = 'ai-message' + (isUser ? ' user-msg' : '');
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function parseRecipients(raw) {
  if (!raw.trim()) return [];
  return raw.split(/[,;]/).map(s => s.trim()).filter(Boolean).map(s => {
    const match = s.match(/^(.*?)\s*<(.+)>$/);
    if (match) return { name: match[1].trim(), email: match[2].trim() };
    return { name: s, email: s };
  });
}

function esc(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('he-IL', { dateStyle: 'short', timeStyle: 'short' });
  } catch { return iso; }
}
