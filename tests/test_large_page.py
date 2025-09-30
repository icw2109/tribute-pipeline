from core.crawl import crawl
from core.config import CrawlConfig

class DummyResp:
    def __init__(self, url: str, status_code: int = 200, text: str = ""):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": "text/html; charset=utf-8"}


def test_large_page_handled():
    seed = "https://example.com/"
    big_text_segment = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 2000  # ~100k chars
    html = f"<html><head><title>Big</title></head><body><p>{big_text_segment}</p></body></html>"

    def fake_fetch(session, url, **kwargs):
        return DummyResp(url, 200, html)

    cfg = CrawlConfig(seed=seed, max_depth=0, max_pages=1)
    out = list(crawl(cfg, fetch_func=fake_fetch))
    assert len(out) == 1
    rec = out[0]
    assert rec["title"] == "Big"
    # Ensure large body captured and truncated not zero
    assert len(rec["text"]) > 50000  # should retain large content
