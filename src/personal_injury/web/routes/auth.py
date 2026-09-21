from __future__ import annotations

import hmac
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from personal_injury.domain.models import (
    BootstrapRequest,
    LoginRequest,
    TokenRead,
    UserAdminUpdate,
    UserCreate,
    UserRead,
    UserRole,
)
from personal_injury.infrastructure.database import (
    AuditLogModel,
    CaseModel,
    SessionTokenModel,
    UserModel,
)
from personal_injury.web.deps import (
    DUMMY_PASSWORD_HASH,
    create_session,
    get_current_user,
    get_db,
    hash_password,
    role_required,
    token_hash,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])

LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_KEY_LIMIT = 5_000
_login_failures: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.casefold()}"


def _normalized_username(username: str) -> str:
    return username.casefold()


def _check_login_rate_limit(key: str) -> None:
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    with _login_lock:
        if len(_login_failures) >= LOGIN_FAILURE_KEY_LIMIT:
            stale_keys = [
                item_key
                for item_key, attempts in _login_failures.items()
                if not attempts or attempts[-1] < cutoff
            ]
            for stale_key in stale_keys:
                _login_failures.pop(stale_key, None)
            if len(_login_failures) >= LOGIN_FAILURE_KEY_LIMIT and key not in _login_failures:
                _login_failures.pop(next(iter(_login_failures)))
        recent = [item for item in _login_failures[key] if item >= cutoff]
        _login_failures[key] = recent
        if len(recent) >= LOGIN_MAX_FAILURES:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")


def _record_login_failure(key: str) -> None:
    with _login_lock:
        _login_failures[key].append(time.monotonic())


def _clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        "access_token",
        token,
        max_age=request.app.state.settings.access_token_minutes * 60,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def user_read(user: UserModel) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=UserRole(user.role),
        is_active=user.is_active,
    )


@router.post("/bootstrap", response_model=TokenRead, status_code=201)
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    db: Session = Depends(get_db),
):
    settings = request.app.state.settings
    if not settings.allow_open_bootstrap:
        if not settings.bootstrap_token:
            raise HTTPException(status_code=503, detail="系统未配置管理员初始化令牌")
        if not bootstrap_token or not hmac.compare_digest(bootstrap_token, settings.bootstrap_token):
            raise HTTPException(status_code=403, detail="管理员初始化令牌无效")
    if db.query(UserModel).count() > 0:
        raise HTTPException(status_code=409, detail="系统已完成初始化")
    user = UserModel(
        username=_normalized_username(payload.username),
        display_name=payload.display_name,
        role=UserRole.ADMIN.value,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token, expires_at = create_session(db, user, request.app.state.settings.access_token_minutes)
    db.add(AuditLogModel(
        actor_id=user.id,
        action="system_bootstrapped",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
    ))
    db.commit()
    _set_session_cookie(response, request, token)
    return TokenRead(expires_at=expires_at.isoformat(), user=user_read(user))


@router.post("/login", response_model=TokenRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    login_key = _login_key(request, payload.username)
    _check_login_rate_limit(login_key)
    normalized_username = _normalized_username(payload.username)
    user = db.query(UserModel).filter(func.lower(UserModel.username) == normalized_username).first()
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)
    if not user or not user.is_active or not password_valid:
        _record_login_failure(login_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    _clear_login_failures(login_key)
    token, expires_at = create_session(db, user, request.app.state.settings.access_token_minutes)
    db.add(AuditLogModel(
        actor_id=user.id,
        action="user_logged_in",
        entity_type="session",
        details={},
    ))
    db.commit()
    _set_session_cookie(response, request, token)
    return TokenRead(expires_at=expires_at.isoformat(), user=user_read(user))


@router.get("/me", response_model=UserRead)
def me(user: UserModel = Depends(get_current_user)):
    return user_read(user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    authorization = request.headers.get("Authorization", "")
    token = (
        authorization[7:].strip()
        if authorization.lower().startswith("bearer ")
        else request.cookies.get("access_token")
    )
    if token:
        session_token = db.query(SessionTokenModel).filter(
            SessionTokenModel.token_hash == token_hash(token),
            SessionTokenModel.user_id == user.id,
        ).first()
        if session_token:
            db.delete(session_token)
    db.add(AuditLogModel(
        actor_id=user.id,
        action="user_logged_out",
        entity_type="session",
        details={},
    ))
    db.commit()
    response.delete_cookie(
        "access_token",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )


@users_router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    user: UserModel = Depends(role_required(UserRole.ADMIN)),
):
    return [user_read(item) for item in db.query(UserModel).order_by(UserModel.username).all()]


@users_router.post("", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: UserModel = Depends(role_required(UserRole.ADMIN)),
):
    normalized_username = _normalized_username(payload.username)
    if db.query(UserModel).filter(func.lower(UserModel.username) == normalized_username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = UserModel(
        username=normalized_username,
        display_name=payload.display_name,
        role=payload.role.value,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(AuditLogModel(
        actor_id=actor.id,
        action="user_created",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": user.role},
    ))
    db.commit()
    db.refresh(user)
    return user_read(user)


@users_router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
    actor: UserModel = Depends(role_required(UserRole.ADMIN)),
):
    target = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    if payload.is_active is False and target.id == actor.id:
        raise HTTPException(status_code=409, detail="管理员不能停用自己的账号")
    if payload.is_active is False and target.role == UserRole.LAWYER.value:
        active_case_count = db.query(CaseModel).filter(
            CaseModel.responsible_lawyer_id == target.id,
            CaseModel.status.in_(["open", "review"]),
        ).count()
        if active_case_count:
            raise HTTPException(status_code=409, detail="请先移交该律师负责的进行中案件")

    changed_fields = []
    invalidate_sessions = False
    if payload.display_name is not None and payload.display_name != target.display_name:
        target.display_name = payload.display_name
        changed_fields.append("display_name")
    if payload.password is not None:
        target.password_hash = hash_password(payload.password)
        changed_fields.append("password")
        invalidate_sessions = True
    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        changed_fields.append("is_active")
        if not payload.is_active:
            invalidate_sessions = True

    if not changed_fields:
        return user_read(target)
    if invalidate_sessions:
        db.query(SessionTokenModel).filter(SessionTokenModel.user_id == target.id).delete(
            synchronize_session=False
        )
    db.add(
        AuditLogModel(
            actor_id=actor.id,
            action="user_updated",
            entity_type="user",
            entity_id=target.id,
            details={"fields": changed_fields},
        )
    )
    db.commit()
    db.refresh(target)
    return user_read(target)
