# Page to API Mapping (P0)

| Page | APIs |
|---|---|
| `/` | `GET /api/v1/dashboard/summary`, `GET /api/v1/trends` |
| `/inspirations` | `GET /api/v1/inspirations` |
| `/trends` | `GET /api/v1/trends`, `GET /api/v1/meta/taxonomy` |
| `/trend/[trendKey]` | `GET /api/v1/trends/{trend_key}`, `GET /api/v1/trends/{trend_key}/timeline` |
| `/evidence/[signalId]` | `GET /api/v1/evidences/{signal_id}` |
| `/categories` | `GET /api/v1/categories` |
| `/methodology` | `GET /api/v1/meta/methodology` |
| `/legal/removal-request` | `POST /api/v1/compliance/removal-requests`, `GET /api/v1/compliance/removal-requests/{ticket_id}?token=...` |
