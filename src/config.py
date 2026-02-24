from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

import yaml


@dataclass(slots=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    use_starttls: bool = True


@dataclass(slots=True)
class AppConfig:
    recipients: list[str]
    smtp: SMTPConfig


DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DOTENV_PATH = Path(".env")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a top-level mapping: {path}")
    return data


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: str | Path = DEFAULT_DOTENV_PATH) -> None:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    path = Path(config_path)
    data = _read_yaml(path)

    recipients = os.getenv("DIGEST_RECIPIENTS")
    if recipients:
        recipient_list = [e.strip() for e in recipients.split(",") if e.strip()]
    else:
        recipient_list = data.get("recipients", [])

    smtp_data = data.get("smtp", {})
    smtp = SMTPConfig(
        host=os.getenv("SMTP_HOST", smtp_data.get("host", "")),
        port=int(os.getenv("SMTP_PORT", smtp_data.get("port", 587))),
        username=os.getenv("SMTP_USERNAME", smtp_data.get("username", "")),
        password=os.getenv("SMTP_PASSWORD", smtp_data.get("password", "")),
        sender=os.getenv("SMTP_SENDER", smtp_data.get("sender", "")),
        use_starttls=_env_bool(
            "SMTP_STARTTLS",
            bool(smtp_data.get("use_starttls", True)),
        ),
    )

    if not recipient_list:
        raise ValueError("No recipients configured. Set DIGEST_RECIPIENTS or recipients in config.yaml")

    return AppConfig(recipients=recipient_list, smtp=smtp)
