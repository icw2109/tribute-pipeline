import json, tempfile, os, sys, subprocess, textwrap, pathlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent

# We assume training CLI and evaluation CLI are available.

SYN_PATH = SCRIPT_DIR / 'synthetic_labeled.jsonl'

SYN_DATA = [
    {"text": "protocol adds validators for security", "label": "Advantage"},
    {"text": "critical exploit risk in contracts", "label": "Risk"},
    {"text": "team publishes neutral operational update", "label": "Neutral"},
    {"text": "throughput increases reduce costs", "label": "Advantage"},
    {"text": "governance attack could occur", "label": "Risk"}
]

# Write synthetic dataset once
if not SYN_PATH.exists():
    with open(SYN_PATH,'w',encoding='utf-8') as f:
        for r in SYN_DATA:
            f.write(json.dumps(r) + '\n')


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_evaluate_cli_tfidf(tmp_path):
    model_dir = tmp_path / 'tfidf_model'
    train_script = ROOT / 'src' / 'cli' / 'train_classifier.py'
    out = _run([sys.executable, str(train_script), '--data', str(SYN_PATH), '--outDir', str(model_dir)])
    assert model_dir.exists()
    eval_script = ROOT / 'src' / 'cli' / 'evaluate.py'
    eval_out = _run([sys.executable, str(eval_script), '--data', str(SYN_PATH), '--modelDir', str(model_dir)])
    data = json.loads(eval_out)
    assert 'primary' in data and 'macro_f1' in data['primary']
    assert data['primary']['primary']['samples'] == len(SYN_DATA) if 'primary' in data['primary'] else True  # backward guard


def test_evaluate_cli_compare(tmp_path):
    model_tfidf = tmp_path / 'tfidf_model'
    model_hash = tmp_path / 'hash_model'
    train_script = ROOT / 'src' / 'cli' / 'train_classifier.py'
    eval_script = ROOT / 'src' / 'cli' / 'evaluate.py'
    _run([sys.executable, str(train_script), '--data', str(SYN_PATH), '--outDir', str(model_tfidf), '--backend', 'tfidf'])
    _run([sys.executable, str(train_script), '--data', str(SYN_PATH), '--outDir', str(model_hash), '--backend', 'hashing', '--hashFeatures', '512'])
    eval_out = _run([sys.executable, str(eval_script), '--data', str(SYN_PATH), '--modelDir', str(model_tfidf), '--compare', str(model_hash)])
    data = json.loads(eval_out)
    assert 'primary' in data and 'compare' in data
    assert data['primary']['backend'] in ('tfidf','legacy_tfidf','hashing')
    assert data['compare']['backend'] in ('tfidf','hashing','legacy_tfidf')
