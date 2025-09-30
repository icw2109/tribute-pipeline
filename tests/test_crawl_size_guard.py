import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.crawl import crawl
from core.config import CrawlConfig

class DummyResp:
    def __init__(self, url: str, text: str):
        self.url = url
        self.text = text
        self.status_code = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}


def test_size_guard():
    seed = "https://example.com/"
    big = "<html><title>Big</title><body>" + ("X" * 900_000) + "</body></html>"  # ~900KB
    def fake_fetch(session, url, **kwargs):
        return DummyResp(seed, big)
    cfg = CrawlConfig(seed=seed, max_depth=0, max_pages=1, max_html_bytes=200_000)  # 200KB limit
    stats = {}
    out = list(crawl(cfg, fetch_func=fake_fetch, stats=stats))
    assert out == []  # skipped
    assert stats.get('skipped_too_large',0) == 1
    assert stats.get('fetched_ok',0) == 0
