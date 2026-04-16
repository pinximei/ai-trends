# Infrastructure Plan

## Runtime
- Backend: FastAPI (`backend/app/main.py`)
- Frontend pages: server-rendered templates under `backend/templates`
- Database: SQLite for local MVP, schema in `db/schema-v1.sql`

## Deployment Targets
- Frontend/API web: Render or Railway (public)
- Data DB: Supabase Postgres in production
- Object storage: Cloudflare R2 for raw payload backups
- Scheduler: GitHub Actions + internal protected run endpoint

## Security
- Public API and internal API separated by route and token policy
- Internal execution requires short-lived token + idempotency key
- Removal request lifecycle auditable via ticket id

## Observability and Gates
- Contract checks: `scripts/contract_test.py`
- Data quality checks: `monitoring/data_quality_gate.py`
- E2E/API tests: `tests/e2e/core/test_core_flow.py`
- CI workflow: `.github/workflows/ci-contract-test.yml`
