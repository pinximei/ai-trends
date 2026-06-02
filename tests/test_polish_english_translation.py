"""英文连接器素材须识别为需译中文。"""
from backend.app.domain.articles import (
    connector_snippet_likely_english,
    polish_text_needs_zh_translation,
)
from backend.app.llm_service import _polish_translation_user_note


def test_polish_text_needs_zh_translation_english_body() -> None:
    en = (
        "Microsoft announced a major update to Xbox promotional materials after fans "
        "criticized the use of rival logos in its streaming show."
    ) * 3
    assert polish_text_needs_zh_translation(en)
    assert not polish_text_needs_zh_translation("这是一段足够长的中文正文。" * 20)


def test_connector_snippet_likely_english_newsapi() -> None:
    snippet = (
        '{"source":"newsapi","title":"Xbox adjusts promo","description":"'
        + ("Fans slammed the decision. " * 15)
        + '","url":"https://example.com/a"}'
    )
    assert connector_snippet_likely_english(snippet, admin_source_key="newsapi")
    assert _polish_translation_user_note(admin_source_key="newsapi", snippet=snippet).startswith("【语言")


def test_connector_snippet_chinese_not_forced() -> None:
    snippet = '{"title":"国产大模型发布","description":"' + ("技术突破。" * 40) + '"}'
    assert not connector_snippet_likely_english(snippet, admin_source_key="product_hunt")
