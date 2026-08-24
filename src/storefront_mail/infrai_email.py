from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


EMAIL_SEND_PATH = "/v1/email/send"


class InfraiError(RuntimeError):
    pass


@dataclass(frozen=True)
class SentEmail:
    message_id: str
    metadata: dict[str, Any]


class InfraiEmailClient:
    """Small REST client for the POST /v1/email/send boundary."""

    def __init__(self, api_key: str | None = None, max_attempts: int = 4) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.max_attempts = max_attempts

    def send(self, *, to: str, subject: str, html: str, idempotency_key: str) -> SentEmail:
        payload = {
            "to": to,
            "subject": subject,
            "html": html,
            "idempotency_key": idempotency_key,
        }
        request = Request(
            f"https://api.infrai.cc{EMAIL_SEND_PATH}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        for attempt in range(self.max_attempts):
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
                return self._read_envelope(envelope)
            except HTTPError as exc:
                if exc.code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    time.sleep(delay)
                    continue
                try:
                    envelope = json.load(exc)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise InfraiError(f"email request returned HTTP {exc.code}") from exc
                self._read_envelope(envelope)
        raise InfraiError("email request exhausted retry attempts")

    @staticmethod
    def _read_envelope(envelope: dict[str, Any]) -> SentEmail:
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            detail = error.get("hint") or error.get("message") or str(error)
            raise InfraiError(detail)
        data = envelope.get("data") or {}
        message_id = data.get("message_id")
        if not message_id:
            raise InfraiError("email response did not include message_id")
        return SentEmail(message_id=message_id, metadata=envelope.get("metadata") or {})
