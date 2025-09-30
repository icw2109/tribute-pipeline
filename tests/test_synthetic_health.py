import json, subprocess, sys, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


def run(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def test_synthetic_balanced_health_pass(tmp_path):
    synth_path = tmp_path / 'synthetic_balanced.jsonl'
    # Generate 10 per class for speed
    run([sys.executable, str(SCRIPTS / 'generate_synthetic_predictions.py'), '--out', str(synth_path), '--per-class', '10'])
    # Health gate (non-strict invocation should still pass; we use ci_health_gate to ensure tests context OK)
    out = run([sys.executable, str(SCRIPTS / 'ci_health_gate.py'), '--pred', str(synth_path)])
    # Expect JSON output containing status 0
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except json.JSONDecodeError:
        raise AssertionError(f"Did not receive JSON output. Raw out:\n{out}")
    assert data.get('health', {}).get('status', 1) == 0, f"Health status not 0: {data}"