import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from insights.rationale import build_rationale  # type: ignore


def test_rationale_advantage_performance_with_signals():
    r = build_rationale("Advantage","Performance",["performance","throughput"],0.6)
    assert "performance" in r.lower()
    assert "signals:" in r.lower()
    # Should mention advantage
    assert "advantage" in r.lower()


def test_rationale_risk_regulatory():
    r = build_rationale("Risk","Regulatory",["regulatory"],0.8)
    assert "regulatory" in r.lower()
    assert "risk" in r.lower()


def test_rationale_truncation():
    long_signals = [f"signal{i}" for i in range(10)]
    r = build_rationale("Advantage","Traction", long_signals, 0.5)
    assert len(r) <= 180
