import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import pytest
from pydantic import SecretStr

from tabforge_api.mailer import LogMailer, SmtpMailer, build_mailer
from tabforge_api.settings import Settings

URL = "postgresql://u:p@localhost:5432/db"


class FakeSMTP:
    instances: list["FakeSMTP"] = []  # noqa: RUF012 (test recorder)

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.args = (host, port, timeout)
        self.calls: list[str] = []
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self, *, context: Any = None) -> None:
        assert context is not None
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, msg: EmailMessage) -> None:
        self.calls.append("send")
        self.sent.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_smtp_mailer_uses_starttls_and_login(fake_smtp: type[FakeSMTP]) -> None:
    mailer = SmtpMailer(
        host="smtp.example.com",
        port=587,
        sender="TabForge <no-reply@tabforge.test>",
        username="user",
        password=SecretStr("pw"),
        starttls=True,
    )
    mailer.send("ana@example.com", "Assunto", "Corpo com acentuação")
    (smtp,) = fake_smtp.instances
    assert smtp.args[:2] == ("smtp.example.com", 587)
    assert smtp.args[2] > 0  # always a timeout
    assert smtp.calls == ["starttls", "login:user:pw", "send", "quit"]
    msg = smtp.sent[0]
    assert msg["To"] == "ana@example.com"
    assert msg["From"] == "TabForge <no-reply@tabforge.test>"
    assert msg["Subject"] == "Assunto"
    assert "acentuação" in msg.get_content()


def test_smtp_mailer_plain_without_credentials(fake_smtp: type[FakeSMTP]) -> None:
    SmtpMailer(host="mailpit", port=1025, sender="x@y.z", starttls=False).send("a@b.c", "s", "b")
    assert fake_smtp.instances[0].calls == ["send", "quit"]


def test_build_mailer_logs_in_dev_without_smtp() -> None:
    mailer = build_mailer(Settings(database_url=URL))  # type: ignore[arg-type]
    assert isinstance(mailer, LogMailer)


def test_build_mailer_uses_smtp_when_configured() -> None:
    settings = Settings(database_url=URL, smtp_host="mailpit", smtp_port=1025)  # type: ignore[arg-type]
    assert isinstance(build_mailer(settings), SmtpMailer)


@pytest.mark.parametrize("env", ["test", "prod"])
def test_build_mailer_fails_closed_outside_dev_without_smtp(env: str) -> None:
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        build_mailer(Settings(database_url=URL, env=env))  # type: ignore[arg-type]


def test_log_mailer_logs_body_but_not_recipient(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Alembic's fileConfig (db fixtures) disables loggers created before it ran.
    monkeypatch.setattr(logging.getLogger("tabforge_api.mailer"), "disabled", False)
    with caplog.at_level(logging.INFO, logger="tabforge_api.mailer"):
        LogMailer().send("ana@example.com", "Assunto", "link: http://x/login/verify#token=t")
    assert "http://x/login/verify#token=t" in caplog.text
    assert "ana@example.com" not in caplog.text
