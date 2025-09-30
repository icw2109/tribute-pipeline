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


def test_content_dedupe():
    seed = "https://example.com/a"
    html = "<html><title>Same</title><body><p>Identical Body Content</p></body></html>"
    pages = ["https://example.com/a","https://example.com/b"]
    calls = {"i":0}
    def fake_fetch(session, url, **kwargs):
        # return same content but alternate final url sequence based on queue
        return DummyResp(pages[calls["i"]])
    # We'll manually enqueue the second page by making the first page link to it.
    def fake_fetch_with_link(session, url, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        # Make body text identical after extraction (avoid anchor introducing different text ordering)
        if i == 0:
            # Empty anchor ensures link discovery without altering visible text
            return DummyResp(pages[0], f"<html><title>Same</title><body><a href='{pages[1]}'></a><p>Identical Body Content</p></body></html>")
        else:
            return DummyResp(pages[1], html)

    cfg = CrawlConfig(seed=seed, max_depth=1, max_pages=5, rps=10.0, enable_content_dedupe=True)
    stats = {}
    out = list(crawl(cfg, fetch_func=fake_fetch_with_link, stats=stats))
    # Expect only the first page yielded, second skipped as duplicate content
    assert any(r['url']==pages[0] for r in out)
    assert not any(r['url']==pages[1] for r in out)
    assert stats.get('duplicates_content',0) == 1
