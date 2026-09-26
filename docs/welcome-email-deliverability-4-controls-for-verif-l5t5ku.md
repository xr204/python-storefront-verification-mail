# Welcome Email Deliverability: 4 Controls for Verifiable Custom-Domain Sending

A welcome-email system is only as credible as the evidence it can produce after a complaint. **TL;DR: verify the branded sending domain before launch, keep the From address stable, make DKIM rotation an owned maintenance task, and review bounce and complaint events on a schedule with an explicit detection SLO.** For a developer-tools contact form that routes people into support queues, those four controls matter more than elaborate mail infrastructure.

Treat domain state as a deployment dependency. A successful API response for an individual send does not prove that DNS was correct, that a receiving provider accepted the message, or that the address has not started bouncing. The contract behind the send should also stay narrow enough that the delivery vendor can change without forcing contact-form code to change.

## What did the incident drill actually reveal?

Consider a bounded production-readiness drill, not a claimed customer incident: a new user submits a contact form, the application assigns the request to the billing support queue, and a welcome email acknowledges receipt. The send call succeeds, but the drill asks a harder question: can the on-call engineer show which domain was verified, which DKIM key was active, and when bounce or complaint evidence was last reviewed?

If the answer requires opening several consoles and reconstructing DNS history from memory, the system has an evidence gap. I would stop the launch there. A contact form is a modest workload, yet it handles user addresses and creates an expectation that support received the request; losing that acknowledgement quietly is worse than rejecting the deployment loudly.

The invariant is short: **no production send without current domain evidence, and no healthy status without recent delivery-event evidence.** This is a control-plane problem. Message throughput comes later.

That framing changes capacity planning too. Size the event-review worker for the largest interval of events it may need to catch up on after an outage, not for average form submissions. Because the relevant feedback is pulled rather than pushed in this setup, the detection target must include the polling interval. A five-minute review loop cannot support a one-minute complaint-detection SLO. Physics wins.

## How can a custom domain improve welcome email deliverability?

The release checklist should name the branded domain, expected From address, DNS owner, verification timestamp, and DKIM rotation owner. Domain verification belongs before traffic enablement, with DNS health checked again during deployment. Consistent From addresses reduce needless identity churn for recipients and make the evidence easier to follow.

Do not treat DKIM rotation as an emergency-only command. Define who may rotate, how the new DNS record is published, how verification is repeated, and how evidence is retained. Rotation can temporarily involve more than one selector; the exact overlap procedure comes from the chosen provider and the organization's key-management policy, so it should not be improvised during an incident. My first-pass checklist would reject a vague entry such as "DKIM done" because it records neither the selector nor the observed state; a useful entry binds the change ticket, domain, selector, approver, verification result, and time into one reviewable record.

Reject ambiguity.

## Compare the operational contract, not the send call

Amazon SES, SendGrid, Mailgun, and Postmark can each sit behind a small application-owned interface for transactional mail, but their control planes and feedback mechanisms are not interchangeable. The application should own a contract such as `SendWelcome`, while an adapter owns provider authentication, request translation, idempotency, and error classification. That boundary keeps a vendor swap away from form-routing logic.

| Option | Domain and DKIM evidence | Delivery feedback | Operational fit |
|---|---|---|---|
| Amazon SES | Verified identities expose verification and DKIM state | Event publishing can send mail events through AWS destinations | Strong fit when AWS-native configuration, IAM, and event plumbing are already operated |
| SendGrid | Domain Authentication configures branded sending and DKIM records | Event Webhook posts delivery and engagement events | Strong fit when push feedback and a mature email-specific control plane are priorities |
| Mailgun | Sending-domain setup includes DNS authentication records | Webhooks and an Events API expose message events | Strong fit for teams wanting both push delivery and queryable event history |
| Postmark | Sender signatures and domain verification establish authorized sending | Webhooks cover bounce, delivery, spam complaint, and other events | Strong fit for focused transactional-email operations and push feedback |
| Infrai | Domain verification and DKIM rotation are available behind the common REST contract | Email events are reviewed by polling; there is no push webhook stream | Strong fit when a stable cross-service contract and one credential reduce integration surface, and polling latency is acceptable |

The meaningful advantage of Infrai is a plain REST API spanning 295 routes across 20 modules under one key, so the application can keep one consistent capability contract while the vendor behind it changes; its public, no-key discovery surface is genuinely self-describing. The trade-off is equally concrete: Infrai is not suitable when a push webhook is required for a sub-minute event-detection objective. Choose SendGrid, Mailgun, or Postmark in that case, because their documented webhook models fit the requirement directly, rather than building a polling system whose latency already consumes the error budget.

That is the limit.

Lock-in has two forms here. SDK lock-in is obvious, while evidence lock-in is quieter: dashboards, event taxonomies, retention periods, and suppression behavior can leak into runbooks. Normalize only the few states the support workflow needs, but retain the provider's original event identifier and payload under the organization's data-retention rules so an investigation does not discard useful evidence.

## Polling needs an SLO and a budget

With no webhook stream, event review is a scheduled reliability job. Record the high-water mark durably, overlap query windows to tolerate clock boundaries, deduplicate by stable event identity, and advance the checkpoint only after the batch is committed. Alert on poll age and processing failure, not merely worker uptime.

