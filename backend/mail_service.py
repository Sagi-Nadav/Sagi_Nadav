import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _normalize_message(msg: dict) -> dict:
    return {
        "id": msg.get("id"),
        "subject": msg.get("subject", "(ללא נושא)"),
        "from_name": msg.get("from", {}).get("emailAddress", {}).get("name", ""),
        "from_email": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
        "to": [
            {"name": r.get("emailAddress", {}).get("name", ""), "email": r.get("emailAddress", {}).get("address", "")}
            for r in msg.get("toRecipients", [])
        ],
        "received_at": msg.get("receivedDateTime"),
        "is_read": msg.get("isRead", False),
        "body_preview": msg.get("bodyPreview", ""),
        "body": msg.get("body", {}).get("content", ""),
        "body_type": msg.get("body", {}).get("contentType", "text"),
        "is_draft": msg.get("isDraft", False),
        "has_attachments": msg.get("hasAttachments", False),
    }


def list_inbox(access_token: str, top: int = 20, skip: int = 0) -> list[dict]:
    url = (
        f"{GRAPH_BASE}/me/messages"
        f"?$filter=isDraft eq false"
        f"&$orderby=receivedDateTime desc"
        f"&$top={top}&$skip={skip}"
        f"&$select=id,subject,from,toRecipients,receivedDateTime,isRead,bodyPreview,isDraft,hasAttachments"
    )
    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return [_normalize_message(m) for m in resp.json().get("value", [])]


def get_message(access_token: str, message_id: str) -> dict:
    url = f"{GRAPH_BASE}/me/messages/{message_id}"
    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return _normalize_message(resp.json())


def create_draft(access_token: str, subject: str, to_recipients: list[dict], body_html: str) -> dict:
    body = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [
            {"emailAddress": {"address": r["email"], "name": r.get("name", r["email"])}}
            for r in to_recipients
        ],
    }
    with httpx.Client() as client:
        resp = client.post(f"{GRAPH_BASE}/me/messages", headers=_headers(access_token), json=body)
        resp.raise_for_status()
    return _normalize_message(resp.json())


def update_draft(access_token: str, message_id: str, updates: dict) -> dict:
    body = {}
    if "subject" in updates:
        body["subject"] = updates["subject"]
    if "body_html" in updates:
        body["body"] = {"contentType": "HTML", "content": updates["body_html"]}
    if "to_recipients" in updates:
        body["toRecipients"] = [
            {"emailAddress": {"address": r["email"], "name": r.get("name", r["email"])}}
            for r in updates["to_recipients"]
        ]
    with httpx.Client() as client:
        resp = client.patch(f"{GRAPH_BASE}/me/messages/{message_id}", headers=_headers(access_token), json=body)
        resp.raise_for_status()
    return _normalize_message(resp.json())


def send_draft(access_token: str, message_id: str) -> None:
    with httpx.Client() as client:
        resp = client.post(f"{GRAPH_BASE}/me/messages/{message_id}/send", headers=_headers(access_token))
        resp.raise_for_status()


def delete_message(access_token: str, message_id: str) -> None:
    url = f"{GRAPH_BASE}/me/messages/{message_id}"
    with httpx.Client(timeout=30) as client:
        resp = client.delete(url, headers=_headers(access_token))
        resp.raise_for_status()


def list_folders(access_token: str) -> list[dict]:
    url = f"{GRAPH_BASE}/me/mailFolders?$top=50"
    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return [
        {"id": f["id"], "name": f["displayName"], "unread": f.get("unreadItemCount", 0), "total": f.get("totalItemCount", 0)}
        for f in resp.json().get("value", [])
    ]


def create_folder(access_token: str, name: str, parent_id: str = "inbox") -> dict:
    url = f"{GRAPH_BASE}/me/mailFolders/{parent_id}/childFolders"
    with httpx.Client() as client:
        resp = client.post(url, headers=_headers(access_token), json={"displayName": name})
        resp.raise_for_status()
    f = resp.json()
    return {"id": f["id"], "name": f["displayName"]}


def move_message(access_token: str, message_id: str, destination_folder_id: str) -> dict:
    url = f"{GRAPH_BASE}/me/messages/{message_id}/move"
    with httpx.Client() as client:
        resp = client.post(url, headers=_headers(access_token), json={"destinationId": destination_folder_id})
        resp.raise_for_status()
    return _normalize_message(resp.json())


def mark_as_read(access_token: str, message_id: str) -> None:
    url = f"{GRAPH_BASE}/me/messages/{message_id}"
    with httpx.Client() as client:
        resp = client.patch(url, headers=_headers(access_token), json={"isRead": True})
        resp.raise_for_status()


def list_unread(access_token: str, top: int = 50) -> list[dict]:
    url = (
        f"{GRAPH_BASE}/me/messages"
        f"?$filter=isRead eq false and isDraft eq false"
        f"&$orderby=receivedDateTime desc"
        f"&$top={top}"
        f"&$select=id,subject,from,toRecipients,receivedDateTime,isRead,bodyPreview,body,isDraft,hasAttachments"
    )
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
    return [_normalize_message(m) for m in resp.json().get("value", [])]


def send_new(access_token: str, subject: str, to_recipients: list[dict], body_html: str) -> None:
    body = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [
                {"emailAddress": {"address": r["email"], "name": r.get("name", r["email"])}}
                for r in to_recipients
            ],
        },
        "saveToSentItems": True,
    }
    with httpx.Client() as client:
        resp = client.post(f"{GRAPH_BASE}/me/sendMail", headers=_headers(access_token), json=body)
        resp.raise_for_status()
