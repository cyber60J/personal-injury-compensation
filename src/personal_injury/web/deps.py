from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from personal_injury.domain.models import UserRole
from personal_injury.infrastructure.database import SessionTokenModel, UserModel


PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )


# 不存在的账号也执行同等成本的密码校验，降低通过响应时长枚举用户名的风险。
DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password")


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iteration_count = int(iterations)
        if iteration_count < 100_000 or iteration_count > 2_000_000:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            iteration_count,
        ).hex()
        return hmac.compare_digest(expected, digest_hex)
    except (TypeError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: UserModel, minutes: int) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    db.query(SessionTokenModel).filter(SessionTokenModel.expires_at <= now).delete(
        synchronize_session=False
    )
    active_sessions = db.query(SessionTokenModel).filter(
        SessionTokenModel.user_id == user.id
    ).order_by(SessionTokenModel.created_at.desc()).all()
    for old_session in active_sessions[9:]:
        db.delete(old_session)
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=minutes)
    db.add(
        SessionTokenModel(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return token, expires_at


def get_db(request: Request):
    session_factory = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _extract_token(authorization: str | None, cookie_token: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return cookie_token


def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> UserModel:
    token = _extract_token(authorization, access_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    session_token = db.query(SessionTokenModel).filter(
        SessionTokenModel.token_hash == token_hash(token)
    ).first()
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效")
    expires_at = session_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(session_token)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user = db.query(UserModel).filter(
        UserModel.id == session_token.user_id,
        UserModel.is_active.is_(True),
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    return user


def role_required(*roles: UserRole) -> Callable:
    allowed = {role.value for role in roles}

    def dependency(user: UserModel = Depends(get_current_user)) -> UserModel:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return dependency
