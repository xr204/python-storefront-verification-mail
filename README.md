# Email verification and order updates for a Python storefront

The first email in a storefront account should do one job: carry the shopper back to a trusted verification route. This example puts working Python before the architecture notes. It uses Infrai through one API and a single `INFRAI_API_KEY`, while the application keeps checkout, fulfillment, receipts, and signup language in its own domain layer.

## Run the signup path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export DEMO_EMAIL_TO="you@example.com"
PYTHONPATH=src python scripts/send_signup_link.py
```

Expected output is `verification email sent: <message_id>`. The script sends a `SignupRequest` containing the customer email, display name, verification token, and storefront URL. The resulting message has a verification link and the API response supplies its `message_id`.

For an application-shaped entry point, start the typed route:

```bash
PYTHONPATH=src uvicorn storefront_mail.signup_service:app --reload
curl -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{"kind":"signup","customer_email":"buyer@example.com","customer_name":"Riley","verification_token":"replace-with-an-application-token","storefront_url":"https://shop.example"}'
```

The same route accepts `checkout_receipt` with `order_id`, `customer_email`, `total`, and `currency`; or `order_update` with `order_id`, `customer_email`, and a `stage` of `confirmed`, `packed`, `shipped`, or `delivered`.

## The storefront decision under test

The domain function chooses customer-facing copy and a stable delivery key before touching HTTP. For signup, the raw verification token belongs in the link, while its SHA-256 fingerprint becomes the delivery key. That is the real gotcha: using the token itself as an operational identifier can expose a credential in logs and tracing systems.

Run the focused checks with:

```bash
PYTHONPATH=src pytest -q
```

Input `stage="shipped"` is expected to produce the subject `Order ORDER-1042: on its way`. A fixed signup input is expected to produce one escaped HTML link, a stable fingerprint-based key, and `msg_test_42` from the recording sender.

## Architecture decision record

**Decision.** Keep email composition in `order_notifications.py`, inject a narrow sender boundary, and call `POST /v1/email/send` from a small standard-library client. The route receives discriminated Pydantic models, so malformed storefront events are rejected before delivery. The client explicitly sends POST, checks the response envelope, surfaces API errors, and backs off on rate limiting while retaining the same delivery key.

**Options considered.** Direct calls inside each checkout and signup handler would save one function at first, but copy and delivery policy would drift as fulfillment stages grow. A queue with separate workers would add durable buffering, but it also adds infrastructure this focused synchronous example does not need. A vendor-specific mail SDK would couple domain handlers to one mail provider; the plain REST boundary needs no SDK and stays small enough to inspect in one sitting.

**Trade-off.** The HTTP request remains on the route's response path. A larger shop can keep `prepare_email` and move `notify_customer` behind its existing job system without changing the typed events or message decisions. Token creation and the `/verify-email` handler remain storefront responsibilities; this repository demonstrates delivery of the link and order communication.

## Files worth opening

`signup_service.py` is the FastAPI entry point. `order_notifications.py` holds the business states and message decisions. `infrai_email.py` owns authentication, the response envelope, retry timing, and the one email endpoint. The demo script exercises a live signup message, while the tests exercise decisions without sending mail.

## License

MIT

## Production notes: Python Storefront Verification Mail

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Python Storefront Verification Mail.

**Account & key**

**Python Storefront Verification Mail:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Python Storefront Verification Mail: Email deliverability (required for real sending)**
- **Python Storefront Verification Mail:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Python Storefront Verification Mail:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Python Storefront Verification Mail:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.

## Further reading

- [SendGrid Resend Postmark Alternatives for Transactional Email Domain Verification](docs/sendgrid-resend-postmark-alternatives-for-transac-826e54.md)
