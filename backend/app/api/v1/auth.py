"""Auth endpoints: register, login, refresh, me + Google/GitHub OAuth code flow."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, audit
from app.api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_fingerprint,
    verify_password,
)
from app.infrastructure.db.models import Bankroll, RefreshToken, Subscription, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(db: DbDep, user: User) -> TokenPair:
    access = create_access_token(str(user.id), role=user.role)
    refresh = create_refresh_token(str(user.id))
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_fingerprint(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    db.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


def _bootstrap_user(db: DbDep, email: str, full_name: str | None, provider: str,
                    password: str | None = None) -> User:
    user = User(
        email=email.lower(), full_name=full_name, provider=provider,
        hashed_password=hash_password(password) if password else None,
    )
    db.add(user)
    db.flush()
    db.add(Subscription(user_id=user.id))
    db.add(Bankroll(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbDep, request: Request) -> TokenPair:
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = _bootstrap_user(db, payload.email, payload.full_name, "local", payload.password)
    audit(db, request, "user.register", user_id=user.id, email=user.email)
    return _issue_tokens(db, user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbDep, request: Request) -> TokenPair:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    audit(db, request, "user.login", user_id=user.id)
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbDep) -> TokenPair:
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_fingerprint(payload.refresh_token)))
    if stored is None or stored.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    user = db.scalar(select(User).where(User.id == int(decoded["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    stored.revoked = True  # rotation: single use
    db.commit()
    return _issue_tokens(db, user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


# ── OAuth (authorization-code flow) ──────────────────────────────────────────
OAUTH_PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
    },
}


def _oauth_config(provider: str) -> tuple[dict, str, str]:
    cfg = OAUTH_PROVIDERS.get(provider)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    cid = settings.GOOGLE_CLIENT_ID if provider == "google" else settings.GITHUB_CLIENT_ID
    secret = settings.GOOGLE_CLIENT_SECRET if provider == "google" else settings.GITHUB_CLIENT_SECRET
    if not cid or not secret:
        raise HTTPException(status_code=503, detail=f"{provider} OAuth not configured")
    return cfg, cid, secret


@router.get("/oauth/{provider}/login")
def oauth_login(provider: str) -> RedirectResponse:
    cfg, cid, _ = _oauth_config(provider)
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/{provider}/callback"
    url = (
        f"{cfg['auth_url']}?client_id={cid}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope={cfg['scope'].replace(' ', '%20')}"
    )
    return RedirectResponse(url)


@router.get("/oauth/{provider}/callback", response_model=TokenPair)
def oauth_callback(provider: str, code: str, db: DbDep, request: Request) -> TokenPair:
    cfg, cid, secret = _oauth_config(provider)
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/{provider}/callback"
    with httpx.Client(timeout=15) as client:
        token_resp = client.post(
            cfg["token_url"],
            data={"client_id": cid, "client_secret": secret, "code": code,
                  "grant_type": "authorization_code", "redirect_uri": redirect_uri},
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access = token_resp.json().get("access_token")
        if not access:
            raise HTTPException(status_code=401, detail="OAuth exchange failed")
        info = client.get(cfg["userinfo_url"], headers={"Authorization": f"Bearer {access}"}).json()
    email = info.get("email")
    if not email and provider == "github":
        with httpx.Client(timeout=15) as client:
            emails = client.get("https://api.github.com/user/emails",
                                headers={"Authorization": f"Bearer {access}"}).json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = primary.get("email") if primary else None
    if not email:
        raise HTTPException(status_code=422, detail="Provider returned no email")
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = _bootstrap_user(db, email, info.get("name") or info.get("login"), provider)
    audit(db, request, "user.oauth_login", user_id=user.id, provider=provider)
    return _issue_tokens(db, user)
