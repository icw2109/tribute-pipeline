Param(
  [string]$OutFile = "synthetic_balanced.jsonl",
  [int]$PerClass = 40,
  [switch]$Strict
)

Write-Host "[1/2] Generating synthetic predictions ($PerClass per class) -> $OutFile" -ForegroundColor Cyan
python scripts/generate_synthetic_predictions.py --out $OutFile --per-class $PerClass
if ($LASTEXITCODE -ne 0) { Write-Host "Generation failed" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "[2/2] Running CI health gate" -ForegroundColor Cyan
if ($Strict) {
  python scripts/ci_health_gate.py --pred $OutFile --strict
} else {
  python scripts/ci_health_gate.py --pred $OutFile
}
if ($LASTEXITCODE -eq 0) {
  Write-Host "Health gate PASSED" -ForegroundColor Green
} else {
  Write-Host "Health gate FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
  exit $LASTEXITCODE
}
