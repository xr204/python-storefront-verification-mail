import os

from storefront_mail.infrai_email import InfraiEmailClient
from storefront_mail.order_notifications import SignupRequest, notify_customer


def main() -> None:
    recipient = os.environ.get("DEMO_EMAIL_TO")
    if not recipient:
        raise SystemExit("DEMO_EMAIL_TO is required")
    event = SignupRequest(
        kind="signup",
        customer_email=recipient,
        customer_name="Avery",
        verification_token="demo-verification-token-2026",
        storefront_url="https://shop.example",
    )
    result = notify_customer(event, InfraiEmailClient())
    print(f"verification email sent: {result.message_id}")


if __name__ == "__main__":
    main()
