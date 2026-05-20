import os
from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Session

import anthropic

from .database import StyleProfile

MODEL = "claude-sonnet-4-6"
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def _get_or_create_style_profile(db: Session) -> StyleProfile:
    profile = db.query(StyleProfile).first()
    if not profile:
        profile = StyleProfile(sample_text="", style_summary="")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def draft_email(db: Session, request: str, context: str = "") -> str:
    profile = _get_or_create_style_profile(db)
    style_desc = profile.style_summary or "כתוב בצורה מקצועית, ישירה ותמציתית בעברית."

    response = _client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=[
            {
                "type": "text",
                "text": (
                    f"אתה עוזרו האישי של המשתמש. כתוב אימייל בסגנון הכתיבה הבא:\n{style_desc}\n\n"
                    "הנחיות:\n"
                    "- כתוב בעברית אלא אם נדרש אחרת\n"
                    "- שמור על הטון והסגנון של המשתמש\n"
                    "- החזר פורמט HTML נקי עם פסקאות (<p> tags)\n"
                    "- אל תוסיף שורת נושא — רק גוף המייל\n"
                    "- אל תוסיף הסברים, רק את גוף המייל עצמו"
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"כתוב מייל לפי הבקשה הבאה:\n{request}"
                + (f"\n\nהקשר נוסף:\n{context}" if context else ""),
            }
        ],
    )
    return response.content[0].text


def improve_draft(current_draft: str, instruction: str) -> str:
    response = _client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": (
                    f"הנה טיוטת מייל:\n\n{current_draft}\n\n"
                    f"שנה אותו לפי ההנחיה הבאה: {instruction}\n\n"
                    "החזר רק את גוף המייל המעודכן בפורמט HTML, ללא הסברים."
                ),
            }
        ],
    )
    return response.content[0].text


def summarize_day(events: list[dict], tasks: list[dict]) -> str:
    today_str = datetime.now().strftime("%A, %d/%m/%Y")
    events_text = "\n".join(
        f"- {e['subject']} ({e['start'][:16] if e['start'] else 'כל היום'})" for e in events
    ) or "אין אירועים להיום"
    tasks_text = "\n".join(
        f"- [{t['status']}] {t['title']}" for t in tasks
    ) or "אין משימות פתוחות"

    response = _client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": (
                    f"תאריך היום: {today_str}\n\n"
                    f"אירועים של היום:\n{events_text}\n\n"
                    f"משימות:\n{tasks_text}\n\n"
                    "כתוב סיכום יום קצר ומסודר בעברית: מה היה, מה נשאר, ומה כדאי לטפל מחר. "
                    "פורמט: כותרות קצרות + נקודות. מקסימום 200 מילים."
                ),
            }
        ],
    )
    return response.content[0].text


def plan_tomorrow(tomorrow_events: list[dict], incomplete_tasks: list[dict]) -> str:
    from datetime import date, timedelta
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%A, %d/%m/%Y")
    events_text = "\n".join(
        f"- {e['subject']} ({e['start'][:16] if e['start'] else 'כל היום'})" for e in tomorrow_events
    ) or "אין אירועים מתוכננים"
    tasks_text = "\n".join(
        f"- {t['title']} (עדיפות: {'גבוהה' if t['priority'] == 1 else 'בינונית' if t['priority'] == 2 else 'נמוכה'})"
        for t in incomplete_tasks
    ) or "אין משימות פתוחות"

    response = _client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": (
                    f"מחר: {tomorrow_str}\n\n"
                    f"אירועים מתוכננים:\n{events_text}\n\n"
                    f"משימות פתוחות:\n{tasks_text}\n\n"
                    "הכן תוכנית יום קצרה ומעשית למחר בעברית. "
                    "כלול: סדר עדיפויות, זמנים מוצעים, ונקודות לתשומת לב. מקסימום 150 מילים."
                ),
            }
        ],
    )
    return response.content[0].text


def suggest_task_priorities(tasks: list[dict]) -> str:
    tasks_text = "\n".join(
        f"{i+1}. {t['title']}" + (f" — {t['description']}" if t.get('description') else "")
        for i, t in enumerate(tasks)
    )
    response = _client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": (
                    f"הנה רשימת משימות:\n{tasks_text}\n\n"
                    "הצע סדר עדיפויות מומלץ בעברית. "
                    "ציין אילו דחופות, אילו ניתן לדחות, ואם יש תלויות בין משימות. "
                    "קצר ומעשי — מקסימום 150 מילים."
                ),
            }
        ],
    )
    return response.content[0].text


def learn_style_from_email(db: Session, email_body: str) -> None:
    profile = _get_or_create_style_profile(db)
    profile.sample_text = (profile.sample_text + "\n\n---\n\n" + email_body).strip()

    # Regenerate style summary when we have enough samples
    if len(profile.sample_text) > 500:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"להלן דוגמאות של מיילים שכתב המשתמש:\n\n{profile.sample_text[:3000]}\n\n"
                        "תאר בקצרה (3-5 משפטים) את סגנון הכתיבה שלו: טון, אורך, פורמליות, "
                        "מאפיינים ייחודיים. תיאור זה ישמש לכתיבת מיילים בשמו."
                    ),
                }
            ],
        )
        profile.style_summary = response.content[0].text

    profile.updated_at = datetime.utcnow()
    db.commit()
