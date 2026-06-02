"""AI 入库结构与公开 API / 前台 TypeScript 契约一致性（无 DB）。"""
from __future__ import annotations

import json

from backend.app.domain import articles as art
from backend.app.domain.replication_analysis import FEED_CARD_TAB_REPLICATION
from tests.replication_fixtures import (
    sample_ai_usage_steps,
    sample_market_position,
    sample_replication_analysis,
)

_VALID_SUMMARY = "OpenAI 发布新模型系列，面向多模态与代码场景；核心提升上下文与推理能力；适合开发者与产品团队跟进。"
_VALID_BODY = "## 一句话看懂\n\n" + "背景与进展说明。" * 40
# validate_llm_polish_for_publish：「描述」tab 的 summary 不少于 72 字
_VALID_DESC_SUMMARY = (
    "描述 tab：用多句话说明事件主体、经过与结论，让读者不看标题也能懂发生了什么；"
    "此处为测试用长摘要，满足列表卡片与发布校验的最低字数门槛要求。。"
)


def _valid_tabs_news() -> list[dict]:
    return [
        {
            "label": "描述",
            "summary": _VALID_DESC_SUMMARY,
            "body_md": "## 描述\n\n" + "事件背景与参与方说明。" * 28,
        },
        {
            "label": "数据支撑",
            "summary": "数据支撑 tab：概括关键事实与数字。",
            "body_md": "## 数据支撑\n\n| 指标 | 数值 | 说明 |\n| --- | --- | --- |\n" + "| 示例 | 1 | 说明 |\n" * 12,
        },
    ]


def _valid_replication_analysis() -> dict:
    return sample_replication_analysis(worth=8, verdict="高价值")


def _valid_tabs_apps() -> list[dict]:
    return [
        {
            "label": "描述",
            "summary": _VALID_DESC_SUMMARY,
            "body_md": "## 描述\n\n" + "产品定位与使用场景说明。" * 28,
        },
        {
            "label": FEED_CARD_TAB_REPLICATION,
            "summary": "变现评估 tab：高价值方向，含阶段化工时与变现假设；技术栈常见，可在数周内搭 MVP 验证核心流程与付费意愿，满足发布校验字数。",
            "body_md": "## 变现评估\n\n" + "实现步骤与开源引用说明。" * 24,
        },
        {
            "label": "数据支撑",
            "summary": "数据支撑 tab：概括核心能力与可核对指标。",
            "body_md": "## 数据支撑\n\n| 指标 | 数值 | 说明 |\n| --- | --- | --- |\n" + "| 能力 | 支持 | 说明 |\n" * 12,
        },
    ]


def test_validate_llm_polish_relaxed_for_newsapi() -> None:
    """NewsAPI 原文偏短：略放宽「描述」tab 字数；仅强制「描述」Tab。"""
    tabs = _valid_tabs_news()
    tabs[0]["summary"] = tabs[0]["summary"][:65]
    tabs[0]["body_md"] = tabs[0]["body_md"][:100]
    data = {
        "title": "某 AI 公司融资",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY[:90],
        "categories": ["政策市场"],
        "feed_kind": "news",
        "tabs": tabs,
    }
    assert art.validate_llm_polish_for_publish(data) is False
    assert art.validate_llm_polish_for_publish(data, admin_source_key="newsapi") is True


def test_validate_llm_polish_accepts_minimal_valid_payload() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["大模型"],
        "feed_kind": "news",
        "tabs": _valid_tabs_news(),
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_validate_llm_polish_accepts_apps_tabs() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["应用产品"],
        "feed_kind": "apps",
        "tabs": _valid_tabs_apps(),
        "replication_analysis": _valid_replication_analysis(),
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_validate_llm_polish_accepts_other_bucket() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["其他"],
        "feed_kind": "news",
        "tabs": _valid_tabs_news(),
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_validate_llm_polish_rejects_two_categories() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["大模型", "开源工具"],
        "feed_kind": "news",
        "tabs": _valid_tabs_news(),
    }
    assert art.validate_llm_polish_for_publish(data) is False


def test_validate_llm_polish_rejects_unknown_canonical() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["不可识别标签XYZ"],
        "feed_kind": "news",
        "tabs": _valid_tabs_news(),
    }
    assert art.validate_llm_polish_for_publish(data) is False


def test_validate_llm_polish_rejects_wrong_tab_labels() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["应用产品"],
        "feed_kind": "apps",
        "tabs": [
            {"label": "产品概述", "summary": "x" * 50, "body_md": "## A\n\n" + "正文" * 40},
            {"label": "技术细节", "summary": "x" * 20, "body_md": "## B\n\n" + "正文" * 40},
        ],
    }
    assert art.validate_llm_polish_for_publish(data) is False


