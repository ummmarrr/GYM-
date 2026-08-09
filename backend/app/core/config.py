from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor every path to the backend package rather than the current working directory, so the
# app reads the same .env, database and vector store no matter where it is launched from.
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


class Settings(BaseSettings):
    app_name: str = "Master GYM"
    bot_name: str = "FitBot"
    environment: str = "development"
    database_url: str = "sqlite:///./gym_coach.db"
    jwt_secret: str = "development-only-change-me-use-at-least-32-characters"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    # 768 keeps the stored vectors a quarter the size of the model's native 3072 with very
    # little loss of recall, which matters on a 0.5 GB database.
    embedding_dimensions: int = 768

    # Second provider, tried when Gemini's free quota runs out. llama-3.1-8b-instant allows
    # 14,400 requests a day free, so the pair together are hard to exhaust.
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    llm_timeout_seconds: int = 20
    llm_retry_attempts: int = 2
    # Output tokens count against the free tier's per-minute and per-day token budget just as
    # input tokens do, and an uncapped coaching answer can run to a thousand of them.
    llm_max_output_tokens: int = 500
    # How long to stop asking a provider that has reported its quota is gone. Without this
    # every later request pays that provider's timeout before falling through.
    llm_cooldown_seconds: int = 900

    # Class times are stored naive UTC. FitBot quotes them as text, so it needs the gym's
    # wall clock; the web UI does this conversion in the browser instead.
    display_timezone: str = "Asia/Kolkata"
    # FitBot is open to signed-out visitors and every message costs an embedding call and an
    # LLM call, so the public endpoints are capped per caller. Generous for a person, useless
    # for a script.
    rate_limit_enabled: bool = True
    chat_rate_limit: int = 20
    chat_rate_window_seconds: int = 300
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    register_rate_limit: int = 5
    register_rate_window_seconds: int = 3600

    max_upload_mb: int = 15
    # Comma-separated, because once deployed the browser talks to the API from the live site
    # and from localhost during development, and both origins have to be allowed.
    frontend_origin: str = "http://localhost:5173"

    # The sign-in page publishes these logins so a visitor can look around. Anyone on the
    # internet holds their passwords, so the API refuses writes from them.
    demo_account_emails: str = (
        "admin-demo@example.com,trainer-demo@example.com,member-demo@example.com"
    )

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    @property
    def demo_emails(self) -> set[str]:
        entries = self.demo_account_emails.split(",")
        return {email.strip().lower() for email in entries if email.strip()}

    @field_validator("database_url")
    @classmethod
    def resolve_sqlite_path(cls, value: str) -> str:
        # Neon hands out a plain postgresql:// URL, which SQLAlchemy reads as "use psycopg2".
        # Name psycopg 3 explicitly so the URL can be pasted from the console unedited.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)

        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value
        location = value[len(prefix) :]
        if location == ":memory:" or location.startswith(":"):
            return value
        return f"{prefix}{_absolute(Path(location)).as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
