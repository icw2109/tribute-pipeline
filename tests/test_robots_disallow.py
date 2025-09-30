import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.crawl import crawl  # type: ignore
from core.config import CrawlConfig  # type: ignore

# We will monkeypatch core.crawl.can_fetch (the symbol used inside crawl) to simulate robots disallow.


def test_robots_disallow(monkeypatch):
    import core.crawl as crawl_mod  # type: ignore
    monkeypatch.setattr(crawl_mod, "can_fetch", lambda agent, url: False)

    cfg = CrawlConfig(seed="https://example.com/", max_depth=1, max_pages=5)
    stats = {}
    out = list(crawl(cfg, stats=stats))
    assert out == []
    assert stats.get("skipped_robots") >= 1
    assert stats.get("fetched_ok") == 0
