"""各数据源入库策略：价值分、上游 id、素材计数。"""
import json

from backend.app.domain.articles import (
    connector_upstream_has_ingest_material,
    extract_source_external_id_from_connector_snippet,
    rule_value_score,
    value_score_min_for_source,
)


def test_product_hunt_prefers_slug_as_external_id():
    snip = json.dumps({"source": "product_hunt", "slug": "wandesk", "id": "1046734", "name": "Wandesk"})
    assert extract_source_external_id_from_connector_snippet(snip) == "wandesk"


def test_acquire_url_as_external_id():
    snip = json.dumps({"url": "https://acquire.com/l/abc", "name": "AI SaaS"})
    assert extract_source_external_id_from_connector_snippet(snip) == "https://acquire.com/l/abc"


def test_short_ph_pack_passes_rule_score():
    snip = json.dumps({"name": "ToolX", "tagline": "AI writing assistant for teams", "votesCount": 100})
    vs = rule_value_score(snippet=snip, summary="x", http_status=200)
    assert vs >= value_score_min_for_source("product_hunt")


def test_hn_title_counts_as_upstream_material():
    snip = json.dumps(
        {
            "title": "Show HN: A long enough English headline about machine learning systems",
            "url": "https://example.com",
            "objectID": "99",
        }
    )
    ok, _ = connector_upstream_has_ingest_material(snip, "hacker_news")
    assert ok is True
