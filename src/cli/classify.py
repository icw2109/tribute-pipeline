from __future__ import annotations
"""Unified classification CLI.

Emits JSONL records with fields:
    text, label, labelTag, rationale, confidence
Optionally includes debug fields when pipeline config debug=True.

Supports an optional JSON config file whose keys map onto PipelineConfig
dataclass fields; CLI flags override config file values.
"""
import argparse, json, sys
from pathlib import Path
from datetime import datetime
import platform, hashlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig


def iter_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        raise SystemExit(f"Failed to load config {path}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True, help='Input enriched insights JSONL')
    ap.add_argument('--out', dest='out', required=True, help='Output classified JSONL')
    ap.add_argument('--model', dest='model', help='Path to self-train model directory (if using self-train)')
    ap.add_argument('--config', dest='config', help='Optional JSON config file for pipeline settings')
    ap.add_argument('--enable-self-train', action='store_true')
    ap.add_argument('--enable-zero-shot', action='store_true')
    ap.add_argument('--zero-shot-primary', action='store_true', help='Run zero-shot NLI as primary model before heuristic override logic')
    ap.add_argument('--strong', type=float, default=None, help='Strong heuristic threshold override')
    ap.add_argument('--model-floor', type=float, default=None, help='Model floor probability for zero-shot fallback')
    ap.add_argument('--zero-shot-model', default=None, help='Zero-shot model name')
    ap.add_argument('--risk-override-threshold', type=float, default=None, help='Threshold for heuristic risk override (default 0.55)')
    ap.add_argument('--enable-margin-gating', action='store_true', help='Enable margin gating for zero-shot primary locking')
    ap.add_argument('--margin-threshold', type=float, default=None, help='Margin threshold for NLI locking (default 0.15)')
    ap.add_argument('--enable-conflict-dampener', action='store_true', help='Reduce confidence when sources disagree with low margin')
    ap.add_argument('--conflict-dampener', type=float, default=None, help='Confidence subtraction amount (default 0.05)')
    ap.add_argument('--enable-provisional-risk', action='store_true', help='Add provisionalLabel=Risk in strong risk heuristic cases downgraded to Neutral')
    ap.add_argument('--debug', action='store_true')
    args = ap.parse_args()

    base_cfg = {}
    if args.config:
        base_cfg = load_config(Path(args.config))
    if args.enable_self_train:
        base_cfg['enable_self_train'] = True
    if args.enable_zero_shot:
        base_cfg['enable_zero_shot'] = True
    if args.strong is not None:
        base_cfg['strong_rule_threshold'] = args.strong
    if args.model_floor is not None:
        base_cfg['model_floor'] = args.model_floor
    if args.zero_shot_model is not None:
        base_cfg['zero_shot_model'] = args.zero_shot_model
    if args.zero_shot_primary:
        base_cfg['zero_shot_primary'] = True
    if args.risk_override_threshold is not None:
        base_cfg['risk_override_threshold'] = args.risk_override_threshold
    if args.enable_margin_gating:
        base_cfg['enable_margin_gating'] = True
    if args.margin_threshold is not None:
        base_cfg['margin_threshold'] = args.margin_threshold
    if args.enable_conflict_dampener:
        base_cfg['enable_conflict_dampener'] = True
    if args.conflict_dampener is not None:
        base_cfg['conflict_dampener'] = args.conflict_dampener
    if args.enable_provisional_risk:
        base_cfg['enable_provisional_risk'] = True
    if args.debug:
        base_cfg['debug'] = True

    # Filter only valid PipelineConfig fields
    valid_fields = set(PipelineConfig.__dataclass_fields__.keys())
    cfg_kwargs = {k: v for k, v in base_cfg.items() if k in valid_fields}
    cfg = PipelineConfig(**cfg_kwargs)
    pipe = ClassifierPipeline(cfg, self_train_model_path=args.model)

    count = 0
    first_pipeline_record_meta = None
    with open(args.out, 'w', encoding='utf-8') as w:
        for rec in iter_jsonl(args.inp):
            text = rec.get('text')
            if not text:
                continue
            out_rec = pipe.classify_text(text)
            if first_pipeline_record_meta is None:
                first_pipeline_record_meta = {
                    'schemaVersion': out_rec.get('schemaVersion'),
                    'taxonomyVersion': out_rec.get('taxonomyVersion'),
                    'tagVocabularyVersion': out_rec.get('tagVocabularyVersion')
                }
            w.write(json.dumps(out_rec, ensure_ascii=False) + '\n')
            count += 1
    manifest = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'records': count,
        'output': str(Path(args.out).resolve()),
        'config': cfg.__dict__,
        'schemaVersion': first_pipeline_record_meta.get('schemaVersion') if first_pipeline_record_meta else None,
        'taxonomyVersion': first_pipeline_record_meta.get('taxonomyVersion') if first_pipeline_record_meta else None,
    'tagVocabularyVersion': first_pipeline_record_meta.get('tagVocabularyVersion') if first_pipeline_record_meta else None,
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'command': ' '.join(sys.argv),
    }
    # Quick integrity hash of output file content size + first 1KB
    try:
        p = Path(args.out)
        data_head = p.read_bytes()[:1024]
        manifest['outputSizeBytes'] = p.stat().st_size
        manifest['outputHeadHash'] = hashlib.sha256(data_head).hexdigest()
    except Exception:
        pass
    manifest_path = Path(args.out).with_name('run_manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'processed': count, 'out': args.out, 'manifest': str(manifest_path)}))


if __name__ == '__main__':  # pragma: no cover
    main()
