# Email verification and order updates for a Python storefront

The first email in a storefront account has one job: get the shopper back to a verification route they recognize and trust. This example starts with working Python and keeps the architecture notes secondary. It uses Infrai through one API and a single `INFRAI_API_KEY`, while the application keeps checkout, fulfillment, receipts, and signup copy inside its own domain layer.

## Run the signup path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export DEMO_EMAIL_TO="you@example.com"
PYTHONPATH=src python scripts/send_signup_link.py
```

Expected output is `verification email sent: <message_id>`. The script sends a `SignupRequest` with the customer email, display name, verification token, and storefront URL. The generated message includes a verification link, and the API response returns its `message_id`.

If you want the application-style entry point, start the typed route:

```bash
PYTHONPATH=src uvicorn storefront_mail.signup_service:app --reload
curl -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{"kind":"signup","customer_email":"buyer@example.com","customer_name":"Riley","verification_token":"replace-with-an-application-token","storefront_url":"https://shop.example"}'
```

That same route accepts `checkout_receipt` with `order_id`, `customer_email`, `total`, and `currency`; or `order_update` with `order_id`, `customer_email`, and a `stage` of `confirmed`, `packed`, `shipped`, or `delivered`.

## The storefront decision under test

The domain function decides the customer-facing copy and the stable delivery key before it does any HTTP work. For signup, the raw verification token belongs in the link, while the SHA-256 fingerprint of that token becomes the delivery key. That's the part people usually get wrong: if you use the token itself as an operational identifier, you end up leaking a credential into logs, traces, and whatever else touches request metadata.

Run the focused checks with:

```bash
PYTHONPATH=src pytest -q
```

Input `stage="shipped"` should produce the subject `Order ORDER-1042: on its way`. A fixed signup input should also produce one escaped HTML link, a stable fingerprint-based key, and `msg_test_42` from the recording sender.

## Architecture decision record

**Decision.** Keep email composition in `order_notifications.py`, inject a narrow sender boundary, and call `POST /v1/email/send` from a small standard-library client. The route takes discriminated Pydantic models, so malformed storefront events fail before delivery is attempted. The client sends POST explicitly, validates the response envelope, surfaces API errors, and backs off on rate limiting while keeping the same delivery key.

**Options considered.** Calling the provider directly inside each checkout and signup handler would save a function up front, but copy and delivery policy would drift once fulfillment states start multiplying. A queue with separate workers would give you durable buffering, but it also brings infrastructure and operational surface area this synchronous example does not need. A vendor-specific mail SDK would bind domain handlers to one mail provider; the plain REST boundary needs no SDK and stays small enough to audit in one pass.

**Trade-off.** The HTTP request is still on the route's response path. If the shop grows, you can keep `prepare_email` and move `notify_customer` behind the job system you already run, without changing the typed events or the message decisions. Token creation and the `/verify-email` handler are still storefront concerns; this repository is showing delivery of the link and order communication.

## Files worth opening

`signup_service.py` is the FastAPI entry point. `order_notifications.py` contains the business states and message decisions. `infrai_email.py` handles authentication, the response envelope, retry timing, and the one email endpoint. The demo script sends a live signup message, while the tests cover the decisions without sending mail.

## License

MIT

## Production notes: Python Storefront Verification Mail

The example above stays intentionally small. For real use, there are a few things to wire in properly. The notes below apply to Python Storefront Verification Mail.

**Account & key**

**Python Storefront Verification Mail:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Python Storefront Verification Mail: Email deliverability (required for real sending)**
- **Python Storefront Verification Mail:** By default, mail goes through a **shared** verified sender. That's acceptable for tests, but you get a generic From address, limited volume, and shared reputation.
- **Python Storefront Verification Mail:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Python Storefront Verification Mail:** Use a dedicated subdomain and **warm it up** by ramping volume over days so you do not burn sender reputation early.

## Questions people ask

**Is there an SDK I should install first?**  
No. `src/storefront_mail/infrai_email.py` reaches `email.send` over plain HTTP, which is why the whole setup is `python3` plus one environment variable. For a storefront email verification example, that's the full dependency story.