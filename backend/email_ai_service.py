"""AI-driven email management: classify, draft replies, notify user for approval."""
import asyncio
import json
import os
import secrets
from datetime import datetime
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from .database import EmailProject, ProcessedEmail, SessionStore, get_db
from . import mail_service

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

STYLE_PROMPT = (
    "אתה עוזרו האישי של שגיב נדב. כתוב תגובה לאימייל שקיבל.\n"
    "סגנון: רשמי וידידותי גם יחד — מקצועי אך חם, ישיר ותמציתי.\n"
    "אם האימייל הוא newsletter, פרסומת, קבלה, אישור אוטומטי, התראת מערכת, או spam — ענה רק: DELETE\n"
    "אחרת, כתוב תגובה בעברית בפורמט HTML עם פסקאות <p>. "
    "אל תוסיף חתימה של 'שגיב נדב' — היא תתווסף אוטומטית."
)


# ── Classification ────────────────────────────────────────────────────────────

def classify_email(db: Session, subject: str, body_preview: str) -> Optional[int]:
    """Return matching EmailProject.id or None."""
    projects = db.query(EmailProject).all()
    if not projects:
        return None
    project_list = "\n".join(
        f"- id={p.id} name='{p.name}' keywords={p.keywords}"
        for p in projects
    )
    try:
        resp = _client.messages.create(
            model=MODEL, max_tokens=50,
            messages=[{"role": "user", "content": (
                f"בחר איזה פרויקט מתאים לאימייל. ענה רק במספר id או 'none'.\n\n"
                f"פרויקטים:\n{project_list}\n\n"
                f"נושא: {subject}\nתוכן: {body_preview[:400]}"
            )}],
        )
        text = resp.content[0].text.strip().lower()
        if text == "none":
            return None
        pid = int(text)
        if any(p.id == pid for p in projects):
            return pid
    except Exception:
        pass
    return None


# ── Meeting request detection ─────────────────────────────────────────────────

def detect_meeting_request(subject: str, body: str) -> bool:
    """Return True if the email is requesting a meeting."""
    keywords = ["פגישה", "לקבוע", "להיפגש", "meeting", "schedule", "available", "זמינות", "תאריך"]
    text = (subject + " " + body[:500]).lower()
    return any(kw in text for kw in keywords)


def format_slots_in_reply(slots: list[dict]) -> str:
    """Embed meeting slot suggestions in HTML for the reply."""
    if not slots:
        return ""
    items = "".join(f"<li>{s['label']}</li>" for s in slots[:3])
    return (
        f"<p>להלן מספר אפשרויות זמינות לפגישה:</p>"
        f"<ul>{items}</ul>"
        f"<p>אשמח לדעת מה מתאים לך.</p>"
    )


# ── Draft reply ───────────────────────────────────────────────────────────────

def draft_reply(subject: str, from_name: str, from_email: str, body: str,
                free_slots: list[dict] | None = None) -> Optional[str]:
    """Generate HTML reply. Returns None if no reply needed, 'DELETE' marker for junk."""
    try:
        resp = _client.messages.create(
            model=MODEL, max_tokens=1000,
            system=STYLE_PROMPT,
            messages=[{"role": "user", "content": (
                f"מאת: {from_name} <{from_email}>\n"
                f"נושא: {subject}\n\n"
                f"{body[:2000]}"
            )}],
        )
        text = resp.content[0].text.strip()
    except Exception:
        return None

    if text.upper().startswith("DELETE"):
        return "DELETE"

    # Append meeting slots if this is a meeting request
    if free_slots:
        text += "\n" + format_slots_in_reply(free_slots)

    return text


# ── Notification email ────────────────────────────────────────────────────────

def send_notification(access_token: str, user_email: str, processed: "ProcessedEmail",
                      draft_html: str, original_subject: str, from_display: str) -> None:
    approve_url = f"{APP_URL}/api/approve/{processed.approval_token}"
    reject_url = f"{APP_URL}/api/reject/{processed.approval_token}"
    body = f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:600px;">
  <h2 style="color:#667eea;">📧 הצעת תגובה לאימייל חדש</h2>
  <table style="border-collapse:collapse;width:100%;margin-bottom:16px;">
    <tr><td style="padding:4px 8px;font-weight:bold;">מאת:</td><td style="padding:4px 8px;">{from_display}</td></tr>
    <tr><td style="padding:4px 8px;font-weight:bold;">נושא:</td><td style="padding:4px 8px;">{original_subject}</td></tr>
  </table>
  <h3 style="color:#333;">הצעת תגובה:</h3>
  <div style="background:#f8f9fa;border-right:4px solid #667eea;padding:16px;margin:16px 0;">
    {draft_html}
  </div>
  <div style="margin-top:24px;text-align:center;">
    <a href="{approve_url}" style="background:#28a745;color:#fff;padding:12px 32px;text-decoration:none;border-radius:6px;font-size:16px;margin-left:16px;">✅ שלח תגובה</a>
    <a href="{reject_url}" style="background:#dc3545;color:#fff;padding:12px 32px;text-decoration:none;border-radius:6px;font-size:16px;">❌ דחה</a>
  </div>
  <p style="color:#999;font-size:12px;margin-top:24px;">
    ניתן גם לנהל ב<a href="{APP_URL}/#email">לוח הניהול</a>.
  </p>
