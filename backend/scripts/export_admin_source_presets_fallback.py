"""Write frontend/admin/public/source-presets-fallback.json from services (run after changing presets)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.services import build_admin_source_preset_items  # noqa: E402

_payload = json.dumps({"items": build_admin_source_preset_items()}, ensure_ascii=False, indent=2) + "\n"
for rel in (
    "frontend/admin/public/source-presets-fallback.json",
    "frontend/admin/src/data/source-presets-fallback.json",
):
    p = _root.parent / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_payload, encoding="utf-8")
    print("wrote", p)
