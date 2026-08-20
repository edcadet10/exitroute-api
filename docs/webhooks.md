# Webhook integration

Create a subscription with an API key carrying `webhooks:manage`. The response
contains `signing_secret` exactly once. Store it as a credential and rotate it
through the subscription endpoint if exposure is suspected.

ExitRoute sends a canonical JSON body and these headers:

- `X-ExitRoute-Delivery`: stable delivery UUID
- `X-ExitRoute-Event`: event name such as `route.published`
- `X-ExitRoute-Timestamp`: Unix seconds used by the signature
- `X-ExitRoute-Signature`: `v1=` followed by a lowercase HMAC-SHA256 digest

The signed bytes are:

```text
<timestamp>.<exact request body bytes>
```

Verify the timestamp is within your replay window, compute HMAC-SHA256 with the
stored secret, compare digests in constant time, and only then parse/process the
body. Keep a durable record of delivery UUIDs so a retry cannot apply the same
event twice.

```python
import hashlib
import hmac
import time


def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    signed = timestamp.encode() + b"." + body
    expected = "v1=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Return any 2xx after durably accepting the event. ExitRoute retries network
errors, 408, 425, 429, and 5xx responses with bounded exponential backoff.
Other 4xx responses and exhausted retries become `dead` and remain inspectable
through the delivery-history endpoint.

Destinations must use HTTPS port 443 and resolve only to globally routable IPs.
Redirects are never followed. DNS is checked at subscription creation and every
attempt; the worker connects to a checked address while using the original host
for TLS certificate verification.