</div>"""
    mail_service.send_new(
        access_token,
        f"[עוזר אישי] תגובה מוצעת: {original_subject}",
        [{"email": user_email, "name": "שגיב נדב"}],
        body,
    )


# ── Daily briefing ────────────────────────────────────────────────────────────

def send_morning_briefing(access_token: str, user_email: str) -> None:
    """Send morning email with today's calendar + pending emails."""
    from . import calendar_service
    from .database import SessionLocal
    db = SessionLocal()
    try:
        events = calendar_service.get_today_events(access_token)
        pending = db.query(ProcessedEmail).filter(ProcessedEmail.status == "pending").count()
    except Exception:
        events, pending = [], 0
    finally:
        db.close()

    from datetime import date
    today_str = date.today().strftime("%d/%m/%Y")
    days_he = ["שני", "שלישי", "רביעי", "חמישי", "ראשון", "שישי", "שבת"]
    day_name = days_he[date.today().weekday()]

    events_html = "".join(
        f"<li><strong>{e['start'][11:16] if e['start'] and len(e['start']) > 10 else 'כל היום'}</strong> — {e['subject']}"
        + (f" 📍{e['location']}" if e.get('location') else "") + "</li>"
        for e in events
    ) or "<li>אין אירועים מתוכננים להיום 🎉</li>"

    pending_html = f"<p>📬 יש לך <strong>{pending}</strong> מיילים הממתינים לאישורך.</p>" if pending else ""

    body = f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:600px;">
  <h2 style="color:#667eea;">☀️ בוקר טוב! סיכום יום {day_name}, {today_str}</h2>
  <h3>📆 לוח זמנים להיום</h3>
  <ul style="line-height:2;">{events_html}</ul>
  {pending_html}
  <p style="margin-top:24px;">
    <a href="{APP_URL}" style="background:#667eea;color:#fff;padding:10px 24px;text-decoration:none;border-radius:6px;">פתח את הלוח</a>
  </p>
</div>"""
    mail_service.send_new(access_token, f"☀️ סיכום בוקר — {today_str}",
                          [{"email": user_email}], body)


def send_eod_summary(access_token: str, user_email: str) -> None:
    """Send end-of-day summary with tomorrow's agenda."""
    from . import calendar_service, ai_service
    from .database import SessionLocal
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        today_events = calendar_service.get_today_events(access_token)
        tomorrow_start = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
        tomorrow_events = calendar_service.get_events(access_token, tomorrow_start, tomorrow_start + timedelta(days=1))
        pending_count = db.query(ProcessedEmail).filter(ProcessedEmail.status == "pending").count()
    except Exception:
        today_events, tomorrow_events, pending_count = [], [], 0
    finally:
        db.close()

    tomorrow_html = "".join(
        f"<li><strong>{e['start'][11:16] if e['start'] and len(e['start']) > 10 else 'כל היום'}</strong> — {e['subject']}</li>"
        for e in tomorrow_events
    ) or "<li>אין אירועים מתוכננים למחר</li>"

    today_str = date.today().strftime("%d/%m/%Y")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")

    body = f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:600px;">
  <h2 style="color:#764ba2;">🌆 סיכום סוף יום — {today_str}</h2>
  <p>סיימת את יום העבודה עם {len(today_events)} אירועים.</p>
  <h3>📅 מחר ({tomorrow_str})</h3>
  <ul style="line-height:2;">{tomorrow_html}</ul>
  {"<p>📬 תזכורת: יש לך " + str(pending_count) + " מיילים הממתינים לאישורך.</p>" if pending_count else ""}
  <p style="margin-top:24px;">
    <a href="{APP_URL}" style="background:#764ba2;color:#fff;padding:10px 24px;text-decoration:none;border-radius:6px;">פתח את הלוח</a>
  </p>
</div>"""
    mail_service.send_new(access_token, f"🌆 סיכום סוף יום — {today_str}",
                          [{"email": user_email}], body)


def send_weekly_summary(access_token: str, user_email: str) -> None:
    """Send weekly summary every Sunday morning."""
    from . import calendar_service
    from datetime import date, timedelta
    today = date.today()
    week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    try:
        events = calendar_service.get_events(access_token, week_start, week_end)
    except Exception:
        events = []

    events_html = "".join(
        f"<li>{e['start'][:10] if e['start'] else ''} {e['start'][11:16] if e['start'] and len(e['start'])>10 else ''} — {e['subject']}</li>"
        for e in events
    ) or "<li>אין אירועים השבוע</li>"

    body = f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:600px;">
  <h2 style="color:#667eea;">📋 סיכום שבועי — שבוע {today.strftime('%d/%m/%Y')}</h2>
  <h3>📆 אירועים השבוע ({len(events)})</h3>
  <ul style="line-height:2;">{events_html}</ul>
  <p style="margin-top:24px;">
    <a href="{APP_URL}" style="background:#667eea;color:#fff;padding:10px 24px;text-decoration:none;border-radius:6px;">פתח את הלוח</a>
  </p>
</div>"""
    mail_service.send_new(access_token, f"📋 סיכום שבועי — {today.strftime('%d/%m/%Y')}",
                          [{"email": user_email}], body)