def test_validate_llm_polish_accepts_desc_only_tab() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["Agent"],
        "feed_kind": "news",
        "tabs": [
            {
                "label": "描述",
                "summary": _VALID_DESC_SUMMARY,
                "body_md": "## 描述\n\n" + "事件背景与参与方说明。" * 28,
            },
        ],
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_validate_llm_polish_rejects_api_json_in_tabs() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["应用产品"],
        "feed_kind": "apps",
        "tabs": _valid_tabs_apps(),
        "replication_analysis": _valid_replication_analysis(),
    }
    data["tabs"][2]["body_md"] = (
        '{"id": 1, "node_id": "MDEwOlJlcG9zaXRvcnk=", "followers_url": "https://api.github.com/users/x/followers"}'
    )
    assert art.validate_llm_polish_for_publish(data) is False


def test_validate_llm_polish_rejects_placeholder_title() -> None:
    data = {
        "title": "同步资源 · 板块 · GitHub",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["开源工具"],
        "feed_kind": "news",
        "tabs": _valid_tabs_news(),
    }
    assert art.validate_llm_polish_for_publish(data) is False


def test_primary_canonical_prefers_first_non_other() -> None:
    assert art.primary_canonical_from_raw_labels(["无关词", "开源工具", "foo"]) == "开源客户端(好抄)"


def test_display_categories_collapses_legacy_multi() -> None:
    legacy = json.dumps(["细分a", "应用观察", "zzz"], ensure_ascii=False)
    out = art.display_categories_for_article(legacy)
    assert out == ["应用产品"]


def test_parse_article_tabs_json_roundtrip_matches_frontend_keys() -> None:
    payload = [
        {"label": "栏一", "summary": "概要文字超过八个字", "body_md": "## 标题\n\nMarkdown **粗体** 正文。"},
        {"label": "栏二", "summary": "第二栏概要同样够长", "body_md": "- 列表项一\n- 列表项二\n\n补充说明凑够十六字。"},
    ]
    s = json.dumps(payload, ensure_ascii=False)
    out = art.parse_article_tabs_json(s)
    assert len(out) == 2
    for row in out:
        assert set(row.keys()) == {"label", "summary", "body_md"}
        assert row["label"]
        assert len(row["summary"]) >= 8
        assert len(row["body_md"]) >= 16


def test_parse_article_tabs_json_malformed_returns_empty() -> None:
    assert art.parse_article_tabs_json("not-json") == []
    assert art.parse_article_tabs_json('{"x":1}') == []


def test_ui_shape_warnings_clean_article() -> None:
    tabs = [
        {"label": "A", "summary": "概要一二三四五六七八", "body_md": "正文正文正文正文正文正文正文正文。"},
        {"label": "B", "summary": "概要二二三四五六七八", "body_md": "正文二正文二正文二正文二正文二正文二正文。"},
    ]
    warns = art.ui_shape_warnings_for_stored_article(
        ai_categories_json=json.dumps(["大模型"], ensure_ascii=False),
        ai_tabs_json=json.dumps(tabs, ensure_ascii=False),
        body="## 总览",
        summary="正常摘要长度足够。",
    )
    assert warns == []


def test_ui_shape_warnings_multi_legacy_categories() -> None:
    tabs = [
        {"label": "A", "summary": "概要一二三四五六七八", "body_md": "正文正文正文正文正文正文正文正文。"},
        {"label": "B", "summary": "概要二二三四五六七八", "body_md": "正文二正文二正文二正文二正文二正文二正文。"},
    ]
    warns = art.ui_shape_warnings_for_stored_article(
        ai_categories_json=json.dumps(["大模型", "开源"], ensure_ascii=False),
        ai_tabs_json=json.dumps(tabs, ensure_ascii=False),
        body="## 总览",
        summary="正常摘要长度足够。",
    )
    assert any("合并" in w or "多条" in w for w in warns)


def test_ui_shape_warnings_bad_tabs_json() -> None:
    warns = art.ui_shape_warnings_for_stored_article(
        ai_categories_json="[]",
        ai_tabs_json='[{"label":"x"}]',
        body="fallback",
        summary="摘要",
    )
    assert any("ai_tabs_json" in w for w in warns)
    assert any("分类" in w for w in warns)


def test_feed_lane_product_hunt_model_story_is_news() -> None:
    assert (
        art.feed_lane_for_article(
            "product_hunt",
            title="Llama 3.1 评测摘要",
            summary="开源权重与推理表现对比。",
            ai_categories_json=json.dumps(["大模型"], ensure_ascii=False),
        )
        == "news"
    )


