"""发布兼容层：应尽量修复而非丢弃。"""
from backend.app.domain.articles import validate_llm_polish_for_publish
from backend.app.polish_publish_compat import coerce_polish_output, ensure_publishable_polish, repair_polish_for_publish
from backend.app.text_display import body_is_connector_kv_metadata


def _minimal_apps_raw() -> dict:
    return {
        "title": "同步资源 · x · y",
        "summary": "短",
        "body_md": "",
        "feed_kind": "apps",
        "categories": ["高价值复刻"],
        "replication_tier": "B",
        "tabs": [
            {"label": "描述", "summary": "产品简介", "body_md": "产品定位与目标用户说明。" * 35},
            {"label": "功能亮点", "summary": "亮点", "body_md": "y" * 90},
        ],
    }


def test_coerce_maps_legacy_tab_to_data():
    out = coerce_polish_output(_minimal_apps_raw())
    labels = [t["label"] for t in out["tabs"]]
    assert "数据支撑" in labels
    assert "功能亮点" not in labels


def test_repair_makes_borderline_apps_publishable():
    snippet = '{"title":"TestApp","description":"' + ("d" * 200) + '","url":"https://example.com"}'
    fixed, fixes = repair_polish_for_publish(
        _minimal_apps_raw(),
        admin_source_key="product_hunt",
        snippet=snippet,
        rule_title="rule",
        rule_summary="规则摘要" * 10,
    )
    assert fixes
    assert validate_llm_polish_for_publish(fixed, admin_source_key="product_hunt")


def test_ensure_publishable_from_two_tabs():
    snippet = '{"title":"RealName","tagline":"' + ("t" * 100) + '"}'
    ready = ensure_publishable_polish(
        _minimal_apps_raw(),
        admin_source_key="github",
        snippet=snippet,
        rule_summary="摘要" * 20,
    )
    assert ready is not None
    assert validate_llm_polish_for_publish(ready, admin_source_key="github")


def test_repair_does_not_pad_ph_kv_into_description() -> None:
    """Product Hunt 字段表不得被 repair 垫进「描述」正文。"""
    snippet = (
        '{"name":"Wandesk","tagline":"Build Your Own AI Desktop",'
        '"votesCount":400,"website":"https://www.producthunt.com/r/x"}'
    )
    raw = {
        "title": "Wandesk",
        "summary": "短",
        "body_md": "",
        "feed_kind": "apps",
        "categories": ["应用产品"],
        "tabs": [
            {
                "label": "描述",
                "summary": "短",
                "body_md": "产品：Wandesk\n标语：Build Your Own AI Desktop\n投票：400\n官网：https://ph.com/r/x",
            },
        ],
    }
    fixed, _ = repair_polish_for_publish(
        raw,
        admin_source_key="product_hunt",
        snippet=snippet,
        rule_summary="规则摘要" * 12,
    )
    desc = next(t for t in fixed["tabs"] if t["label"] == "描述")
    assert not body_is_connector_kv_metadata(desc["body_md"])
    assert "产品：Wandesk" not in desc["body_md"]


def test_ensure_publishable_rejects_ph_kv_only_tabs() -> None:
    snippet = '{"name":"Wandesk","tagline":"Build AI Desktop","votesCount":1,"url":"https://ph.com/p"}'
    raw = {
        "title": "Wandesk",
        "summary": "短摘要",
        "feed_kind": "apps",
        "categories": ["应用产品"],
        "tabs": [
            {
                "label": "描述",
                "summary": "x" * 80,
                "body_md": "产品：Wandesk\n标语：tag\n投票：1\n官网：https://ph.com/p\n" + ("x" * 120),
            },
        ],
    }
    assert ensure_publishable_polish(raw, admin_source_key="product_hunt", snippet=snippet) is None
