import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig  # type: ignore


def test_unified_classifier_schema():
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False))
    sample_texts = [
        "The protocol suffered a minor slashing event but funds are secure.",
        "Partnership expansion increases market traction and user growth.",
        "General operational update with no significant changes.",
    ]
    for txt in sample_texts:
        rec = pipe.classify_text(txt)
        # Required keys
        for key in ("text", "label", "labelTag", "rationale", "confidence"):
            assert key in rec, f"Missing key {key} in record: {rec}"
        assert rec["text"], "Text field should not be empty"
        assert rec["label"] in {"Risk", "Advantage", "Neutral"}
        assert isinstance(rec["labelTag"], str)
        assert isinstance(rec["rationale"], str) and len(rec["rationale"]) > 0
        assert 0.0 <= rec["confidence"] <= 1.0
        # Basic rationale sanity: should mention label (case-insensitive)
        assert rec["label"].lower() in rec["rationale"].lower()


def test_debug_payload_included_when_enabled():
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False, debug=True))
    rec = pipe.classify_text("Neutral operational insight.")
    assert "debug" in rec, "Debug key missing when debug=True"
    dbg = rec["debug"]
    for k in ("ruleStrength", "signals", "config"):
        assert k in dbg
    assert isinstance(dbg["signals"], list)
