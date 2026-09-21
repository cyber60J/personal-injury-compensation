from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name}必须是true或false")


def _environment() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def _trusted_hosts() -> tuple[str, ...]:
    value = os.getenv("TRUSTED_HOSTS", "*")
    hosts = tuple(host.strip() for host in value.split(",") if host.strip())
    return hosts or ("*",)


def _database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url
    password = os.getenv("DB_PASSWORD")
    if password is None:
        return "sqlite:///./data/personal_injury.db"
    username = quote(os.getenv("DB_USER", "personal_injury"), safe="")
    encoded_password = quote(password, safe="")
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    database = quote(os.getenv("DB_NAME", "personal_injury"), safe="")
    return f"postgresql+psycopg://{username}:{encoded_password}@{host}:{port}/{database}"


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=_database_url)
    environment: str = field(default_factory=_environment)
    access_token_minutes: int = field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_MINUTES", "480"))
    )
    allow_demo_standards: bool = field(
        default_factory=lambda: _env_bool("ALLOW_DEMO_STANDARDS", _environment() != "production")
    )
    auto_create_schema: bool = field(
        default_factory=lambda: _env_bool("AUTO_CREATE_SCHEMA", _environment() != "production")
    )
    cookie_secure: bool = field(
        default_factory=lambda: _env_bool("COOKIE_SECURE", _environment() == "production")
    )
    allow_open_bootstrap: bool = field(
        default_factory=lambda: _env_bool("ALLOW_OPEN_BOOTSTRAP", _environment() != "production")
    )
    bootstrap_token: str | None = field(default_factory=lambda: os.getenv("BOOTSTRAP_TOKEN") or None)
    trusted_hosts: tuple[str, ...] = field(default_factory=_trusted_hosts)
    public_origin: str | None = field(
        default_factory=lambda: (os.getenv("PUBLIC_ORIGIN") or "").rstrip("/") or None
    )
    docs_enabled: bool = field(
        default_factory=lambda: _env_bool("DOCS_ENABLED", _environment() != "production")
    )

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV必须是development、test或production")
        if self.access_token_minutes < 5 or self.access_token_minutes > 24 * 60:
            raise ValueError("ACCESS_TOKEN_MINUTES必须在5到1440之间")
        if self.public_origin:
            origin = urlsplit(self.public_origin)
            if (
                origin.scheme not in {"http", "https"}
                or not origin.netloc
                or origin.username
                or origin.password
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
            ):
                raise ValueError("PUBLIC_ORIGIN必须是仅包含协议和主机的HTTP(S)来源")
        if self.environment == "production" and self.allow_demo_standards:
            raise ValueError("生产环境不能启用ALLOW_DEMO_STANDARDS")
        if self.environment == "production" and not self.database_url.startswith("postgresql"):
            raise ValueError("生产环境必须使用PostgreSQL数据库")
        if self.environment == "production" and self.auto_create_schema:
            raise ValueError("生产环境必须通过Alembic迁移，不能启用AUTO_CREATE_SCHEMA")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("生产环境必须启用COOKIE_SECURE")
        if self.environment == "production" and self.allow_open_bootstrap:
            raise ValueError("生产环境不能启用ALLOW_OPEN_BOOTSTRAP")
        if self.environment == "production" and self.bootstrap_token:
            if len(self.bootstrap_token) < 32:
                raise ValueError("生产环境BOOTSTRAP_TOKEN至少需要32个字符")
        if self.environment == "production" and "*" in self.trusted_hosts:
            raise ValueError("生产环境必须显式配置TRUSTED_HOSTS")
        if self.environment == "production" and (
            not self.public_origin or urlsplit(self.public_origin).scheme != "https"
        ):
            raise ValueError("生产环境必须配置HTTPS PUBLIC_ORIGIN")


def get_settings() -> Settings:
    return Settings()
