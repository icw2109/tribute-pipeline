import json, tempfile, pathlib, sys
from typing import List, Dict

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from core.crawl import crawl, PageRecord  # type: ignore
from core.config import CrawlConfig  # type: ignore
import core.crawl as crawl_mod  # type: ignore
from core.insight_extract import extract_insights  # type: ignore
from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig  # type: ignore


def fake_fetch_sequence(pages: Dict[str, str]):
    """Return a fetch_func that serves simple HTML documents from an in-memory map.
    Keys are URLs, values are body inner text (we'll wrap in minimal HTML).
    Missing URL returns 404-like object.
    """
    class Resp:
        def __init__(self, url: str, text: str, status: int = 200):
            self.url = url
            self.text = text
            self.status_code = status
            self.headers = {'Content-Type': 'text/html; charset=utf-8'} if status == 200 else {}

    def _fetch(session, url, timeout=10, allow_redirects=True):  # noqa: ARG001
        if url in pages:
            body = f"<html><head><title>{pages[url].split()[0][:30]}</title></head><body><main>{pages[url]}</main></body></html>"
            return Resp(url, body)
        return Resp(url, '', 404)
    return _fetch


def test_scrape_output_schema(monkeypatch):
    # Bypass network robots logic for deterministic unit test by patching the symbol used inside crawl
    monkeypatch.setattr(crawl_mod, 'can_fetch', lambda ua, url, fallback_allow=False: True)
    # Use a pseudo domain unlikely to resolve network fetches; rely on robots fallback allow
    seed = 'https://example.test/'  # include trailing slash so canonical_url matches fake fetch keys
    pages = {
        seed: 'Security audit completed with no critical issues. <a href="/roadmap">roadmap</a> Growing validator set indicates adoption.',
        'https://example.test/roadmap': 'Project maintains a public roadmap. Token unlock schedule may dilute holders.'
    }
    cfg = CrawlConfig(seed=seed, max_depth=1, max_pages=5, rps=10.0, per_page_cap=10, robots_fallback_allow=True)
    recs = list(crawl(cfg, fetch_func=fake_fetch_sequence(pages)))
    assert len(recs) <= 5 and len(recs) >= 1
    for r in recs:
        # Required fields
        assert set(r.keys()) == {'url','title','text','depth','discoveredFrom'}
        assert r['url'].startswith('https://')
        assert isinstance(r['title'], str)
        assert isinstance(r['text'], str) and len(r['text']) > 0
        assert isinstance(r['depth'], int) and r['depth'] >= 0
        # discoveredFrom may be None for seed; else a URL
        if r['discoveredFrom'] is not None:
            assert isinstance(r['discoveredFrom'], str) and r['discoveredFrom'].startswith('https://')
        assert r['depth'] <= cfg.max_depth


def test_extract_output_schema(tmp_path: pathlib.Path):
    # Create a minimal scraped_pages.jsonl file
    scraped = tmp_path / 'scraped_pages.jsonl'
    records = [
        {"url":"https://example.com","title":"Example","text":"Security audit completed with no critical issues. Token unlock schedule may dilute holders.","depth":0,"discoveredFrom":None}
    ]
    scraped.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
    out_raw = tmp_path / 'insights_raw.jsonl'
    stats = extract_insights(str(scraped), str(out_raw), target_count=(1,50))
    assert out_raw.exists()
    lines = [l for l in out_raw.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert len(lines) >= 1
    for ln in lines:
        obj = json.loads(ln)
        for field in ('sourceUrl','section','text','evidence','candidateType','qualityScore','provenance'):
            assert field in obj
        assert isinstance(obj['sourceUrl'], str) and obj['sourceUrl'].startswith('https://')
        assert isinstance(obj['section'], str) and len(obj['section']) > 0
        assert isinstance(obj['text'], str) and 5 <= len(obj['text']) <= 300
        assert isinstance(obj['evidence'], list) and len(obj['evidence']) >= 1
        assert 0.0 <= float(obj['qualityScore']) <= 1.0
        assert obj['provenance'] == 'scraped'


def test_classify_output_schema(tmp_path: pathlib.Path):
    # Prepare minimal raw insights file
    raw = tmp_path / 'insights_raw.jsonl'
    raw_recs = [
        {"sourceUrl":"https://example.com","section":"root","text":"Security audit completed with no critical issues.","evidence":["Security audit completed"],"candidateType":"security","qualityScore":0.9,"provenance":"scraped"},
        {"sourceUrl":"https://example.com","section":"root","text":"Token unlock schedule may dilute holders.","evidence":["Token unlock schedule"],"candidateType":"tokenomics","qualityScore":0.8,"provenance":"scraped"},
        {"sourceUrl":"https://example.com","section":"root","text":"Project maintains a public roadmap.","evidence":["public roadmap"],"candidateType":"roadmap","qualityScore":0.7,"provenance":"scraped"},
    ]
    raw.write_text('\n'.join(json.dumps(r) for r in raw_recs) + '\n', encoding='utf-8')
    cfg = PipelineConfig(enable_zero_shot=False, enable_self_train=False)
    pipe = ClassifierPipeline(cfg)
    out_lines=[]
    for r in raw_recs:
        out_lines.append(pipe.classify_text(r['text']))
    assert len(out_lines) == len(raw_recs)
    allowed_labels = {'Advantage','Risk','Neutral'}
    for rec in out_lines:
        # Core required fields
        for f in ('text','label','labelTag','rationale','confidence'):
            assert f in rec
        assert rec['label'] in allowed_labels
        assert isinstance(rec['labelTag'], str) and rec['labelTag'].strip() != ''
        assert isinstance(rec['rationale'], str) and 0 < len(rec['rationale']) <= 300
        assert 0.0 <= float(rec['confidence']) <= 1.0
        # Optional metadata fields
        if 'schemaVersion' in rec:
            assert isinstance(rec['schemaVersion'], str)
        if 'taxonomyVersion' in rec:
            assert isinstance(rec['taxonomyVersion'], str)
        if 'tagVocabularyVersion' in rec:
            assert isinstance(rec['tagVocabularyVersion'], str)