# ── Active session helper ─────────────────────────────────────────────────────

def _get_active_session(db: Session) -> Optional[dict]:
    from . import auth as _auth
    row = (
        db.query(SessionStore)
        .filter(SessionStore.user_id != "demo-user")
        .order_by(SessionStore.last_seen.desc())
        .first()
    )
    if not row:
        return None
    try:
        token = _auth.decrypt_token(row.access_token)
        return {"access_token": token, "email": row.email, "display_name": row.display_name}
    except Exception:
        return None


# ── Main processing loop ──────────────────────────────────────────────────────

def process_new_emails(db: Session) -> int:
    """Fetch unread emails, classify, draft replies, send notifications."""
    from . import calendar_service
    session = _get_active_session(db)
    if not session:
        return 0

    token = session["access_token"]
    user_email = session["email"]

    try:
        messages = mail_service.list_unread(token, top=30)
    except Exception:
        return 0

    count = 0
    for msg in messages:
        ms_id = msg["id"]
        if db.query(ProcessedEmail).filter(ProcessedEmail.ms_message_id == ms_id).first():
            continue

        subject = msg.get("subject", "")
        from_email = msg.get("from_email", "")
        from_name = msg.get("from_name", "")
        body = msg.get("body") or msg.get("body_preview", "")
        received_raw = msg.get("received_at")
        received_at = None
        if received_raw:
            try:
                received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Classify to project
        project_id = classify_email(db, subject, body)
        if project_id:
            project = db.query(EmailProject).filter(EmailProject.id == project_id).first()
            if project and project.folder_id:
                try:
                    mail_service.move_message(token, ms_id, project.folder_id)
                except Exception:
                    pass

        # Detect meeting request → get free slots
        free_slots = None
        if detect_meeting_request(subject, body):
            try:
                free_slots = calendar_service.get_free_slots(token, duration_minutes=60)
            except Exception:
                free_slots = []

        # Draft reply
        draft_html = draft_reply(subject, from_name, from_email, body, free_slots)

        # DELETE = junk, trash it
        if draft_html == "DELETE":
            try:
                mail_service.delete_message(token, ms_id)
            except Exception:
                pass
            record = ProcessedEmail(
                ms_message_id=ms_id, subject=subject, from_email=from_email,
                from_name=from_name, received_at=received_at, project_id=project_id,
                status="no_reply_needed", notification_sent=False,
            )
            db.add(record)
            db.commit()
            count += 1
            continue

        approval_token = secrets.token_urlsafe(32) if draft_html else None
        record = ProcessedEmail(
            ms_message_id=ms_id, subject=subject, from_email=from_email,
            from_name=from_name, received_at=received_at, project_id=project_id,
            draft_reply_html=draft_html, approval_token=approval_token,
            status="pending" if draft_html else "no_reply_needed",
            notification_sent=False,
        )
        db.add(record)
        db.flush()

        if draft_html and approval_token:
            try:
                send_notification(token, user_email, record, draft_html, subject,
                                  f"{from_name} <{from_email}>" if from_name else from_email)
                record.notification_sent = True
            except Exception:
                pass

        db.commit()
        count += 1

    return count


# ── Background loop ───────────────────────────────────────────────────────────

async def background_email_loop():
    """Every 10 min: process emails. At 08:00 morning briefing. At 17:00 EOD. Sunday 08:00 weekly."""
    last_morning = None
    last_eod = None
    last_weekly = None

    while True:
        await asyncio.sleep(10 * 60)
        now = datetime.now()
        db = next(get_db())
        try:
            session = _get_active_session(db)

            # Process new emails
            process_new_emails(db)

            if session:
                token = session["access_token"]
                email = session["email"]
                today = now.date()

                # Morning briefing at 08:00
                if now.hour == 8 and last_morning != today:
                    try:
                        send_morning_briefing(token, email)
                        last_morning = today
                    except Exception:
                        pass

                # EOD summary at 17:00
                if now.hour == 17 and last_eod != today:
                    try:
                        send_eod_summary(token, email)
                        last_eod = today
                    except Exception:
                        pass

                # Weekly summary Sunday at 08:00 (weekday 6)
                if now.weekday() == 6 and now.hour == 8 and last_weekly != today:
                    try:
                        send_weekly_summary(token, email)
                        last_weekly = today
                    except Exception:
                        pass

        except Exception:
            pass
        finally:
            db.close()
