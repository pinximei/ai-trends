# Internal Security Runbook

## Mode A (recommended)
- Private runner in private network.
- Internal APIs not publicly routable.

## Mode B (public protected gateway)
- Use OIDC exchange to short-lived token.
- Require `idempotency_key` for every trigger.
- Reject anonymous requests.
- Log `run_id` and `request_id` for audit.

## Required Endpoints
- `POST /internal/run`
- `GET /internal/runs/{run_id}`

## Idempotency Rules
- Same `idempotency_key` returns same `run_id` within time window.
- Repeated request must not create duplicated jobs.