def test_feed_lane_product_hunt_store_install_is_apps() -> None:
    assert (
        art.feed_lane_for_article(
            "product_hunt",
            title="Focus Timer",
            summary="Pomodoro for teams; download on Google Play and App Store.",
            ai_categories_json=json.dumps(["应用产品"], ensure_ascii=False),
        )
        == "apps"
    )


def test_feed_lane_product_hunt_launch_defaults_to_apps() -> None:
    assert (
        art.feed_lane_for_article(
            "product_hunt",
            title="Acme AI",
            summary="Ship faster with our new SaaS dashboard for teams.",
            ai_categories_json=json.dumps(["应用产品"], ensure_ascii=False),
        )
        == "apps"
    )


def test_feed_lane_github_stays_news_even_with_install_words() -> None:
    assert (
        art.feed_lane_for_article(
            "github",
            title="CLI tool",
            summary="brew install — desktop workflow",
            ai_categories_json=json.dumps(["开源工具"], ensure_ascii=False),
        )
        == "news"
    )


def test_feed_lane_huggingface_spaces_defaults_to_apps_except_agent_primary() -> None:
    assert (
        art.feed_lane_for_article(
            "huggingface_spaces",
            title="Demo Space",
            summary="Gradio UI hosted on Hugging Face.",
            ai_categories_json=json.dumps(["应用产品"], ensure_ascii=False),
        )
        == "apps"
    )
    assert (
        art.feed_lane_for_article(
            "huggingface_spaces",
            title="Demo",
            summary="LangChain agent playground in the browser.",
            ai_categories_json=json.dumps(["Agent"], ensure_ascii=False),
        )
        == "news"
    )


def test_extract_cover_image_product_hunt_thumbnail() -> None:
    payload = {
        "thumbnail": {"url": "https://ph-files.imgix.net/abc.png?auto=format"},
        "media": [{"type": "image", "url": "https://ph-files.imgix.net/other.png"}],
    }
    url = art.extract_cover_image_url("product_hunt", json.dumps(payload, ensure_ascii=False))
    assert url == "https://ph-files.imgix.net/abc.png?auto=format"


def test_extract_cover_image_product_hunt_media_fallback() -> None:
    payload = {"media": [{"type": "image", "url": "https://ph-files.imgix.net/fallback.png"}]}
    url = art.extract_cover_image_url("product_hunt", json.dumps(payload))
    assert url == "https://ph-files.imgix.net/fallback.png"


def test_extract_cover_image_hf_relative_thumbnail() -> None:
    payload = {"id": "org/demo-space", "cardData": {"thumbnail": "assets/cover.png"}}
    url = art.extract_cover_image_url("huggingface_spaces", json.dumps(payload))
    assert url == "https://huggingface.co/spaces/org/demo-space/resolve/main/assets/cover.png"


def test_extract_cover_image_hf_absolute_thumbnail() -> None:
    payload = {
        "id": "org/demo",
        "cardData": {"thumbnail": "https://huggingface.co/spaces/org/demo/resolve/main/x.png"},
    }
    url = art.extract_cover_image_url("huggingface_spaces", json.dumps(payload))
    assert url.endswith("/resolve/main/x.png")


def test_extract_cover_image_ignores_github() -> None:
    assert art.extract_cover_image_url("github", '{"thumbnail":{"url":"https://x.com/a.png"}}') is None


def test_article_detail_profile_by_source() -> None:
    assert art.article_detail_profile("github", "news") == art.DETAIL_PROFILE_OPEN_SOURCE
    assert art.article_detail_profile("product_hunt", "apps") == art.DETAIL_PROFILE_PRODUCT_LAUNCH
    assert art.article_detail_profile("hacker_news", "news") == art.DETAIL_PROFILE_NEWS_WIRE
    assert art.article_detail_profile("arxiv", "news") == art.DETAIL_PROFILE_NEWS_ARTICLE
    assert art.article_detail_profile("unknown_src", "apps") == art.DETAIL_PROFILE_APP_PRODUCT
    assert art.article_detail_profile("", "news") == art.DETAIL_PROFILE_NEWS_ARTICLE


def test_normalize_polish_tabs_renames_legacy_and_strips_json() -> None:
    from backend.app import article_ingest as ing

    tabs = [
        {
            "label": "功能亮点",
            "summary": "短摘要",
            "body_md": "说明。\n\n```json\n{\"stars\": 42}\n```",
        },
    ]
    ing._normalize_polish_tabs(tabs)
    assert tabs[0]["label"] == "数据支撑"
    assert "```json" not in tabs[0]["body_md"]


