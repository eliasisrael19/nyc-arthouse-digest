from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.config import _parse_recipients, load_config, load_dotenv


def test_load_dotenv_sets_only_missing_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ='qux'\n", encoding="utf-8")

    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.setenv("BAZ", "existing")

    load_dotenv(env_file)

    assert os.getenv("FOO") == "bar"
    assert os.getenv("BAZ") == "existing"


def test_parse_recipients_accepts_common_separators_and_dedupes() -> None:
    raw = "one@example.com,\ntwo@example.com; two@example.com  \nthree@example.com"

    assert _parse_recipients(raw) == [
        "one@example.com",
        "two@example.com",
        "three@example.com",
    ]


def test_load_config_rejects_invalid_env_recipient(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
smtp:
  host: "smtp.example.com"
  port: 587
  username: "sender@example.com"
  password: "secret"
  sender: "sender@example.com"
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGEST_RECIPIENTS", "good@example.com,bad address")

    with pytest.raises(ValueError, match="Invalid recipient email address"):
        load_config(config_file)
