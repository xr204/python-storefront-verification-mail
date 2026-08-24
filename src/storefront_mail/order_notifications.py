from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Literal, Protocol
from urllib.parse import urlencode

from pydantic import BaseModel, EmailStr, Field

from .infrai_email import SentEmail


class SignupRequest(BaseModel):
    kind: Literal["signup"]
    customer_email: EmailStr
    customer_name: str = Field(min_length=1)
    verification_token: str = Field(min_length=16)
    storefront_url: str = Field(pattern=r"^https?://")


class CheckoutReceiptRequest(BaseModel):
    kind: Literal["checkout_receipt"]
    order_id: str = Field(min_length=1)
    customer_email: EmailStr
    total: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class OrderUpdateRequest(BaseModel):
    kind: Literal["order_update"]
    order_id: str = Field(min_length=1)
    customer_email: EmailStr
    stage: Literal["confirmed", "packed", "shipped", "delivered"]


StorefrontEvent = SignupRequest | CheckoutReceiptRequest | OrderUpdateRequest


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    html: str
    idempotency_key: str


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, html: str, idempotency_key: str) -> SentEmail:
        pass


def prepare_email(event: StorefrontEvent) -> OutgoingEmail:
    if isinstance(event, SignupRequest):
        query = urlencode({"token": event.verification_token})
        link = f"{event.storefront_url.rstrip('/')}/verify-email?{query}"
        token_fingerprint = hashlib.sha256(event.verification_token.encode()).hexdigest()
        return OutgoingEmail(
            to=str(event.customer_email),
            subject="Verify your email to finish creating your account",
            html=(
                f"<p>Hi {escape(event.customer_name)},</p>"
                f'<p><a href="{escape(link, quote=True)}">Verify email</a> to finish setting up your storefront account.</p>'
            ),
            idempotency_key=f"signup-verification:{token_fingerprint}",
        )

    if isinstance(event, CheckoutReceiptRequest):
        amount = f"{event.total:.2f} {event.currency.upper()}"
        return OutgoingEmail(
            to=str(event.customer_email),
            subject=f"Receipt for order {event.order_id}",
            html=f"<p>Payment received for order <strong>{escape(event.order_id)}</strong>: {escape(amount)}.</p>",
            idempotency_key=f"checkout-receipt:{event.order_id}",
        )

    stage_labels = {
        "confirmed": "confirmed",
        "packed": "packed",
        "shipped": "on its way",
        "delivered": "delivered",
    }
    label = stage_labels[event.stage]
    return OutgoingEmail(
        to=str(event.customer_email),
        subject=f"Order {event.order_id}: {label}",
        html=f"<p>Your order <strong>{escape(event.order_id)}</strong> is {escape(label)}.</p>",
        idempotency_key=f"order-update:{event.order_id}:{event.stage}",
    )


def notify_customer(event: StorefrontEvent, sender: EmailSender) -> SentEmail:
    email = prepare_email(event)
    return sender.send(
        to=email.to,
        subject=email.subject,
        html=email.html,
        idempotency_key=email.idempotency_key,
    )
