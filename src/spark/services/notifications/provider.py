"""Outbound notification providers per factory."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from spark.core.logging import get_logger

log = get_logger(__name__)


class NotificationProvider(Protocol):
    async def send(self, *, subject: str, body: str, context: dict[str, Any]) -> bool: ...


class WebhookProvider:
    def __init__(self, url: str) -> None:
        self.url = url

    async def send(self, *, subject: str, body: str, context: dict[str, Any]) -> bool:
        payload = {"subject": subject, "text": body, "context": context}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.url, json=payload)
                return resp.status_code < 400
        except Exception as exc:
            log.warning("webhook_notify_failed", error=str(exc)[:120])
            return False


class SmtpProvider:
    def __init__(self, host: str, port: int, username: str, password: str, from_addr: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr

    async def send(self, *, subject: str, body: str, context: dict[str, Any]) -> bool:
        import asyncio
        import smtplib
        from email.message import EmailMessage

        def _send() -> None:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = str(context.get("to") or self.username)
            msg.set_content(body)
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(self.username, self.password)
                smtp.send_message(msg)

        try:
            await asyncio.get_running_loop().run_in_executor(None, _send)
            return True
        except Exception as exc:
            log.warning("smtp_notify_failed", error=str(exc)[:120])
            return False


class LineNotifyProvider:
    def __init__(self, token: str) -> None:
        self.token = token

    async def send(self, *, subject: str, body: str, context: dict[str, Any]) -> bool:
        message = f"{subject}\n{body}"[:1000]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://notify-api.line.me/api/notify",
                    headers={"Authorization": f"Bearer {self.token}"},
                    data={"message": message},
                )
                return resp.status_code < 400
        except Exception as exc:
            log.warning("line_notify_failed", error=str(exc)[:120])
            return False


def build_providers(channels: list[dict[str, Any]]) -> list[NotificationProvider]:
    providers: list[NotificationProvider] = []
    for ch in channels:
        kind = str(ch.get("type") or "").lower()
        if kind == "webhook" and ch.get("url"):
            providers.append(WebhookProvider(str(ch["url"])))
        elif kind == "smtp" and ch.get("host"):
            providers.append(
                SmtpProvider(
                    host=str(ch["host"]),
                    port=int(ch.get("port") or 587),
                    username=str(ch.get("username") or ""),
                    password=str(ch.get("password") or ""),
                    from_addr=str(ch.get("from") or ch.get("username") or ""),
                )
            )
        elif kind == "line" and ch.get("token"):
            providers.append(LineNotifyProvider(str(ch["token"])))
    return providers
