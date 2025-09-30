from __future__ import annotations
"""End-to-end pipeline orchestration.

Steps:
 1. (Optional) Train model if --modelDir does not already contain model.joblib
 2. Classify test set (hybrid or ml) using saved model
 3. Generate metrics markdown + examples via generate_reports
 4. (Optional) Run benchmark classification for latency stats and feed into report

Example:
  python src/cli/pipeline_e2e.py \
    --train data/splits/train.jsonl --dev data/splits/dev.jsonl --test data/splits/test.jsonl \
    --modelDir models/distilbert_exp1 --backend distilbert --calibrate \
    --mode hybrid --reportsDir reports/exp1 --benchmark

Assumes labeled JSONL for splits with fields text,label.
"""
import argparse, json, subprocess, sys, os, shutil
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import LABELS  # noqa


def build_parser():
    p = argparse.ArgumentParser(description='End-to-end pipeline runner (train -> classify -> report).')
    p.add_argument('--train', required=True, help='Train split JSONL')
    p.add_argument('--dev', required=True, help='Dev split JSONL')
    p.add_argument('--test', required=True, help='Test split JSONL')
    p.add_argument('--modelDir', required=True, help='Directory for model artifacts')
    p.add_argument('--backend', choices=['tfidf','hashing','distilbert'], default='tfidf')
    p.add_argument('--calibrate', action='store_true')
    p.add_argument('--mode', choices=['heuristic','ml','hybrid'], default='hybrid', help='Classification mode for final run')
    p.add_argument('--reportsDir', required=True, help='Directory to write markdown reports')
    p.add_argument('--benchmark', action='store_true', help='Also run benchmark_classify for latency stats')
    p.add_argument('--hybridRiskThreshold', type=float, default=0.65)
    p.add_argument('--hybridAdvThreshold', type=float, default=0.60)
    # DistilBERT params
    p.add_argument('--hfModel', default='distilbert-base-uncased')
    p.add_argument('--maxSeqLen', type=int, default=256)
    p.add_argument('--embedBatchSize', type=int, default=16)
    p.add_argument('--pooling', choices=['cls','mean'], default='cls')
    p.add_argument('--noDense', action='store_true')
    p.add_argument('--maxFeatures', type=int, default=20000)
    p.add_argument('--hashFeatures', type=int, default=2**18)
    p.add_argument('--costPerSecond', type=float, default=0.0004)
    return p


def run_cmd(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f'Command failed: {cmd}\nSTDERR:\n{proc.stderr}')
    return proc.stdout.strip()


def ensure_model(args):
    model_path = Path(args.modelDir) / 'model.joblib'
    if model_path.exists():
        return 'existing'
    cmd = [sys.executable, 'src/cli/train_classifier.py',
           '--trainFile', args.train, '--devFile', args.dev, '--testFile', args.test,
           '--backend', args.backend, '--outDir', args.modelDir]
    if args.calibrate:
        cmd.append('--calibrate')
    if args.backend == 'distilbert':
        cmd += ['--hfModel', args.hfModel, '--maxSeqLen', str(args.maxSeqLen), '--embedBatchSize', str(args.embedBatchSize), '--pooling', args.pooling]
        if args.noDense:
            cmd.append('--noDense')
    elif args.backend == 'tfidf':
        cmd += ['--maxFeatures', str(args.maxFeatures)]
    elif args.backend == 'hashing':
        cmd += ['--hashFeatures', str(args.hashFeatures)]
    out = run_cmd(cmd)
    return out


def classify_test(args, classified_path: Path):
    cmd = [sys.executable, 'src/cli/classify.py', '--in', args.test, '--out', str(classified_path), '--mode', args.mode, '--modelDir', args.modelDir, '--eval', '--truth', args.test, '--metrics', '--hybridRiskThreshold', str(args.hybridRiskThreshold), '--hybridAdvThreshold', str(args.hybridAdvThreshold)]
    out = run_cmd(cmd)
    return out


def benchmark(args, benchmark_path: Path):
    cmd = [sys.executable, 'src/cli/benchmark_classify.py', '--inputs', args.test, '--modelDir', args.modelDir, '--truth', args.test, '--repeats', '2']
    out = run_cmd(cmd)
    benchmark_path.write_text(out, encoding='utf-8')
    return out


def generate_reports(args, classified_path: Path, benchmark_path: Path|None):
    cmd = [sys.executable, 'src/cli/generate_reports.py', '--predictions', str(classified_path), '--truth', args.test, '--outDir', args.reportsDir, '--costPerSecond', str(args.costPerSecond)]
    if benchmark_path and benchmark_path.exists():
        cmd += ['--benchmark', str(benchmark_path)]
    out = run_cmd(cmd)
    return out


def main(argv=None):
    args = build_parser().parse_args(argv)
    Path(args.reportsDir).mkdir(parents=True, exist_ok=True)
    model_status = ensure_model(args)
    classified_path = Path(args.reportsDir) / 'test_classified.jsonl'
    classify_out = classify_test(args, classified_path)
    benchmark_path = None
    if args.benchmark:
        benchmark_path = Path(args.reportsDir) / 'benchmark.json'
        benchmark(args, benchmark_path)
    report_out = generate_reports(args, classified_path, benchmark_path)
    summary = {
        'model': args.modelDir,
        'model_status': model_status,
        'classified': str(classified_path),
        'reportsDir': args.reportsDir,
        'mode': args.mode
    }
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