def test_validate_llm_polish_ignores_unknown_extra_tabs() -> None:
    data = {
        "title": "测试标题",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "categories": ["大模型"],
        "feed_kind": "news",
        "tabs": [
            {
                "label": "描述",
                "summary": _VALID_DESC_SUMMARY,
                "body_md": "## 描述\n\n" + "事件背景与参与方说明。" * 28,
            },
            {
                "label": "要点",
                "summary": "非规范 Tab 名会被忽略，不影响仅有「描述」的发布校验。",
                "body_md": "## 要点\n\n" + "- 要点\n" * 18,
            },
        ],
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_extract_source_original_url_json_html_url() -> None:
    payload = json.dumps({"title": "x", "html_url": "https://github.com/a/b/issues/1"}, ensure_ascii=False)
    assert art.extract_source_original_url_from_connector_snippet(payload) == "https://github.com/a/b/issues/1"


def test_extract_source_original_url_plain_text() -> None:
    s = 'noise See https://example.com/path?q=1 for more.'
    assert art.extract_source_original_url_from_connector_snippet(s) == "https://example.com/path?q=1"


def test_extract_source_original_url_nested_list() -> None:
    payload = json.dumps([{"url": "https://news.ycombinator.com/item?id=1"}], ensure_ascii=False)
    assert art.extract_source_original_url_from_connector_snippet(payload) == "https://news.ycombinator.com/item?id=1"


def test_extract_source_original_url_prefers_html_url_over_github_api() -> None:
    payload = json.dumps(
        {
            "url": "https://api.github.com/repos/foo/bar/issues/1",
            "html_url": "https://github.com/foo/bar/issues/1",
        },
        ensure_ascii=False,
    )
    assert art.extract_source_original_url_from_connector_snippet(payload) == "https://github.com/foo/bar/issues/1"


def test_extract_source_original_url_skips_oss_when_html_present() -> None:
    payload = json.dumps(
        {
            "cover": "https://bucket.oss-cn-hangzhou.aliyuncs.com/cover.jpg",
            "html_url": "https://example.com/article/1",
        },
        ensure_ascii=False,
    )
    assert art.extract_source_original_url_from_connector_snippet(payload) == "https://example.com/article/1"


def test_extract_source_original_url_only_cdn_returns_none() -> None:
    payload = json.dumps({"thumb": "https://d111111abcdef8.cloudfront.net/out.jpg"}, ensure_ascii=False)
    assert art.extract_source_original_url_from_connector_snippet(payload) is None


def test_extract_source_original_url_plain_text_skips_only_cdn() -> None:
    s = "see https://bucket.oss-cn-hangzhou.aliyuncs.com/a.jpg only"
    assert art.extract_source_original_url_from_connector_snippet(s) is None


def test_extract_source_external_id_hits_object_id() -> None:
    payload = json.dumps({"hits": [{"objectID": "hn-123", "url": "https://example.com/x"}]}, ensure_ascii=False)
    assert art.extract_source_external_id_from_connector_snippet(payload) == "hn-123"


def test_extract_source_external_id_items_node_id() -> None:
    payload = json.dumps({"items": [{"node_id": "MDEwOlJlcG9zaXRvcnkx", "id": 1}]}, ensure_ascii=False)
    assert art.extract_source_external_id_from_connector_snippet(payload) == "MDEwOlJlcG9zaXRvcnkx"


def test_extract_source_external_id_list_root() -> None:
    payload = json.dumps([{"id": 42, "title": "x"}], ensure_ascii=False)
    assert art.extract_source_external_id_from_connector_snippet(payload) == "42"


def test_extract_source_external_id_invalid_returns_none() -> None:
    assert art.extract_source_external_id_from_connector_snippet("not json") is None
    assert art.extract_source_external_id_from_connector_snippet("{}") is None


def test_extract_github_engagement_stargazers_and_trending_today() -> None:
    payload = json.dumps(
        {
            "stargazers_count": 12000,
            "trending_stars_today": 3991,
            "id": 1,
        },
        ensure_ascii=False,
    )
    m = art.extract_github_engagement_from_snippet(payload)
    assert m["stars_total"] == 12000
    assert m["stars_today"] == 3991


def test_extract_github_engagement_stars_today_from_aisoul_trending() -> None:
    payload = json.dumps(
        {
            "stargazers_count": 500,
            "_aisoul_trending": {"stars_today": 42},
        },
        ensure_ascii=False,
    )
    m = art.extract_github_engagement_from_snippet(payload)
    assert m["stars_total"] == 500
    assert m["stars_today"] == 42
