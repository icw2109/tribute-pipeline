import sys, pathlib, json, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights import extract_insights


def test_extract_dedupe(tmp_path):
    scraped_path = tmp_path / "scraped.jsonl"
    data = [
        {"url": "https://example.com/restaking/overview", "text": "Restaking allows security extension. Restaking allows security extension."},
        {"url": "https://example.com/tokenomics/info", "text": "Emission is 5% annually. Emission is 5% annually."},
        {"url": "https://example.com/other/page", "text": "World-class innovative pioneering platform."},
    ]
    with scraped_path.open('w', encoding='utf-8') as w:
        for rec in data:
            w.write(json.dumps(rec) + "\n")
    out_path = tmp_path / "insights.jsonl"
    stats = extract_insights(str(scraped_path), str(out_path), target_count=(1,50))
    # Expect at least 2 insights (restaking + emission) and fluff filtered
    assert stats["written"] >= 2
    lines = out_path.read_text(encoding='utf-8').strip().splitlines()
    texts = [json.loads(l)["text"].lower() for l in lines]
    assert any("restaking" in t for t in texts)
    assert any("emission" in t for t in texts)
    # Dedupe ensures no duplicate lines for emission sentence
    restaking_count = sum(1 for t in texts if "restaking allows security extension" in t)
    assert restaking_count == 1
