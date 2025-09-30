# Changelog

All notable changes to this project will be documented here. Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) principles (lightly) and semantic versioning for future releases.

## [Unreleased]
### Added
- `docs/DEPRECATIONS.md` formalizing cleanup phases & risk assessment.
- `scripts/collect_metrics.py` unified metrics aggregator.
- Deprecation warning emission in `run_all.py`.
- Baseline CHANGELOG file.
 - `tribute-e2e` console script for one-line end-to-end run.
 - CI workflow (`.github/workflows/ci.yml`) installing package + smoke running.

### Planned
- CI workflow (tests + health + validation).
- Tag baseline release (`v0.1.0`).
- Notebook `notebooks/pipeline_metrics_report.ipynb` (optional, exploratory).

## [0.1.0] - 2025-09-30
### Added
- Initial public import: deterministic crawler, insight extraction, classification, health gate, validation, packaging, Docker, dependency audit, manifest versioning.
 - Summary persistence (`summary.json`).
 - Simplified GitHub install instructions.
### Changed
- Consolidated orchestration under `scripts/run_pipeline.py --all`.
### Deprecated
- `run_all.py` (use `scripts/run_pipeline.py --all`).
