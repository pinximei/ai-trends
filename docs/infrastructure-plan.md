# Infrastructure Plan

## Runtime
- Backend: FastAPI (`backend/app/main.py`)
- Frontend: Vite apps under `frontend/`（公开站）与 `frontend/admin/`（管理端）；后端仅提供 API
- Database: **PostgreSQL**（本地 `docker compose`；连接串见 `backend/.env.example`）

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
- API smoke tests: `pytest tests/`（见 `pyproject.toml`）
- Data quality checks: `monitoring/data_quality_gate.py`
- CI workflow: `.github/workflows/ci.yml`
