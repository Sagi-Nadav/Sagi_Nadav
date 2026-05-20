import asyncio
import os
import secrets
from datetime import datetime, date, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, Task, EmailProject, ProcessedEmail
from . import auth, calendar_service, mail_service, tasks_service, ai_service, email_ai_service

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "pa_session")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app = FastAPI(title="עוזר אישי", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        auth.cleanup_old_sessions(db)
    finally:
        db.close()
    if not DEMO_MODE:
        asyncio.create_task(email_ai_service.background_email_loop())


# ── Auth dependency ─────────────────────────────────────────────────────────

def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    return auth.get_current_user(request, db)


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.get("/auth/login")
async def login():
    if DEMO_MODE:
        return RedirectResponse(url="/")
    state = secrets.token_urlsafe(16)
    url = auth.get_auth_url(state)
    return RedirectResponse(url)


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = "", error_description: str = "", db: Session = Depends(get_db)):
    if error:
        return HTMLResponse(f"""<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8"><title>שגיאת כניסה</title>
        <style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f0f2f5}}
        .card{{background:#fff;border-radius:12px;padding:40px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:500px}}</style></head>
        <body><div class="card"><h2 style="color:#e53e3e">שגיאת התחברות</h2>
        <p><strong>{error}</strong></p><p style="color:#718096">{error_description}</p>
        <a href="/auth/login" style="color:#667eea;">נסה שוב</a></div></body></html>""", status_code=400)
    if not code:
        return RedirectResponse(url="/auth/login")
    try:
        token_result = auth.exchange_code_for_token(code)
    except Exception as e:
        return HTMLResponse(f"""<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8"><title>שגיאה</title>
        <style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f0f2f5}}
        .card{{background:#fff;border-radius:12px;padding:40px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:500px}}</style></head>
        <body><div class="card"><h2 style="color:#e53e3e">שגיאה בהתחברות</h2>
        <p style="color:#718096">{str(e)}</p>
        <a href="/auth/login" style="color:#667eea;">נסה שוב</a></div></body></html>""", status_code=400)

    signed_session = auth.create_session(db, token_result)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed_session,
        httponly=True,
        secure=not os.getenv("DEBUG"),
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@app.post("/auth/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.delete_session(request, db)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@app.get("/auth/me")
async def me(request: Request, db: Session = Depends(get_db)):
    if DEMO_MODE:
        return {"authenticated": True, "display_name": auth.DEMO_USER["display_name"], "email": auth.DEMO_USER["email"], "demo": True}
    try:
        user = auth.get_current_user(request, db)
        return {"authenticated": True, "display_name": user["display_name"], "email": user["email"]}
    except HTTPException:
        return {"authenticated": False}


# ── Calendar routes ──────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    subject: str
    start: str
    end: str
    location: Optional[str] = None
    body: Optional[str] = None
    attendees: Optional[list[dict]] = None
    timezone: Optional[str] = "Asia/Jerusalem"
    is_online: Optional[bool] = False


class EventUpdate(BaseModel):
    subject: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    location: Optional[str] = None
    body: Optional[str] = None
    timezone: Optional[str] = "Asia/Jerusalem"


def _demo_events(start_dt: datetime, end_dt: datetime) -> list:
    from datetime import timedelta
    base = start_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    events = []
    for i, (h, title, loc) in enumerate([
        (9, "סטנד-אפ צוות", "Zoom"),
        (11, "פגישת לקוח — Q2 Review", "חדר ישיבות A"),
        (14, "שיחת מנהל", "Teams"),
        (16, "סקירת קוד", ""),
    ]):
        day = base + timedelta(days=i % 5)
        start = day.replace(hour=h)
        if start < start_dt or start > end_dt:
            continue
        events.append({
            "id": f"demo-{i}",
            "subject": title,
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "timezone": "Asia/Jerusalem",
            "is_all_day": False,
            "location": loc,
            "body": "",
            "body_type": "text",
            "attendees": [],
            "organizer_name": "שגיב נדב",
            "organizer_email": "demo@assistant.local",
            "is_cancelled": False,
            "online_meeting_url": None,
        })
    return events


@app.get("/api/calendar/events")
async def list_events(start: str, end: str, user: dict = Depends(current_user)):
    if DEMO_MODE:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        return _demo_events(start_dt, end_dt)
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        events = calendar_service.get_events(user["access_token"], start_dt, end_dt)
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/events/today")
async def today_events(user: dict = Depends(current_user)):
    if DEMO_MODE:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return _demo_events(today, today.replace(hour=23, minute=59))
    try:
        return calendar_service.get_today_events(user["access_token"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calendar/events/{event_id}")
async def get_event(event_id: str, user: dict = Depends(current_user)):
    try:
        return calendar_service.get_event(user["access_token"], event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calendar/events", status_code=201)
async def create_event(data: EventCreate, user: dict = Depends(current_user)):
    try:
        return calendar_service.create_event(user["access_token"], data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/calendar/events/{event_id}")
async def update_event(event_id: str, data: EventUpdate, user: dict = Depends(current_user)):
    try:
        return calendar_service.update_event(user["access_token"], event_id, data.model_dump(exclude_none=True))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/calendar/events/{event_id}", status_code=204)
async def delete_event(event_id: str, user: dict = Depends(current_user)):
    try:
        calendar_service.delete_event(user["access_token"], event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Task routes ──────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 2
    due_date: Optional[str] = None
    week_of: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[str] = None


def _task_to_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "week_of": task.week_of.isoformat() if task.week_of else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@app.get("/api/tasks")
async def list_tasks(week_of: Optional[str] = None, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    wo = date.fromisoformat(week_of) if week_of else None
    return [_task_to_dict(t) for t in tasks_service.get_week_tasks(db, wo)]


@app.get("/api/tasks/today")
async def today_tasks(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [_task_to_dict(t) for t in tasks_service.get_today_tasks(db)]


@app.get("/api/tasks/incomplete")
async def incomplete_tasks(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [_task_to_dict(t) for t in tasks_service.get_incomplete_tasks(db)]


@app.get("/api/tasks/weekly-summary")
async def weekly_summary(week_of: Optional[str] = None, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    wo = date.fromisoformat(week_of) if week_of else None
    return tasks_service.get_weekly_summary(db, wo)


@app.post("/api/tasks", status_code=201)
async def create_task(data: TaskCreate, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    due = datetime.fromisoformat(data.due_date) if data.due_date else None
    wo = date.fromisoformat(data.week_of) if data.week_of else None
    task = tasks_service.create_task(db, data.title, data.description, data.priority, due, wo)
    return _task_to_dict(task)


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, data: TaskUpdate, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_none=True)
    if "due_date" in updates and updates["due_date"]:
        updates["due_date"] = datetime.fromisoformat(updates["due_date"])
    try:
        task = tasks_service.update_task(db, task_id, **updates)
        return _task_to_dict(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    tasks_service.delete_task(db, task_id)


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    try:
        task = tasks_service.complete_task(db, task_id)
        return _task_to_dict(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Mail routes ──────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    request: str
    to: Optional[list[dict]] = None
    subject: Optional[str] = None
    context: Optional[str] = ""


class DraftRevise(BaseModel):
    instruction: Optional[str] = None
    body_html: Optional[str] = None
    subject: Optional[str] = None
    to_recipients: Optional[list[dict]] = None


class StyleSample(BaseModel):
    email_body: str


@app.get("/api/mail/inbox")
async def inbox(top: int = 20, skip: int = 0, user: dict = Depends(current_user)):
    if DEMO_MODE:
        return [
            {"id": "demo-1", "subject": "Re: הצעת מחיר Q2", "from_name": "דוד כהן", "from_email": "david@example.com", "received_at": "2025-05-07T08:30:00", "is_read": False, "body_preview": "שלום, בדקתי את ההצעה ויש לי כמה שאלות...", "body": "<p>שלום,<br>בדקתי את ההצעה ויש לי כמה שאלות לגבי הסעיף השלישי.</p>", "body_type": "html", "is_draft": False, "has_attachments": False},
            {"id": "demo-2", "subject": "פגישה מחר 10:00", "from_name": "שרה לוי", "from_email": "sarah@example.com", "received_at": "2025-05-07T07:15:00", "is_read": True, "body_preview": "אשמח לאשר את הפגישה...", "body": "<p>אשמח לאשר את הפגישה מחר בשעה 10:00.</p>", "body_type": "html", "is_draft": False, "has_attachments": False},
            {"id": "demo-3", "subject": "דוח חודשי — אפריל 2025", "from_name": "מנהלת חשבונות", "from_email": "accounts@example.com", "received_at": "2025-05-06T16:00:00", "is_read": True, "body_preview": "מצ\"ב הדוח החודשי לאפריל...", "body": "<p>מצ\"ב הדוח החודשי לאפריל 2025.</p>", "body_type": "html", "is_draft": False, "has_attachments": True},
        ]
    try:
        return mail_service.list_inbox(user["access_token"], top, skip)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mail/{message_id}")
async def get_mail(message_id: str, user: dict = Depends(current_user)):
    try:
        return mail_service.get_message(user["access_token"], message_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mail/draft", status_code=201)
async def create_mail_draft(data: DraftRequest, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    body_html = ai_service.draft_email(db, data.request, data.context or "")
    to = data.to or []
    subject = data.subject or ""

    # Save draft in Microsoft
    ms_draft = None
    if to and subject:
        try:
            ms_draft = mail_service.create_draft(user["access_token"], subject, to, body_html)
        except Exception:
            pass

    # Save locally
    from .database import EmailDraft
    import json
    local = EmailDraft(
        subject=subject,
        to_recipients=json.dumps(to),
        body_html=body_html,
        ms_message_id=ms_draft["id"] if ms_draft else None,
    )
    db.add(local)
    db.commit()
    db.refresh(local)

    return {
        "id": local.id,
        "ms_message_id": local.ms_message_id,
        "subject": subject,
        "to": to,
        "body_html": body_html,
    }


@app.patch("/api/mail/draft/{draft_id}")
async def revise_draft(draft_id: int, data: DraftRevise, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from .database import EmailDraft
    import json
    local = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not local:
        raise HTTPException(status_code=404, detail="Draft not found")

    new_body = local.body_html
    if data.instruction:
        new_body = ai_service.improve_draft(local.body_html, data.instruction)
    elif data.body_html:
        new_body = data.body_html

    local.body_html = new_body
    if data.subject:
        local.subject = data.subject
    if data.to_recipients:
        local.to_recipients = json.dumps(data.to_recipients)
    db.commit()

    # Sync to Microsoft if linked
    if local.ms_message_id:
        try:
            updates = {"body_html": new_body}
            if data.subject:
                updates["subject"] = data.subject
            mail_service.update_draft(user["access_token"], local.ms_message_id, updates)
        except Exception:
            pass

    return {"id": local.id, "body_html": local.body_html, "subject": local.subject}


@app.post("/api/mail/draft/{draft_id}/send")
async def send_draft(draft_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from .database import EmailDraft
    import json
    local = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not local:
        raise HTTPException(status_code=404, detail="Draft not found")

    to = json.loads(local.to_recipients)

    if local.ms_message_id:
        # Update body then send
        mail_service.update_draft(user["access_token"], local.ms_message_id, {"body_html": local.body_html})
        mail_service.send_draft(user["access_token"], local.ms_message_id)
    else:
        mail_service.send_new(user["access_token"], local.subject or "", to, local.body_html)

    local.status = "sent"
    db.commit()
    return {"ok": True}


@app.post("/api/mail/learn-style")
async def learn_style(data: StyleSample, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    ai_service.learn_style_from_email(db, data.email_body)
    return {"ok": True}


# ── AI routes ────────────────────────────────────────────────────────────────

@app.get("/api/ai/day-summary")
async def day_summary(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    events = calendar_service.get_today_events(user["access_token"])
    tasks = [_task_to_dict(t) for t in tasks_service.get_incomplete_tasks(db)]
    summary = ai_service.summarize_day(events, tasks)
    return {"summary": summary}


@app.get("/api/ai/tomorrow-plan")
async def tomorrow_plan(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    tomorrow_start = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
    tomorrow_end = tomorrow_start + timedelta(days=1)
    events = calendar_service.get_events(user["access_token"], tomorrow_start, tomorrow_end)
    tasks = [_task_to_dict(t) for t in tasks_service.get_incomplete_tasks(db)]
    plan = ai_service.plan_tomorrow(events, tasks)
    return {"plan": plan}


@app.get("/api/ai/morning-briefing")
async def morning_briefing_now(user: dict = Depends(current_user)):
    if DEMO_MODE:
        return {"ok": True, "demo": True}
    try:
        email_ai_service.send_morning_briefing(user["access_token"], user["email"])
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/eod-summary")
async def eod_summary_now(user: dict = Depends(current_user)):
    if DEMO_MODE:
        return {"ok": True, "demo": True}
    try:
        email_ai_service.send_eod_summary(user["access_token"], user["email"])
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/weekly-summary")
async def weekly_summary_now(user: dict = Depends(current_user)):
    if DEMO_MODE:
        return {"ok": True, "demo": True}
    try:
        email_ai_service.send_weekly_summary(user["access_token"], user["email"])
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SlotRequest(BaseModel):
    duration_minutes: int = 60
    days_ahead: int = 7


@app.post("/api/calendar/free-slots")
async def free_slots(data: SlotRequest, user: dict = Depends(current_user)):
    if DEMO_MODE:
        from datetime import date, timedelta
        base = datetime.now().replace(minute=0, second=0) + timedelta(hours=2)
        return [
            {"start": (base + timedelta(hours=i*3)).isoformat(),
             "end": (base + timedelta(hours=i*3+1)).isoformat(),
             "label": f"מחר בשעה {(base + timedelta(hours=i*3)).strftime('%H:%M')}–{(base + timedelta(hours=i*3+1)).strftime('%H:%M')}"}
            for i in range(3)
        ]
    try:
        return calendar_service.get_free_slots(user["access_token"], data.duration_minutes, data.days_ahead)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calendar/parse-natural")
async def parse_natural(request: Request, user: dict = Depends(current_user)):
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    try:
        result = calendar_service.parse_natural_event(text)
        return result or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/suggest-priorities")
async def suggest_priorities(tasks: list[dict], user: dict = Depends(current_user)):
    suggestion = ai_service.suggest_task_priorities(tasks)
    return {"suggestion": suggestion}


@app.get("/api/settings")
async def get_settings():
    return {
        "demo_mode": DEMO_MODE,
        "azure_configured": bool(
            os.getenv("AZURE_CLIENT_ID") and
            os.getenv("AZURE_CLIENT_SECRET") and
            os.getenv("AZURE_TENANT_ID")
        ),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "app_url": os.getenv("APP_URL", ""),
        "redirect_uri": os.getenv("AZURE_REDIRECT_URI", ""),
    }


# ── Email projects ────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    keywords: list[str] = []
    color: str = "#667eea"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    keywords: Optional[list[str]] = None
    color: Optional[str] = None


def _project_to_dict(p: EmailProject) -> dict:
    import json as _json
    kw = p.keywords
    if isinstance(kw, str):
        try:
            kw = _json.loads(kw)
        except Exception:
            kw = []
    return {
        "id": p.id,
        "name": p.name,
        "keywords": kw,
        "folder_id": p.folder_id,
        "color": p.color,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@app.get("/api/email-projects")
async def list_projects(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [_project_to_dict(p) for p in db.query(EmailProject).all()]


@app.post("/api/email-projects", status_code=201)
async def create_project(data: ProjectCreate, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    import json as _json
    p = EmailProject(name=data.name, keywords=_json.dumps(data.keywords), color=data.color)
    db.add(p)
    db.commit()
    db.refresh(p)

    # Create matching folder in Outlook (best-effort)
    if not DEMO_MODE:
        try:
            folder = mail_service.create_folder(user["access_token"], data.name)
            p.folder_id = folder["id"]
            db.commit()
        except Exception:
            pass

    return _project_to_dict(p)


@app.patch("/api/email-projects/{project_id}")
async def update_project(project_id: int, data: ProjectUpdate, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    import json as _json
    p = db.query(EmailProject).filter(EmailProject.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if data.name is not None:
        p.name = data.name
    if data.keywords is not None:
        p.keywords = _json.dumps(data.keywords)
    if data.color is not None:
        p.color = data.color
    db.commit()
    return _project_to_dict(p)


@app.delete("/api/email-projects/{project_id}", status_code=204)
async def delete_project(project_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    p = db.query(EmailProject).filter(EmailProject.id == project_id).first()
    if p:
        db.delete(p)
        db.commit()


# ── Email AI management ───────────────────────────────────────────────────────

def _processed_to_dict(e: ProcessedEmail) -> dict:
    return {
        "id": e.id,
        "ms_message_id": e.ms_message_id,
        "subject": e.subject,
        "from_email": e.from_email,
        "from_name": e.from_name,
        "received_at": e.received_at.isoformat() if e.received_at else None,
        "project_id": e.project_id,
        "draft_reply_html": e.draft_reply_html,
        "status": e.status,
        "notification_sent": e.notification_sent,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@app.get("/api/email-ai/pending")
async def pending_emails(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if DEMO_MODE:
        return [
            {
                "id": 1,
                "ms_message_id": "demo-msg-1",
                "subject": "Re: הצעת מחיר Q2",
                "from_email": "david@example.com",
                "from_name": "דוד כהן",
                "received_at": "2025-05-07T08:30:00",
                "project_id": None,
                "draft_reply_html": "<p>שלום דוד,<br>תודה על פנייתך. אשמח לענות על שאלותיך לגבי סעיף שלוש. ניתן לתאם שיחה מחר בשעות הבוקר?<br>תודה, שגיב</p>",
                "status": "pending",
                "notification_sent": True,
                "created_at": "2025-05-07T09:00:00",
            }
        ]
    rows = db.query(ProcessedEmail).filter(ProcessedEmail.status == "pending").order_by(ProcessedEmail.created_at.desc()).all()
    return [_processed_to_dict(r) for r in rows]


@app.patch("/api/email-ai/{email_id}")
async def update_processed_email(email_id: int, data: dict, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(ProcessedEmail).filter(ProcessedEmail.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if "draft_reply_html" in data:
        row.draft_reply_html = data["draft_reply_html"]
    if "project_id" in data:
        row.project_id = data["project_id"]
    db.commit()
    return _processed_to_dict(row)


@app.post("/api/email-ai/{email_id}/approve")
async def approve_email_reply(email_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(ProcessedEmail).filter(ProcessedEmail.id == email_id).first()
    if not row or not row.draft_reply_html:
        raise HTTPException(status_code=404, detail="Not found")
    if DEMO_MODE:
        row.status = "sent"
        db.commit()
        return {"ok": True, "demo": True}
    try:
        mail_service.send_new(
            user["access_token"],
            f"Re: {row.subject}",
            [{"email": row.from_email, "name": row.from_name}],
            row.draft_reply_html,
        )
        row.status = "sent"
        db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email-ai/{email_id}/reject")
async def reject_email_reply(email_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(ProcessedEmail).filter(ProcessedEmail.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.status = "rejected"
    db.commit()
    return {"ok": True}


@app.post("/api/email-ai/process-now")
async def process_now(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if DEMO_MODE:
        return {"processed": 0, "demo": True}
    count = email_ai_service.process_new_emails(db)
    return {"processed": count}


# ── Public token-based approve / reject (from notification email links) ───────

def _approval_html(title: str, message: str, color: str) -> str:
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>{title}</title>
<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f0f2f5}}
.card{{background:#fff;border-radius:12px;padding:40px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:400px}}
h2{{color:{color}}}p{{color:#555}}</style></head>
<body><div class="card"><h2>{title}</h2><p>{message}</p>
<a href="/" style="color:#667eea;">חזרה ללוח הניהול</a></div></body></html>"""


@app.get("/api/approve/{token}", response_class=HTMLResponse)
async def approve_by_token(token: str, db: Session = Depends(get_db)):
    row = db.query(ProcessedEmail).filter(ProcessedEmail.approval_token == token).first()
    if not row:
        return HTMLResponse(_approval_html("שגיאה", "קישור לא תקין או שפג תוקפו.", "#dc3545"), status_code=404)
    if row.status not in ("pending",):
        label = {"sent": "נשלחה כבר", "rejected": "נדחתה"}.get(row.status, row.status)
        return HTMLResponse(_approval_html("כבר טופל", f"התגובה {label}.", "#667eea"))

    # Get active session token to send the reply
    active = email_ai_service._get_active_session(db)
    if not active:
        return HTMLResponse(_approval_html("שגיאה", "לא נמצאה הפעלה פעילה. אנא התחבר ואשר מלוח הניהול.", "#dc3545"), status_code=401)

    try:
        mail_service.send_new(
            active["access_token"],
            f"Re: {row.subject}",
            [{"email": row.from_email, "name": row.from_name}],
            row.draft_reply_html,
        )
        row.status = "sent"
        db.commit()
        return HTMLResponse(_approval_html("נשלח! ✅", f"התגובה לאימייל '{row.subject}' נשלחה בהצלחה.", "#28a745"))
    except Exception as e:
        return HTMLResponse(_approval_html("שגיאה בשליחה", str(e), "#dc3545"), status_code=500)


@app.get("/api/reject/{token}", response_class=HTMLResponse)
async def reject_by_token(token: str, db: Session = Depends(get_db)):
    row = db.query(ProcessedEmail).filter(ProcessedEmail.approval_token == token).first()
    if not row:
        return HTMLResponse(_approval_html("שגיאה", "קישור לא תקין.", "#dc3545"), status_code=404)
    row.status = "rejected"
    db.commit()
    return HTMLResponse(_approval_html("נדחה ❌", f"התגובה לאימייל '{row.subject}' נדחתה.", "#dc3545"))


# ── Static files (SPA) — must be last ───────────────────────────────────────

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
