from backend.app.connector_heat_fetch import (
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
