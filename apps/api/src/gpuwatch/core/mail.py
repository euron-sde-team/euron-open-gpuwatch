"""Outgoing mail for alert notifications: SMTP (Mailpit locally), SES, or the log only.

One small Protocol with one implementation per backend, chosen by ``MAIL_MODE``. Senders
raise on failure; the notification outbox retries with backoff.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol

from gpuwatch.core.aws import aws_client
from gpuwatch.core.config import Settings

log = logging.getLogger("gpuwatch.mail")


class MailSender(Protocol):
    mode: str

    async def send(self, to: list[str], subject: str, text: str) -> None: ...


class LogMail:
    """Writes the message to the log; nothing is delivered (the default, documented)."""

    mode = "log"

    async def send(self, to: list[str], subject: str, text: str) -> None:
        log.info("mail not delivered (MAIL_MODE=log)", extra={"to": to, "subject": subject})


class SmtpMail:
    mode = "smtp"

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._s.smtp_host, self._s.smtp_port, timeout=15) as smtp:
            if self._s.smtp_starttls:
                smtp.starttls()
            if self._s.smtp_user and self._s.smtp_password:
                smtp.login(self._s.smtp_user, self._s.smtp_password)
            smtp.send_message(message)

    async def send(self, to: list[str], subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._s.mail_from
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message.set_content(text)
        await asyncio.to_thread(self._send, message)


class SesMail:
    mode = "ses"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._from = settings.mail_from
        self._ses = client or aws_client(settings, "sesv2")

    async def send(self, to: list[str], subject: str, text: str) -> None:
        await asyncio.to_thread(
            self._ses.send_email,
            FromEmailAddress=self._from,
            Destination={"ToAddresses": to},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": text, "Charset": "UTF-8"}},
                }
            },
        )


def create_mail(settings: Settings) -> MailSender:
    if settings.mail_mode == "smtp":
        return SmtpMail(settings)
    if settings.mail_mode == "ses":
        return SesMail(settings)
    return LogMail()
