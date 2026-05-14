"""Print admin source presets JSON from the database (stdout only).

Previously this script wrote frontend static JSON; presets are now served only from
`admin_source_configs` via GET /api/admin/v1/sources/presets. Use this for local inspection:

  cd backend && python scripts/export_admin_source_presets_fallback.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data_api_service import DataApiService  # noqa: E402
from app.db import SessionLocal, ensure_schema_compatibility  # noqa: E402


def main() -> None:
    ensure_schema_compatibility()
    db = SessionLocal()
    try:
        items = DataApiService(db).list_admin_source_presets()
        print(json.dumps({"items": items}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
