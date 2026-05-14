"""连接器多段 pack 与 HF 列表 URL 判定（无 DB）。"""
from __future__ import annotations

import json

from backend.app import article_ingest as ing
from backend.app.connector_heat_fetch import huggingface_api_spaces_is_list_index
from backend.app.domain import articles as art


def test_extract_source_external_id_slug_fallback() -> None:
    payload = json.dumps({"slug": "acme-ai-launch", "name": "Acme"}, ensure_ascii=False)
    assert art.extract_source_external_id_from_connector_snippet(payload) == "acme-ai-launch"


def test_parse_connector_sync_item_snippets_pack() -> None:
    item_a = '{"id":"a"}'
    item_b = '{"id":"b"}'
    raw = json.dumps(
        {"connector_sync_items_v1": [{"snippet": item_a}, {"snippet": item_b}]},
        ensure_ascii=False,
    )
    assert ing.parse_connector_sync_item_snippets(raw) == [item_a, item_b]


def test_huggingface_api_spaces_is_list_index() -> None:
    assert huggingface_api_spaces_is_list_index("https://huggingface.co/api/spaces?limit=80")
    assert not huggingface_api_spaces_is_list_index("https://huggingface.co/api/spaces/foo/bar")
