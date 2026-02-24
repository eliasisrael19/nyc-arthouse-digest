from __future__ import annotations

import os
from pathlib import Path

from src.config import load_dotenv


def test_load_dotenv_sets_only_missing_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ='qux'\n", encoding="utf-8")

    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.setenv("BAZ", "existing")

    load_dotenv(env_file)

    assert os.getenv("FOO") == "bar"
    assert os.getenv("BAZ") == "existing"
