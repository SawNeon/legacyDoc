"""Transactional email delivery."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from legacydoc_core.settings import Settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15


class EmailSender(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.warning(
            "\n"
            "=================== EMAIL (console backend) ===================\n"
            "To     : %s\n"
            "Subject: %s\n"
            "---------------------------------------------------------------\n"
            "%s\n"
            "===============================================================",
            to,
            subject,
            body,
        )


class SmtpEmailSender(EmailSender):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        await asyncio.to_thread(self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        settings = self._settings

        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
        ) as server:
            server.starttls()

            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password.get_secret_value())

            server.send_message(message)


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend.lower() == "smtp":
        return SmtpEmailSender(settings)

    return ConsoleEmailSender()


def render_password_reset(*, reset_url: str, ttl_minutes: int) -> tuple[str, str]:
    subject = "Redefinicao de senha - Legacy Doc"

    body = (
        "Voce pediu para redefinir sua senha no Legacy Doc.\n\n"
        f"Abra o link abaixo para criar uma nova senha. Ele vale por {ttl_minutes} "
        "minutos e so pode ser usado uma vez.\n\n"
        f"{reset_url}\n\n"
        "Se nao foi voce que pediu, ignore este e-mail: sua senha continua a mesma."
    )

    return subject, body
