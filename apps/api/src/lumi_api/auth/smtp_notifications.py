from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


class SmtpAuthNotificationPort:
    """Minimal SMTP delivery adapter. Tokens are sent in mail body and never logged."""

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int,
        from_address: str,
        public_base_url: str,
        use_starttls: bool = False,
    ) -> None:
        if not smtp_host or not from_address or not public_base_url.startswith(("http://", "https://")):
            raise ValueError("SMTP notification adapter requires host/from/public base URL")
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_address = from_address
        self.public_base_url = public_base_url.rstrip("/")
        self.use_starttls = use_starttls

    async def _send(self, *, email: str, subject: str, path: str, token: str) -> None:
        query = urlencode({"token": token})
        url = f"{self.public_base_url}{path}?{query}"
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = email
        message["Subject"] = subject
        message.set_content(
            f"Open this LUMI link to continue:\n\n{url}\n\n"
            "If you did not request this action, ignore this email."
        )

        def deliver() -> None:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                if self.use_starttls:
                    smtp.starttls()
                smtp.send_message(message)

        await asyncio.to_thread(deliver)

    async def send_email_verification(self, *, email: str, token: str) -> None:
        await self._send(
            email=email,
            subject="Verify your LUMI email",
            path="/verify-email",
            token=token,
        )

    async def send_password_reset(self, *, email: str, token: str) -> None:
        await self._send(
            email=email,
            subject="Reset your LUMI password",
            path="/reset-password",
            token=token,
        )

    async def send_organization_invite(
        self,
        *,
        email: str,
        organization_id: str,
        token: str,
    ) -> None:
        await self._send(
            email=email,
            subject="You were invited to a LUMI organization",
            path=f"/organizations/{organization_id}/invite",
            token=token,
        )
