import { api, toast } from './app.js';

export async function initSettings() {
  const container = document.getElementById('view-container');
  container.innerHTML = `<div style="padding:32px;text-align:center;"><span class="loading-text">⏳ טוען...</span></div>`;

  let settings;
  try {
    settings = await api('GET', '/api/settings');
  } catch (e) {
    container.innerHTML = `<div style="color:var(--danger);">שגיאה בטעינת הגדרות</div>`;
    return;
  }

  const appUrl = settings.app_url || window.location.origin;
  const callbackUrl = `${appUrl}/auth/callback`;

  const demoWarning = settings.demo_mode ? `
    <div class="settings-banner warning">
      <strong>⚠️ מצב דמו פעיל</strong> — האפליקציה מציגה נתונים מדומים. כדי לחבר את Outlook האמיתי שלך, בצע את השלבים למטה.
    </div>` : '';

  const connectionStatus = settings.demo_mode
    ? `<div class="settings-status demo">🎭 מצב דמו — לא מחובר ל-Outlook</div>`
    : (settings.azure_configured
        ? `<div class="settings-status connected">✅ Outlook מוגדר — <a href="/auth/login">לחץ כאן להתחבר</a></div>`
        : `<div class="settings-status error">❌ פרטי Azure חסרים — בצע את השלבים למטה</div>`);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">⚙️ הגדרות</div>
    </div>

    ${demoWarning}

    <div class="settings-grid">

      <!-- Connection status card -->
      <div class="card settings-card">
        <div class="card-title">🔗 חיבור ל-Outlook</div>
        ${connectionStatus}

        ${!settings.demo_mode && settings.azure_configured ? `
          <div style="margin-top:16px;">
            <a href="/auth/login" class="btn btn-primary">🔑 התחבר עם חשבון Microsoft</a>
          </div>
        ` : ''}

        <div style="margin-top:16px;padding:12px;background:var(--bg-page);border-radius:var(--radius-sm);font-size:13px;color:var(--text-secondary);">
          <strong>כתובת Callback (לשלב 3):</strong><br>
          <code style="font-size:12px;word-break:break-all;">${callbackUrl}</code>
          <button class="btn btn-ghost btn-small" style="margin-top:6px;" onclick="navigator.clipboard.writeText('${callbackUrl}').then(()=>alert('הועתק!'))">📋 העתק</button>
        </div>
      </div>

      <!-- Step-by-step guide -->
      <div class="card settings-card">
        <div class="card-title">📋 מדריך התחברות — 3 שלבים</div>

        <div class="setup-steps">

          <div class="setup-step">
            <div class="step-number">1</div>
            <div class="step-content">
              <div class="step-title">רשום אפליקציה ב-Azure</div>
              <div class="step-desc">
                <a href="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade" target="_blank" class="btn btn-primary btn-small" style="margin-bottom:8px;">
                  🔗 פתח Azure Portal
                </a>
                <ol class="step-list">
                  <li>שם: <strong>Personal Assistant</strong></li>
                  <li>Supported account types: <strong>Single tenant</strong></li>
                  <li>Redirect URI: <strong>Web</strong> → הדבק את הכתובת מלמעלה</li>
                  <li>לחץ <strong>Register</strong></li>
                </ol>
              </div>
            </div>
          </div>

          <div class="setup-step">
            <div class="step-number">2</div>
            <div class="step-content">
              <div class="step-title">קבל את הפרטים</div>
              <div class="step-desc">
                <ol class="step-list">
                  <li>בדף האפליקציה: העתק <strong>Application (client) ID</strong></li>
                  <li>העתק <strong>Directory (tenant) ID</strong></li>
                  <li>עבור ל-<strong>Certificates & secrets</strong> → New client secret → העתק את ה-Value</li>
                  <li>עבור ל-<strong>API permissions</strong> → Add → Microsoft Graph → Delegated → הוסף:<br>
                    <code>User.Read, Calendars.ReadWrite, Mail.ReadWrite, Mail.Send, offline_access</code>
                  </li>
                  <li>לחץ <strong>Grant admin consent</strong></li>
                </ol>
              </div>
            </div>
          </div>

          <div class="setup-step">
            <div class="step-number">3</div>
            <div class="step-content">
              <div class="step-title">הגדר משתני סביבה ב-Railway</div>
              <div class="step-desc">
                <a href="https://railway.app/project/2e212ae9-5f51-420c-a03f-8b7375db4a97" target="_blank" class="btn btn-primary btn-small" style="margin-bottom:8px;">
                  🚂 פתח Railway
                </a>
                <p style="margin-bottom:8px;">לחץ על השירות → <strong>Variables</strong> → הוסף:</p>
                <table class="vars-table">
                  <tr><td><code>AZURE_CLIENT_ID</code></td><td>ה-Application ID מסעיף 2</td></tr>
                  <tr><td><code>AZURE_CLIENT_SECRET</code></td><td>ה-Secret Value מסעיף 2</td></tr>
                  <tr><td><code>AZURE_TENANT_ID</code></td><td>ה-Directory ID מסעיף 2</td></tr>
                  <tr><td><code>AZURE_REDIRECT_URI</code></td><td><code>${callbackUrl}</code></td></tr>
                  <tr><td><code>ANTHROPIC_API_KEY</code></td><td>מפתח מ-console.anthropic.com</td></tr>
                  <tr><td><code>DEMO_MODE</code></td><td><code>false</code></td></tr>
                </table>
                <p style="margin-top:8px;color:var(--text-secondary);font-size:12px;">לאחר שמירה, Railway יאתחל אוטומטית. חזור לאפליקציה ולחץ "התחבר עם Microsoft".</p>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- API keys status -->
      <div class="card settings-card">
        <div class="card-title">🔑 סטטוס הגדרות</div>
        <div class="settings-checks">
          <div class="check-row">
            <span class="${settings.azure_configured ? 'check-ok' : 'check-miss'}">
              ${settings.azure_configured ? '✅' : '❌'}
            </span>
            <span>Azure App Registration (AZURE_CLIENT_ID / SECRET / TENANT_ID)</span>
          </div>
          <div class="check-row">
            <span class="${settings.anthropic_configured ? 'check-ok' : 'check-miss'}">
              ${settings.anthropic_configured ? '✅' : '❌'}
            </span>
            <span>Anthropic API Key (לתכונות AI)</span>
          </div>
          <div class="check-row">
            <span class="${!settings.demo_mode ? 'check-ok' : 'check-miss'}">
              ${!settings.demo_mode ? '✅' : '⚠️'}
            </span>
            <span>DEMO_MODE=${settings.demo_mode ? 'true (יש לשנות ל-false)' : 'false'}</span>
          </div>
        </div>
      </div>

    </div>
  `;
}
