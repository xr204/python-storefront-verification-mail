from typing import Annotated

from fastapi import FastAPI
from pydantic import Field

from .infrai_email import InfraiEmailClient
from .order_notifications import (
    CheckoutReceiptRequest,
    OrderUpdateRequest,
    SignupRequest,
    StorefrontEvent,
    notify_customer,
)


app = FastAPI(title="Storefront customer email service")
EventBody = Annotated[
    SignupRequest | CheckoutReceiptRequest | OrderUpdateRequest,
    Field(discriminator="kind"),
]


@app.post("/notifications")
def send_notification(event: EventBody) -> dict[str, str]:
    result = notify_customer(event, InfraiEmailClient())
    return {"message_id": result.message_id}
