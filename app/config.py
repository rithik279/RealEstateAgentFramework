from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


ROOT_DIR = Path(__file__).resolve().parent.parent
load_env_file(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    dry_run: bool = _to_bool(os.getenv("APP_DRY_RUN"), default=True)
    base_url: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    data_file: Path = ROOT_DIR / os.getenv("APP_DATA_FILE", "data/store.json")
    ui_file: Path = ROOT_DIR / "app" / "ui" / "index.html"

    booking_link: str = os.getenv("BOOKING_LINK", "https://calendly.com/your-link")
    company_name: str = os.getenv("COMPANY_NAME", "Your Real Estate Advisory")
    advisor_name: str = os.getenv("ADVISOR_NAME", "Your Name")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")

    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")

    meta_page_access_token: str = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    meta_page_id: str = os.getenv("META_PAGE_ID", "")


settings = Settings()
settings.data_file.parent.mkdir(parents=True, exist_ok=True)
