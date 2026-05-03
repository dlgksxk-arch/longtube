"""Login, signup, and user approval endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.security.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    hash_password,
    parse_session_token,
    verify_password,
)


router = APIRouter()


class AuthUserOut(BaseModel):
    id: str
    username: str
    display_name: str | None
    role: str
    status: str
    created_at: datetime | None = None
    approved_at: datetime | None = None


class AuthMeOut(BaseModel):
    authenticated: bool
    user: AuthUserOut | None = None


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    username: str
    password: str


class ApprovalRequest(BaseModel):
    role: str = "user"


def _user_out(user: User) -> AuthUserOut:
    return AuthUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        approved_at=user.approved_at,
    )


def _set_session_cookie(response: Response, user: User) -> None:
    token = create_session_token(user.id, user.username, user.role)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    payload = parse_session_token(request.cookies.get(SESSION_COOKIE_NAME))
    if not payload:
        return None
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or user.status != "approved":
        return None
    return user


def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


def require_master(user: User = Depends(require_user)) -> User:
    if user.role != "master":
        raise HTTPException(status_code=403, detail="마스터 권한이 필요합니다.")
    return user


@router.post("/signup", response_model=AuthUserOut)
def signup(body: SignupRequest, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip()
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 존재하는 계정입니다.")

    has_any_user = db.query(User.id).first() is not None
    user = User(
        username=username,
        display_name=(body.display_name or "").strip() or username,
        password_hash=hash_password(body.password),
        role="user" if has_any_user else "master",
        status="pending" if has_any_user else "approved",
        approved_at=datetime.now(timezone.utc) if not has_any_user else None,
        approved_by="bootstrap" if not has_any_user else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if user.status == "approved":
        _set_session_cookie(response, user)
    return _user_out(user)


@router.post("/login", response_model=AuthUserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="계정 또는 비밀번호가 맞지 않습니다.")
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="아직 승인 대기 중입니다.")
    if user.status != "approved":
        raise HTTPException(status_code=403, detail="사용할 수 없는 계정입니다.")
    _set_session_cookie(response, user)
    return _user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=AuthMeOut)
def me(user: User | None = Depends(get_optional_user)):
    return AuthMeOut(authenticated=bool(user), user=_user_out(user) if user else None)


@router.get("/users/pending", response_model=list[AuthUserOut])
def pending_users(_: User = Depends(require_master), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.status == "pending").order_by(User.created_at.asc()).all()
    return [_user_out(user) for user in users]


@router.post("/users/{user_id}/approve", response_model=AuthUserOut)
def approve_user(user_id: str, body: ApprovalRequest, master: User = Depends(require_master), db: Session = Depends(get_db)):
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="승인 role은 user 또는 admin만 가능합니다.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if user.role == "master":
        raise HTTPException(status_code=400, detail="마스터 계정은 승인 상태를 바꿀 수 없습니다.")
    user.role = body.role
    user.status = "approved"
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by = master.id
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/users/{user_id}/reject", response_model=AuthUserOut)
def reject_user(user_id: str, _: User = Depends(require_master), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if user.role == "master":
        raise HTTPException(status_code=400, detail="마스터 계정은 거절할 수 없습니다.")
    user.status = "rejected"
    db.commit()
    db.refresh(user)
    return _user_out(user)
