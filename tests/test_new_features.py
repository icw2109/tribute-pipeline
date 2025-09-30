import sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig


def test_rationale_word_cap():
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False))
    # Craft text likely to trigger long rationale via many signals
    text = 'Growth scaling efficiency performance adoption security reliability uptime throughput users customers partners investors'
    rec = pipe.classify_text(text)
    word_count = len(rec['rationale'].split())
    assert word_count <= 26  # 25 + possible ellipsis token


def test_pii_scrub_email_phone():
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False, debug=True))
    rec = pipe.classify_text('Contact us at founder@example.com or +1 212-555-7788 for details 10% growth.')
    assert '[REDACTED_EMAIL]' in rec['text']
    assert '[REDACTED_PHONE]' in rec['text']
    assert rec['debug']['piiScrubbed'] is True


def test_tag_vocabulary_enforcement():
    # We rely on heuristic tag; simulate by using text unlikely to match vocab -> fallback Other
    pipe = ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False))
    rec = pipe.classify_text('Unrelated content with arbitrary jargon foobarization quantum synergy 42%.')
    assert rec['labelTag'] in {'Other'}
