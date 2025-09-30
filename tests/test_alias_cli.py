import json, subprocess, sys, tempfile, pathlib

PYTHON = sys.executable
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'

def run(cmd):
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(cmd)}\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
    return proc

def test_classify_alias_minimal(tmp_path):
    # Prepare minimal insights_raw.jsonl
    raw = tmp_path / 'insights_raw.jsonl'
    recs = [
        {"sourceUrl":"https://example.com/a","section":"a","text":"Security audit completed with no critical issues.","evidence":["Security audit completed"]},
        {"sourceUrl":"https://example.com/b","section":"b","text":"Token supply unlock schedule introduces dilution risk.","evidence":["unlock schedule dilution risk"]},
        {"sourceUrl":"https://example.com/c","section":"c","text":"Company maintains documentation portal.","evidence":["documentation portal"]},
    ]
    with raw.open('w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
    out_path = tmp_path / 'classified.jsonl'
    cmd = [PYTHON, str(SCRIPTS / 'classify'), '--in', str(raw), '--out', str(out_path)]
    run(cmd)
    lines = out_path.read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert 'label' in first and 'confidence' in first and 'labelTag' in first