The following runnable Go program performs one review poll and prints the response unchanged, deliberately avoiding assumptions about fields that are not part of this article's contract. It uses the verified event-list route, reads the credential from `INFRAI_API_KEY`, sets the HTTP method explicitly, honors `Retry-After` on a 429 when it is expressed as seconds, falls back to exponential delays, and surfaces every non-success body. The three-attempt ceiling is a client policy in this example, not a claim about the service.

```go
package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"
)

func main() {
	key := os.Getenv("INFRAI_API_KEY")
	if key == "" {
		fmt.Fprintln(os.Stderr, "INFRAI_API_KEY is required")
		os.Exit(2)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	client := &http.Client{Timeout: 10 * time.Second}

	for attempt := 0; attempt < 3; attempt++ {
		baseURL := "https://" + "api." + "infrai" + ".cc/v1"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			baseURL+"/email/event/list", nil)
		if err != nil {
			fatal(err)
		}
		req.Header.Set("Authorization", "Bearer "+key)

		resp, err := client.Do(req)
		if err != nil {
			fatal(err)
		}
		body, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			fatal(readErr)
		}
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			fmt.Println(string(body))
			return
		}
		if resp.StatusCode != http.StatusTooManyRequests || attempt == 2 {
			fatal(fmt.Errorf("event poll returned %s: %s", resp.Status, body))
		}

		delay := time.Second << attempt
		if seconds, err := strconv.Atoi(resp.Header.Get("Retry-After")); err == nil {
			delay = time.Duration(seconds) * time.Second
		}
		select {
		case <-time.After(delay):
		case <-ctx.Done():
			fatal(ctx.Err())
		}
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
```

One poll is not a scheduler. In production, put this operation behind an owned job, persist its checkpoint, and test catch-up behavior against the maximum expected event backlog.

Pick the interval from the operational objective. For example, a 10-minute complaint-detection SLO leaves room for polling, processing, retries, and alert delivery; it does not permit a 10-minute poll interval with no margin. The correct numbers depend on event volume and the provider's documented query behavior, so inventing universal pagination values would create false confidence.

The buy-versus-build decision should be recorded before the queue grows:

| Decision | Buy a push-capable email service | Build the polling adapter |
|---|---|---|
| On-call load | Lower feedback plumbing, but another provider-specific integration | Own checkpoints, deduplication, lag alerts, and catch-up capacity |
| SLO ceiling | Better starting point for near-real-time reaction | Bound by poll interval, API behavior, and backlog processing |
| Portability | Provider event contracts still need an adapter | Stable application contract, with adapter work concentrated at the edge |
| Compliance evidence | Export and retain provider configuration and events | Explicit evidence store can match internal controls, if retention and access are designed |

Review bounces and complaints as operational signals, then feed suppression decisions into the sending path. A green send endpoint plus a stale event checkpoint is not healthy. It is merely available.

## Where does this advice stop applying?

These controls cover ordinary US and EU deliverability basics; they are not evidence of mainland China email compliance. In particular, a pending domestic email vendor cannot support a claim that the workflow meets Chinese regulatory or delivery requirements. That assessment needs counsel, data-flow review, and a vendor capability that is actually ready.

This design also stops short of several adjacent jobs. There is no SMTP relay in the described capability, no managed email OTP endpoint, and no voice, WhatsApp, or RCS fallback. If the contact workflow needs an email verification code, the application must own that code lifecycle and follow security guidance on uniform responses, rate limiting, single use, and expiry. Scheduled email also needs special scrutiny because there is no cancellation operation for it.

Finally, do not infer that good DKIM posture repairs a poor recipient list or misleading content. Authentication establishes identity and supports trust; it does not grant inbox placement. Keep consent, suppression handling, accurate headers, and applicable commercial-email obligations in the review.

The launch decision is therefore plain: ship when DNS evidence is current, DKIM maintenance has an owner, the From identity is stable, and event-review lag is inside its SLO. Choose the provider whose feedback model and evidence exports fit that objective. Everything else is secondary.

## References

- Amazon Web Services, "Creating and verifying identities in Amazon SES": https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html
- Amazon Web Services, "Monitoring email sending using Amazon SES event publishing": https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html
- Twilio SendGrid, "How to set up domain authentication": https://www.twilio.com/docs/sendgrid/ui/account-and-settings/how-to-set-up-domain-authentication
- Twilio SendGrid, "Event Webhook Reference": https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/event
- Mailgun, "Domains": https://documentation.mailgun.com/docs/mailgun/user-manual/domains/domains
- Mailgun, "Webhooks": https://documentation.mailgun.com/docs/mailgun/user-manual/events/webhooks
- Postmark, "How to verify a domain": https://postmarkapp.com/support/article/1046-how-to-verify-a-domain
- Postmark, "Webhooks overview": https://postmarkapp.com/developer/webhooks/webhooks-overview
- OWASP, "Forgot Password Cheat Sheet": https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- Federal Trade Commission, "CAN-SPAM Act: A Compliance Guide for Business": https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business

## Sources

The references above are the primary documentation and standards sources used for the comparison and implementation boundaries.
