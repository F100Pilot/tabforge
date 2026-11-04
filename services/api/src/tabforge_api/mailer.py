"""Outgoing email behind a small port: generic SMTP (stdlib) or, in dev without SMTP, the log."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from pydantic import SecretStr

from tabforge_api.settings import Settings

log = logging.getLogger("tabforge_api.mailer")
SMTP_TIMEOUT_S = 10.0


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    """One connection per message; the volume (login links) does not justify pooling."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: SecretStr | None = None,
        starttls: bool = True,
        timeout_s: float = SMTP_TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._starttls = starttls
        self._timeout_s = timeout_s

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as smtp:
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._username:
                password = self._password.get_secret_value() if self._password else ""
                smtp.login(self._username, password)
            smtp.send_message(msg)


class LogMailer:
    """Dev only: writes the message body (the login link) to the log, never the recipient.

    WARNING level so it shows without logging configuration (uvicorn leaves the root logger bare).
    """

    def send(self, to: str, subject: str, body: str) -> None:
        log.warning("dev mail (no SMTP configured): %s\n%s", subject, body)


def build_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host:
        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.mail_from,
            username=settings.smtp_username,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
        )
    if settings.env == "dev":
        return LogMailer()
    # Fail closed: outside dev, login links must never end up in logs.
    raise RuntimeError("TABFORGE_SMTP_HOST is required outside env=dev")
