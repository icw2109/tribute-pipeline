# Changelog

All notable changes to this project will be documented here. Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) principles (lightly) and semantic versioning for future releases.

## [Unreleased]
### Planned
- Notebook `notebooks/pipeline_metrics_report.ipynb` (optional, exploratory).
- Reliability calibration & confidence reliability bins.
- Cleanup execution checklist & staged deprecation removals.

## [0.1.2] - 2025-09-30
### Fixed
- Correct publication of console script path fix: previous tag `v0.1.1` contained wheel metadata still at 0.1.0 causing old path logic to ship. This release ensures the module-based stage invocation & CWD auto-workdir logic are present in the packaged artifact.
### Added
- `RELEASING.md` checklist to avoid tag/version mismatch and enforce smoke test before tagging.
### Integrity
- Verified `tribute-e2e` resolves `cli.*` modules (no `src/cli/*.py` paths) and outputs under invocation directory `./out/run_*`.

## [0.1.3] - 2025-09-30
### Fixed
- Hardened pipeline entrypoint to always attempt module (`-m cli.scrape` etc.) first and only then fallback; adds explicit diagnostic banner showing resolution mode & output root so environment issues are immediately visible.
- Clarified error message when both module and legacy path invocations fail, guiding users to verify installed version vs tag.
### Added
- Startup banner prints: package version, source_mode(bool), output_root.
### Internal
- Defensive helper `_invoke` consolidates subprocess logic & doubles logging in failure path.

## [0.1.1] - 2025-09-30
### Fixed
- Installed console script (`tribute-e2e` / `tribute-run`) failed invoking `src/cli/*.py` paths outside a source checkout. Switched all stage invocations to module form (`-m cli.scrape`, `-m cli.extract_insights`, `-m cli.classify`, etc.) with fallback for source tree. Auto workDir now rooted at the invoking CWD (not the site-packages install path) when running from an installed wheel.
### Changed
- Added source vs installed environment detection heuristic and safer sys.path injection only when needed.
### Added
- Output root selection logic + notes in code for future packaging refactors.

## [0.1.0] - 2025-09-30
### Added
- Initial public import: deterministic crawler, insight extraction, classification, health gate, validation, packaging, Docker, dependency audit, manifest versioning.
 - Summary persistence (`summary.json`).
 - Simplified GitHub install instructions.
### Changed
- Consolidated orchestration under `scripts/run_pipeline.py --all`.
### Deprecated
- `run_all.py` (use `scripts/run_pipeline.py --all`).
