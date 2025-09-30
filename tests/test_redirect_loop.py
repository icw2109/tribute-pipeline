from core.crawl import crawl
from core.config import CrawlConfig

# Simulate a redirect loop A -> B -> A by crafting responses.

class DummyResp:
    def __init__(self, url: str, status_code: int = 200, text: str = "<html><title>Ok</title><body>Loop</body></html>"):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": "text/html"}


def test_redirect_loop_breaks():
    seed = "https://example.com/a"
    # We'll alternate returned final URLs to simulate following redirects handled internally
    calls = {"n": 0}
    final_urls = ["https://example.com/b", "https://example.com/a"]  # cycle

    def fake_fetch(session, url, **kwargs):
        idx = calls["n"] % len(final_urls)
        calls["n"] += 1
        return DummyResp(final_urls[idx])

    cfg = CrawlConfig(seed=seed, max_depth=1, max_pages=5, rps=5.0)
    stats = {}
    out = list(crawl(cfg, fetch_func=fake_fetch, stats=stats))
    # Ensure we actually fetched something and terminated (no infinite loop)
    assert stats.get("fetched_ok", 0) >= 1
    assert len(out) <= 2
