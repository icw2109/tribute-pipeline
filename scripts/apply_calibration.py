#!/usr/bin/env python
"""Apply calibration parameters to a classified predictions JSONL file.

Supports temperature scaling json or isotonic (not yet implemented storage format—placeholder).

Input:
  --pred predictions JSONL (fields: confidence)
  --calib calibration json produced by calibrate_confidence.py
Output:
  Writes new JSONL with added field 'confidenceCalibrated'.

Usage:
  python scripts/apply_calibration.py --pred out/insights_classified.jsonl \
    --calib out/calibration.json --out out/insights_classified.calibrated.jsonl
"""
import argparse, json, math
from pathlib import Path

def load_jsonl(path: Path):
    rows=[]
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--calib', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()

    calib = json.loads(Path(args.calib).read_text(encoding='utf-8'))
    rows = load_jsonl(Path(args.pred))

    method = calib.get('method')
    if method == 'temperature':
        T = calib.get('T',1.0) or 1.0
        def scale(p: float) -> float:
            eps=1e-6
            p=min(max(p,eps),1-eps)
            logit = math.log(p/(1-p))
            scaled = 1/(1+math.exp(-logit/T))
            return float(round(scaled,6))
    elif method == 'isotonic':
        # Placeholder: assume not supported yet.
        raise SystemExit('Isotonic apply not implemented—extend script when isotonic saved mapping available.')
    else:
        raise SystemExit(f"Unknown calibration method: {method}")

    out_path = Path(args.out)
    with out_path.open('w', encoding='utf-8') as w:
        for r in rows:
            c = r.get('confidence')
            if isinstance(c,(int,float)):
                r['confidenceCalibrated'] = scale(float(c))
            w.write(json.dumps(r, ensure_ascii=False)+'\n')

    print(json.dumps({'written': len(rows), 'method': method, 'out': str(out_path.resolve())}, indent=2))

if __name__=='__main__':
    main()
