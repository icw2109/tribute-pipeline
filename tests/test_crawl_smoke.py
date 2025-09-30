import os, json, tempfile, pathlib
from core.crawl import crawl
from core.config import CrawlConfig

# A minimal smoke test using example.com (static, stable) depth 0

def test_crawl_example_dot_com_depth0():
    seed = "https://example.com/"
    cfg = CrawlConfig(seed=seed, max_depth=0, max_pages=1, rps=2.0)
    out = list(crawl(cfg))
    assert len(out) == 1
    rec = out[0]
    assert rec["url"].startswith(seed)
    assert rec["depth"] == 0
    # text might be short but should contain Example Domain
    assert "Example" in rec["text"]
