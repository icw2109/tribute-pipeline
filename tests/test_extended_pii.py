import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig

def test_extended_pii_patterns():
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False, debug=True))
    text = 'Contact 0x1234567890abcdef1234567890abcdef12345678 at admin@example.com or +1 650-555-7788; server 192.168.0.1 wallet 1BoatSLRHtKNngkdXEeobR76b53LETtpyT.'
    rec = pipe.classify_text(text)
    redacted = rec['text']
    assert '[REDACTED_WALLET]' in redacted
    assert '[REDACTED_EMAIL]' in redacted
    assert '[REDACTED_PHONE]' in redacted
    assert '[REDACTED_IP]' in redacted
    assert rec['debug']['piiScrubbed'] is True
