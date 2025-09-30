"""Generate a balanced synthetic predictions JSONL file for health gate demonstration.

This script fabricates classification-like records with fields matching the
expected schema subset consumed by diagnostics & health scripts:
  - text
  - label (Advantage/Risk/Neutral)
  - labelTag
  - rationale
  - confidence

Class distribution is balanced unless overridden.

Example:
  python scripts/generate_synthetic_predictions.py --out synthetic_balanced.jsonl --per-class 40
  python scripts/ci_health_gate.py --pred synthetic_balanced.jsonl --strict

NOTE: These are synthetic placeholders not derived from model output.
"""
from __future__ import annotations
import argparse, json, random, time
from pathlib import Path

TAGS_ADV = ["Growth", "Ecosystem", "Adoption", "Token Utility"]
TAGS_RISK = ["Security Risk", "Governance Risk", "Economic Risk", "Operational Risk"]
TAGS_NEUT = ["General", "Background", "Neutral Observation"]

EXAMPLE_TEXT = {
    'Advantage': [
        'Protocol shows accelerating validator set expansion.',
        'Growing integration across partner ecosystems.',
        'Fee capture model incentivizes long-term participation.',
        'Strong developer tooling lowers onboarding friction.'
    ],
    'Risk': [
        'Slashing penalties may deter smaller operators.',
        'Governance centralization remains unresolved.',
        'Economic incentives could weaken under low volume.',
        'Operational complexity introduces upgrade risk.'
    ],
    'Neutral': [
        'Protocol launched mainnet phase two this quarter.',
        'Documentation updated with new module specs.',
        'Community call scheduled for next month.',
        'Audit report published and under review.'
    ]
}

RATIONALE_TEMPLATE = {
    'Advantage': 'Advantage due to positive growth/adoption signals.',
    'Risk': 'Risk indicated by governance/economic/security concerns.',
    'Neutral': 'Neutral factual statement without directional signal.'
}

def build_record(label: str, idx: int) -> dict:
    if label == 'Advantage':
        tag = random.choice(TAGS_ADV)
    elif label == 'Risk':
        tag = random.choice(TAGS_RISK)
    else:
        tag = random.choice(TAGS_NEUT)
    text = random.choice(EXAMPLE_TEXT[label])
    base_conf = 0.85 if label != 'Neutral' else 0.75
    jitter = random.uniform(-0.08, 0.08)
    confidence = max(0.05, min(0.99, base_conf + jitter))
    return {
        'text': text,
        'label': label,
        'labelTag': tag,
        'rationale': RATIONALE_TEMPLATE[label],
        'confidence': round(confidence, 3),
        'schemaVersion': '1.0',
        'taxonomyVersion': 'v1.0-draft',
        'synthetic': True,
        'id': f'synth-{label.lower()}-{idx}'
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='Generate synthetic balanced predictions JSONL.')
    ap.add_argument('--out', required=True, help='Output JSONL path')
    ap.add_argument('--per-class', type=int, default=30, help='Records per class')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args(argv)
    random.seed(args.seed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    labels = ['Advantage', 'Risk', 'Neutral']
    with out_path.open('w', encoding='utf-8') as f:
        for label in labels:
            for i in range(args.per_class):
                rec = build_record(label, i)
                f.write(json.dumps(rec) + '\n')

    summary = {
        'out': str(out_path.resolve()),
        'per_class': args.per_class,
        'total': args.per_class * len(labels),
        'labels': labels,
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':  # pragma: no cover
    main()
