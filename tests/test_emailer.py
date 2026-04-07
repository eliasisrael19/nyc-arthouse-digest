from __future__ import annotations

from src.config import AppConfig, SMTPConfig
from src.emailer import send_email


class DummySMTP:
    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = None
        self.sent = None

    def __enter__(self) -> "DummySMTP":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        self.sent = (sender, recipients, message)


def test_send_email_uses_private_to_header(monkeypatch) -> None:
    captured: dict[str, DummySMTP] = {}

    def fake_smtp(host: str, port: int, timeout: int) -> DummySMTP:
        smtp = DummySMTP(host, port, timeout)
        captured["smtp"] = smtp
        return smtp

    monkeypatch.setattr("src.emailer.smtplib.SMTP", fake_smtp)

    config = AppConfig(
        recipients=["one@example.com", "two@example.com"],
        smtp=SMTPConfig(
            host="smtp.example.com",
            port=587,
            username="sender@example.com",
            password="secret",
            sender="sender@example.com",
        ),
    )

    send_email(config, "Digest", "<p>Hello</p>", "Hello")

    smtp = captured["smtp"]
    assert smtp.started_tls is True
    assert smtp.logged_in == ("sender@example.com", "secret")
    assert smtp.sent is not None
    sender, recipients, message = smtp.sent
    assert sender == "sender@example.com"
    assert recipients == ["one@example.com", "two@example.com"]
    assert "To: sender@example.com" in message
    assert "one@example.com, two@example.com" not in message
