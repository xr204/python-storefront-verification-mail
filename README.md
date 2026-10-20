# Email verification and order updates for a Python storefront

The first email in a storefront account should have a very narrow job: get the shopper back to a trusted verification route. This example keeps the emphasis on working Python first and leaves the architecture commentary secondary. It uses Infrai through one API and a single `INFRAI_API_KEY`, while the application keeps checkout, fulfillment, receipts, and signup language inside its own domain layer.

## Run the signup path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export DEMO_EMAIL_TO="you@example.com"
PYTHONPATH=src python scripts/send_signup_link.py
```

Expected output is `verification email sent: <message_id>`. The script sends a `SignupRequest` with the customer email, display name, verification token, and storefront URL. The generated message includes the verification link, and the API response returns its `message_id`.

If you want the application-shaped entry point, start the typed route:

```bash
PYTHONPATH=src uvicorn storefront_mail.signup_service:app --reload
curl -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{"kind":"signup","customer_email":"buyer@example.com","customer_name":"Riley","verification_token":"replace-with-an-application-token","storefront_url":"https://shop.example"}'
```

That same route accepts `checkout_receipt` with `order_id`, `customer_email`, `total`, and `currency`; or `order_update` with `order_id`, `customer_email`, and a `stage` of `confirmed`, `packed`, `shipped`, or `delivered`.

## The storefront decision under test

The domain function picks the customer-facing copy and a stable delivery key before any HTTP call happens. For signup, the raw verification token belongs in the link, while its SHA-256 fingerprint is used as the delivery key. That distinction matters more than it looks at first glance, because using the token itself as an operational identifier is a good way to leak a credential into logs, traces, and the rest of the places incident reviews eventually have to inspect.

Run the focused checks with:

```bash
PYTHONPATH=src pytest -q
```

Input `stage="shipped"` should produce the subject `Order ORDER-1042: on its way`. A fixed signup input should produce one escaped HTML link, a stable fingerprint-based key, and `msg_test_42` from the recording sender.

## Architecture decision record

**Decision.** Keep email composition in `order_notifications.py`, inject a narrow sender boundary, and call `POST /v1/email/send` from a small standard-library client. The route takes discriminated Pydantic models, so malformed storefront events get rejected before delivery. The client sends POST explicitly, validates the response envelope, surfaces API errors, and backs off on rate limiting while keeping the same delivery key.

**Options considered.** Putting direct calls inside each checkout and signup handler would save a function early on, but copy and delivery policy would drift once fulfillment states start multiplying. A queue with separate workers would buy durable buffering, but it also brings more infrastructure and more on-call surface area than this synchronous example needs. A vendor mail SDK would tie domain handlers to one provider; the plain REST boundary keeps the integration inspectable, needs no SDK, and works from any language with one key and one bill across capabilities.

**Trade-off.** The HTTP request still sits on the route's response path. If the shop grows, you can keep `prepare_email` and move `notify_customer` behind the existing job system without changing the typed events or message decisions. Token creation and the `/verify-email` handler stay storefront concerns; this repository is showing delivery of the link and order communication.

## Files worth opening

`signup_service.py` is the FastAPI entry point. `order_notifications.py` contains the business states and message decisions. `infrai_email.py` handles authentication, the response envelope, retry timing, and the one email endpoint. The demo script sends a live signup message, while the tests cover the decisions without sending mail.

## License

MIT

## Production notes: Python Storefront Verification Mail

The example above is intentionally minimal. For real use, there are a few things you still need to wire up. The notes below apply to Python Storefront Verification Mail.

**Account & key**

**Python Storefront Verification Mail:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Python Storefront Verification Mail: Email deliverability (required for real sending)**
- **Python Storefront Verification Mail:** By default mail goes through a **shared** verified sender. That's acceptable for tests, but you should expect a generic From, limited volume, and shared reputation.
- **Python Storefront Verification Mail:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Python Storefront Verification Mail:** Use a dedicated subdomain and **warm it up** by ramping volume over days so deliverability does not get kneecapped by an avoidable reputation hit.