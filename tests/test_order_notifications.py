from storefront_mail.infrai_email import SentEmail
from storefront_mail.order_notifications import OrderUpdateRequest, SignupRequest, notify_customer


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, html: str, idempotency_key: str) -> SentEmail:
        self.sent.append(
            {"to": to, "subject": subject, "html": html, "idempotency_key": idempotency_key}
        )
        return SentEmail(message_id="msg_test_42", metadata={})


def test_signup_sends_a_verification_link_with_a_stable_business_key() -> None:
    sender = RecordingSender()
    event = SignupRequest(
        kind="signup",
        customer_email="buyer@example.com",
        customer_name="Sam & Jo",
        verification_token="fixed-token-for-test",
        storefront_url="https://shop.example",
    )

    result = notify_customer(event, sender)

    sent = sender.sent[0]
    assert result.message_id == "msg_test_42"
    assert sent["subject"] == "Verify your email to finish creating your account"
    assert "https://shop.example/verify-email?token=fixed-token-for-test" in sent["html"]
    assert "Sam &amp; Jo" in sent["html"]
    assert sent["idempotency_key"].startswith("signup-verification:")
    assert "fixed-token-for-test" not in sent["idempotency_key"]


def test_shipped_order_uses_the_customer_facing_fulfillment_state() -> None:
    sender = RecordingSender()
    event = OrderUpdateRequest(
        kind="order_update",
        order_id="ORDER-1042",
        customer_email="buyer@example.com",
        stage="shipped",
    )

    notify_customer(event, sender)

    assert sender.sent[0]["subject"] == "Order ORDER-1042: on its way"
    assert sender.sent[0]["idempotency_key"] == "order-update:ORDER-1042:shipped"
