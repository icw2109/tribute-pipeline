from insights.pipeline import extract_insights
import json, tempfile, os

def write_scraped(lines):
    fd, path = tempfile.mkstemp(text=True)
    with os.fdopen(fd,'w', encoding='utf-8') as f:
        for i, txt in enumerate(lines):
            obj = {"url": f"u{i}", "title": "t", "text": txt, "depth": 0, "discoveredFrom": None}
            f.write(json.dumps(obj) + "\n")
    return path

def test_confidence_risk_higher_than_neutral(tmp_path):
    scraped = write_scraped([
        "Security risk of exploit increased 20% in 2024.",
        "Routine meeting minutes for committee agenda.",
    ])
    out = tmp_path / 'out.jsonl'
    stats = extract_insights(scraped, str(out), target_count=(1,10), do_classify=True, do_metrics=True)
    # Load outputs
    recs = [json.loads(l) for l in out.open()]  # order preserved
    assert len(recs) >= 2
    risk_conf = next(r['confidence'] for r in recs if r.get('category')=='Risk')
    neutral_conf = next(r['confidence'] for r in recs if r.get('category')=='Neutral')
    assert risk_conf > neutral_conf

