"""
config.py
Loads all environment variables via pydantic-settings.
Values are read from a .env file in the project root.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    # Default to SQLite for development; override with postgresql:// URL in production
    DATABASE_URL: str = "sqlite:///./afid.db"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480   # 8-hour clinic shift

    # ── App ───────────────────────────────────────────────────────────────────
    APP_TITLE: str = "AFID HMS API"
    APP_VERSION: str = "1.0.0"
    CORS_ORIGINS: list[str] = ["http://localhost", "http://127.0.0.1", "null", "http://localhost:5173", "http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
