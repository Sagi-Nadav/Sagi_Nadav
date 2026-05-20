import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import msal
from cryptography.fernet import Fernet
from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer
from sqlalchemy.orm import Session

from .database import SessionStore

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
DEMO_USER = {
    "session_id": "demo",
    "user_id": "demo-user",
    "display_name": "שגיב נדב",
    "email": "demo@assistant.local",
    "access_token": "demo-token",
}

AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "pa_session")

SCOPES = [
    "User.Read",
    "Calendars.ReadWrite",
    "Mail.ReadWrite",
    "Mail.Send",
    "Tasks.ReadWrite",
]

AUTHORITY = "https://login.microsoftonline.com/common"

_signer = URLSafeSerializer(SECRET_KEY, salt="session")

# Derive a 32-byte URL-safe base64 key from SECRET_KEY for Fernet
import base64, hashlib
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
_fernet = Fernet(_fernet_key)


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=AUTHORITY,
        client_credential=AZURE_CLIENT_SECRET,
        instance_discovery=False,
    )


def get_auth_url(state: str) -> str:
    app = _msal_app()
    return app.get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=AZURE_REDIRECT_URI,
    )


def exchange_code_for_token(code: str) -> dict:
    app = _msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=AZURE_REDIRECT_URI,
    )
    if "error" in result:
        raise ValueError(f"Token exchange failed: {result.get('error_description', result['error'])}")
    return result


def refresh_access_token(refresh_token_plain: str) -> dict:
    app = _msal_app()
    result = app.acquire_token_by_refresh_token(
        refresh_token=refresh_token_plain,
        scopes=SCOPES,
    )
    if "error" in result:
        raise ValueError(f"Token refresh failed: {result.get('error_description', result['error'])}")
    return result


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()


def create_session(db: Session, token_result: dict) -> str:
    claims = token_result.get("id_token_claims", {})
    user_id = claims.get("oid") or claims.get("sub", "unknown")
    display_name = claims.get("name") or claims.get("preferred_username", "משתמש")
    email = claims.get("preferred_username") or claims.get("email", "")

    expiry = datetime.utcnow() + timedelta(seconds=token_result.get("expires_in", 3600))
    session_id = secrets.token_urlsafe(32)

    record = SessionStore(
        session_id=session_id,
        user_id=user_id,
        display_name=display_name,
        email=email,
        access_token=encrypt_token(token_result["access_token"]),
        refresh_token=encrypt_token(token_result.get("refresh_token", "")),
        token_expiry=expiry,
        created_at=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db.add(record)
    db.commit()

    signed = _signer.dumps(session_id)
    return signed


def _get_session_record(request: Request, db: Session) -> Optional[SessionStore]:
    signed = request.cookies.get(SESSION_COOKIE_NAME)
    if not signed:
        return None
    try:
        session_id = _signer.loads(signed)
    except Exception:
        return None

    record = db.query(SessionStore).filter(SessionStore.session_id == session_id).first()
    if not record:
        return None

    record.last_seen = datetime.utcnow()
    db.commit()
    return record


def get_current_user(request: Request, db: Session) -> dict:
    if DEMO_MODE:
        return DEMO_USER
    record = _get_session_record(request, db)
    if not record:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Refresh token if expiring within 5 minutes
    if record.token_expiry <= datetime.utcnow() + timedelta(minutes=5):
        try:
            refresh_token_plain = decrypt_token(record.refresh_token)
            result = refresh_access_token(refresh_token_plain)
            record.access_token = encrypt_token(result["access_token"])
            if "refresh_token" in result:
                record.refresh_token = encrypt_token(result["refresh_token"])
            record.token_expiry = datetime.utcnow() + timedelta(seconds=result.get("expires_in", 3600))
            db.commit()
        except Exception:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")

    access_token = decrypt_token(record.access_token)
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "display_name": record.display_name,
        "email": record.email,
        "access_token": access_token,
    }


def delete_session(request: Request, db: Session) -> None:
    record = _get_session_record(request, db)
    if record:
        db.delete(record)
        db.commit()


def cleanup_old_sessions(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(days=7)
    db.query(SessionStore).filter(SessionStore.last_seen < cutoff).delete()
    db.commit()
