from backend.app.connector_heat_fetch import (
    _github_backfill_payloads_from_ranked,
    github_trending_is_discovery_url,
    parse_github_trending_repos,
)

SAMPLE_HTML = """
<html><body>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/owner-one/repo-alpha">repo-alpha</a>
  </h2>
  <span class="d-inline-block float-sm-right">2,500 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/owner-two/repo-beta">repo-beta</a></h2>
  <span>120 stars today</span>
</article>
</body></html>
"""


def test_github_trending_is_discovery_url() -> None:
    assert github_trending_is_discovery_url("https://github.com/trending?since=daily")
    assert not github_trending_is_discovery_url("https://api.github.com/repos/a/b")


def test_parse_github_trending_repos() -> None:
    rows = parse_github_trending_repos(SAMPLE_HTML, limit=10)
    assert len(rows) == 2
    assert rows[0]["full_name"] == "owner-one/repo-alpha"
    assert rows[0]["stars_today"] == 2500
    assert rows[1]["full_name"] == "owner-two/repo-beta"
    assert rows[1]["stars_today"] == 120


def test_github_backfill_when_filter_thins_pack() -> None:
    payloads: list[dict] = [{"full_name": "a/b", "name": "b"}]
    ranked = [
        {"full_name": "a/b", "rank": 1},
        {"full_name": "x/y", "rank": 2, "description": "desktop electron client"},
        {"full_name": "p/q", "rank": 3, "description": "cli tool"},
    ]
    _github_backfill_payloads_from_ranked(payloads, ranked, n=3, since="daily", discovery_url="https://github.com/trending")
    assert len(payloads) == 3
    assert payloads[-1].get("full_name") == "p/q"
    assert payloads[-1].get("_aisoul_trending", {}).get("filter_fallback") is True
