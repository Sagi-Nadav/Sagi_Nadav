"""
calendar_service.py — Microsoft Graph calendar operations + free slot finder
"""
from datetime import datetime, date, timedelta
from typing import Optional
import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
WORK_START = 9   # 09:00
WORK_END = 16    # 16:00


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _normalize_event(ev: dict) -> dict:
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id"),
        "subject": ev.get("subject", "(ללא נושא)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "timezone": start.get("timeZone", "UTC"),
        "is_all_day": ev.get("isAllDay", False),
        "location": ev.get("location", {}).get("displayName", ""),
        "body": ev.get("body", {}).get("content", ""),
        "body_type": ev.get("body", {}).get("contentType", "text"),
        "attendees": [
            {
                "name": a.get("emailAddress", {}).get("name", ""),
                "email": a.get("emailAddress", {}).get("address", ""),
                "status": a.get("status", {}).get("response", ""),
            }
            for a in ev.get("attendees", [])
        ],
        "organizer_name": ev.get("organizer", {}).get("emailAddress", {}).get("name", ""),
        "organizer_email": ev.get("organizer", {}).get("emailAddress", {}).get("address", ""),
        "is_cancelled": ev.get("isCancelled", False),
        "online_meeting_url": ev.get("onlineMeeting", {}).get("joinUrl") if ev.get("onlineMeeting") else None,
    }


def get_events(access_token: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    url = (
        f"{GRAPH_BASE}/me/calendarView"
        f"?startDateTime={start_str}&endDateTime={end_str}"
        f"&$orderby=start/dateTime&$top=100"
        f"&$select=id,subject,start,end,isAllDay,location,body,attendees,organizer,isCancelled,onlineMeeting"
    )
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return [_normalize_event(e) for e in resp.json().get("value", [])]


def get_today_events(access_token: str) -> list[dict]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return get_events(access_token, today, tomorrow)


def get_event(access_token: str, event_id: str) -> dict:
    url = f"{GRAPH_BASE}/me/events/{event_id}"
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return _normalize_event(resp.json())


def create_event(access_token: str, data: dict) -> dict:
    body = {
        "subject": data["subject"],
        "start": {"dateTime": data["start"], "timeZone": data.get("timezone", "Asia/Jerusalem")},
        "end": {"dateTime": data["end"], "timeZone": data.get("timezone", "Asia/Jerusalem")},
    }
    if data.get("location"):
        body["location"] = {"displayName": data["location"]}
    if data.get("body"):
        body["body"] = {"contentType": "HTML", "content": data["body"]}
    if data.get("attendees"):
        body["attendees"] = [
            {
                "emailAddress": {"address": a["email"], "name": a.get("name", a["email"])},
                "type": "required",
            }
            for a in data["attendees"]
        ]
    if data.get("is_online"):
        body["isOnlineMeeting"] = True
        body["onlineMeetingProvider"] = "teamsForBusiness"

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{GRAPH_BASE}/me/events", headers=_headers(access_token), json=body)
        resp.raise_for_status()
    return _normalize_event(resp.json())


def update_event(access_token: str, event_id: str, data: dict) -> dict:
    body = {}
    if "subject" in data:
        body["subject"] = data["subject"]
    if "start" in data:
        body["start"] = {"dateTime": data["start"], "timeZone": data.get("timezone", "Asia/Jerusalem")}
    if "end" in data:
        body["end"] = {"dateTime": data["end"], "timeZone": data.get("timezone", "Asia/Jerusalem")}
    if "location" in data:
        body["location"] = {"displayName": data["location"]}
    if "body" in data:
        body["body"] = {"contentType": "HTML", "content": data["body"]}

    with httpx.Client(timeout=30) as client:
        resp = client.patch(f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(access_token), json=body)
        resp.raise_for_status()
    return _normalize_event(resp.json())


def delete_event(access_token: str, event_id: str) -> None:
    with httpx.Client(timeout=30) as client:
        resp = client.delete(f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(access_token))
        resp.raise_for_status()


def get_free_slots(access_token: str, duration_minutes: int = 60, days_ahead: int = 7) -> list[dict]:
    """Find free meeting slots within working hours (WORK_START–WORK_END), next N days."""
    now = datetime.now()
    search_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    search_end = search_start + timedelta(days=days_ahead)

    # Fetch all events in range
    try:
        events = get_events(access_token, search_start, search_end)
    except Exception:
        events = []

    # Build set of busy intervals
    busy = []
    for ev in events:
        if ev.get("is_cancelled"):
            continue
        try:
            s = datetime.fromisoformat(ev["start"].replace("Z", "+00:00")).replace(tzinfo=None)
            e = datetime.fromisoformat(ev["end"].replace("Z", "+00:00")).replace(tzinfo=None)
            busy.append((s, e))
        except Exception:
            pass

    slots = []
    current = search_start
    while current < search_end and len(slots) < 6:
        # Skip weekends (Fri=4, Sat=5)
        if current.weekday() in (4, 5):
            current = (current + timedelta(days=1)).replace(hour=WORK_START, minute=0)
            continue

        # Only within working hours
        slot_start = current.replace(minute=0, second=0, microsecond=0)
        if slot_start.hour < WORK_START:
            slot_start = slot_start.replace(hour=WORK_START)
        if slot_start.hour >= WORK_END:
            slot_start = (slot_start + timedelta(days=1)).replace(hour=WORK_START, minute=0)
            current = slot_start
            continue

        slot_end = slot_start + timedelta(minutes=duration_minutes)
        if slot_end.hour > WORK_END or (slot_end.hour == WORK_END and slot_end.minute > 0):
            slot_start = (slot_start + timedelta(days=1)).replace(hour=WORK_START, minute=0)
            current = slot_start
            continue

        # Check no overlap with busy
        overlap = any(s < slot_end and e > slot_start for s, e in busy)
        if not overlap:
            slots.append({
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "label": _hebrew_slot_label(slot_start, slot_end),
            })
            current = slot_end
        else:
            current = slot_start + timedelta(minutes=30)

    return slots


def _hebrew_slot_label(start: datetime, end: datetime) -> str:
    days_he = ["שני", "שלישי", "רביעי", "חמישי", "ראשון", "שישי", "שבת"]
    day = days_he[start.weekday()]
    return f"יום {day} {start.strftime('%d/%m')} בשעה {start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def parse_natural_event(text: str) -> Optional[dict]:
    """Parse natural-language Hebrew event description into event fields. Returns None on failure."""
    import anthropic, os, json
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"עכשיו: {now_str}\n"
                    f"טקסט: \"{text}\"\n\n"
                    "חלץ פרטי אירוע יומן. החזר JSON בלבד (ללא ```), עם המפתחות:\n"
                    "subject (string), start (ISO8601 datetime), end (ISO8601 datetime, ברירת מחדל שעה אחרי start), "
                    "location (string or null), attendees (list of {name,email} or []).\n"
                    "אם לא ניתן לחלץ — החזר null."
                ),
            }],
        )
        text_out = resp.content[0].text.strip()
        if text_out.lower() == "null":
            return None
        return json.loads(text_out)
    except Exception:
        return None
