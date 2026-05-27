"""每日摘要排版：分栏、邮件纯文本、飞书正文。"""
from __future__ import annotations

from types import SimpleNamespace

from backend.app.newsletter_digest_format import (
    build_digest_body_from_articles,
    build_digest_subject_default,
    digest_delivery_texts,
    enrich_digest_read_links,
    format_digest_for_delivery,
    normalize_digest_body_md,
)


def test_build_body_highlight_and_more_sections() -> None:
    apps = [
        SimpleNamespace(
            id=1,
            title="App One",
            summary="x" * 300,
            replication_tier="A",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        ),
        SimpleNamespace(
            id=2,
            title="App Two",
            summary="short",
            replication_tier="B",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        ),
        SimpleNamespace(
            id=3,
            title="App Three",
            summary="third",
            replication_tier="",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        ),
        SimpleNamespace(
            id=4,
            title="App Four",
            summary="fourth",
            replication_tier="",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        ),
    ]
    body = build_digest_body_from_articles(apps, [], highlight_apps=2, highlight_news=0)
    assert "## 高价值应用" in body
    assert "## 今日应用" in body
    assert "## 更多应用" in body
    assert "**介绍**：" in body
    assert "### 1. App One" in body
    assert "文章 #4" in body
    intro_line = next(l for l in body.splitlines() if l.startswith("- **介绍**："))
    assert len(intro_line) <= 240


def test_build_body_only_highlights_when_few_items() -> None:
    apps = [
        SimpleNamespace(
            id=1,
            title="Only",
            summary="one",
            replication_tier="A",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        )
    ]
    body = build_digest_body_from_articles(apps, [], highlight_apps=3)
    assert "## 今日应用" in body
    assert "## 更多应用" not in body


def test_build_body_shows_tier_only_with_deep_replication() -> None:
    import json

    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    repl = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
    apps = [
        SimpleNamespace(
            id=1,
            title="Deep",
            summary="ok",
            replication_tier="S",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
            replication_analysis_json=json.dumps(repl, ensure_ascii=False),
        ),
        SimpleNamespace(
            id=2,
            title="Shallow",
            summary="ok",
            replication_tier="S",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
        ),
    ]
    from backend.app.newsletter_replication import article_high_value_for_digest, split_deep_replicable_apps

    assert article_high_value_for_digest(apps[0]) is True
    assert article_high_value_for_digest(apps[1]) is False
    high_lane, regular_lane = split_deep_replicable_apps(apps)
    assert [a.title for a in high_lane] == ["Deep"]
    assert [a.title for a in regular_lane] == ["Shallow"]

    body = build_digest_body_from_articles(apps, [], highlight_apps=3)
    assert "Deep" in body
    assert "Shallow" in body


def test_build_subject_default() -> None:
    subj = build_digest_subject_default("2026-05-19", [SimpleNamespace(id=1)], [SimpleNamespace(id=2)])
    assert "2026-05-19" in subj


def test_normalize_collapses_blank_lines() -> None:
    raw = "## 亮点应用\n\n\n\n### 1. X"
    out = normalize_digest_body_md(raw)
    assert "\n\n\n" not in out


def test_enrich_read_links() -> None:
    body = "- **站内阅读**：文章 #7"
    article = SimpleNamespace(id=7)
    out = enrich_digest_read_links(
        body,
        public_site_base_url="https://www.ai-trends.news",
        article_by_id={7: article},
    )
    assert "https://www.ai-trends.news/resources/7" in out


def test_delivery_texts_have_section_headers() -> None:
    md = """## 高价值应用

> 编辑推荐 Top 1 条

### 1. 测试产品
- **介绍**：一句话
- **为何关注**：复刻向
- **站内阅读**：文章 #1

## 本周必读

> 今日暂无新稿。
"""
    email, feishu = digest_delivery_texts(
        md,
        "今日 AI 精选",
        digest_date="2026-05-19",
        public_site_base_url="https://example.com",
        apps_count=1,
        news_count=0,
    )
    assert "【高价值应用】" in email
    assert "【本周必读】" in email
    assert "📬 AI 产品雷达" in feishu
    assert "应用 1 条" in feishu
    assert "【高价值应用】" in feishu
    assert "━━━━━━━━" not in feishu
    assert "1. 测试产品" in feishu
    assert "  介绍：" in feishu


def test_format_digest_for_delivery() -> None:
    apps = [SimpleNamespace(id=3)]
    md, email, feishu = format_digest_for_delivery(
        "## 今日应用\n\n### 1. X\n- **站内阅读**：文章 #3\n\n## 本周必读\n\n> 今日暂无新稿。",
        "标题",
        digest_date="2026-05-19",
        public_site_base_url="https://site.test",
        apps=apps,
        news=[],
    )
    assert "/resources/3" in md
    assert "【今日应用】" in email
    assert len(feishu) > 20
    assert "━━━━━━━━" not in feishu
    assert "【今日应用】" in feishu
