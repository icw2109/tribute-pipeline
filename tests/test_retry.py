from core.crawl import crawl
from core.config import CrawlConfig

class DummyResp:
    def __init__(self, url: str, status_code: int, text: str = "<html><title>Ok</title><body>Content</body></html>"):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": "text/html; charset=utf-8"}


def test_retry_succeeds_after_failures():
    seed = "https://example.com/"
    attempts = {"count": 0}

    def fake_fetch(session, url, **kwargs):  # accept timeout/allow_redirects
        attempts["count"] += 1
        # First two attempts 503, third returns 200 success
        if attempts["count"] < 3:
            return DummyResp(url, 503)
        return DummyResp(url, 200)

    cfg = CrawlConfig(seed=seed, max_depth=0, max_pages=1, retry_attempts=4, retry_backoff_base=0.01)
    stats = {}
    out = list(crawl(cfg, fetch_func=fake_fetch, stats=stats))
    assert len(out) == 1, "Expected successful fetch after retries"
    # Ensure we actually retried twice before success => total attempts 3
    assert attempts["count"] == 3
    # stats should show only one fetched_ok
    assert stats.get("fetched_ok") == 1
