# Deprecations & Cleanup Plan

This document formalizes the previously discussed phased cleanup / deprecation strategy. It balances backward compatibility, user communication, and risk mitigation (avoiding sudden breaks) while simplifying the codebase.

## Goals
1. Reduce duplicate orchestration surfaces (move everyone to `scripts/run_pipeline.py --all`).
2. Clarify which scripts are stable public interfaces vs. internal utilities.
3. Provide a predictable removal timeline so downstream users can adapt.
4. Preserve reproducibility (tagged baseline `v0.1.0`) before removals.

## Scope of Initial Deprecations
| Item | Status | Replacement | Rationale |
|------|--------|-------------|-----------|
| `run_all.py` | Deprecated (soft) | `python scripts/run_pipeline.py --url <seed> --all` | Duplicate orchestration logic; new pipeline flag consolidates features & validation.
| Multiple ad‑hoc analysis scripts producing overlapping metrics (`diagnostics_summary.py`, `check_health.py`, `validate_delivery.py`) | Retained (stable) | N/A (wrapped by collector) | These remain but will be *composed* via `scripts/collect_metrics.py`.
| Future: experimental one-off helpers (if any appear) | To be evaluated | Core pipeline or metrics collector | Reduce surface area for CI & docs.

## Risk Assessment
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| External user still calling `run_all.py` after hard removal | Broken runs | Medium (short-term) | Emit runtime `DeprecationWarning` now; add README & CHANGELOG notices; delay removal until `v0.3.0`.
| Silent divergence between `run_all.py` and `run_pipeline.py` behavior | Inconsistent results / confusion | Low (frozen) | Freeze logic—no new features added to `run_all.py`; point users to replacement.
| Over‑eager deletion harms reproducibility | Loss of historical parity | Low | Create git tag (`v0.1.0`) before removals; keep manifest schema stable.
| Metrics fragmentation continues (users write bespoke parsers) | Duplication + errors | Medium | Introduce `collect_metrics.py` unified JSON aggregator.
| Notebook adds dependencies not installed | Import errors | Medium | Make notebook resilient (try/except for optional libs; document optional install).

## Phases & Timeline
| Phase | Version Window | Actions | Exit Criteria |
|-------|----------------|---------|---------------|
| Phase 0 (Now) | v0.1.x | Mark `run_all.py` deprecated; add docs + warnings; introduce metrics collector; baseline tag `v0.1.0`. | Warning visible; docs published. |
| Phase 1 | v0.2.x | Update CI (optional) to assert no new usage of deprecated entrypoints; encourage migration in README/CHANGELOG. | Zero CI references to deprecated scripts. |
| Phase 2 (Removal) | v0.3.0 | Remove `run_all.py`; archive historical copy under `archives/` (if needed); shorten docs section. | No user complaints for >= 30 days, tag `v0.3.0`. |

## User Communication Checklist
- [x] README notice
- [x] Runtime `DeprecationWarning` emitted
- [x] This `DEPRECATIONS.md` file
- [ ] CHANGELOG entry (added now)
- [ ] Release notes upon tagging

## Policy for Future Deprecations
1. Must provide a documented alternative.
2. Emit `DeprecationWarning` at runtime for *at least* one minor version window.
3. Record in CHANGELOG with first version introduced and targeted removal version.
4. Add unit/CI guard (optional) to ensure no internal code calls deprecated APIs unless explicitly grandfathered.

## Metrics & Observability Additions
`scripts/collect_metrics.py` composes:
* `diagnostics.json` (label distribution, neutrality, confidence bins)
* `health.json` (health status code & reasons)
* `validation.json` (schema/semantic validation state)
* Run summary (subset if available from pipeline stdout or `summary.json`)

Output schema (example):
```json
{
  "workDir": "out/run_20250930_120301",
  "timestamp": "2025-09-30T12:09:33Z",
  "diagnostics": {"count": 87, "label_dist": {"Advantage": 41, "Risk": 29, "Neutral": 17}},
  "health": {"status": 1, "details": {"neutral_ratio": 0.195}},
  "validation": {"status": "pass"},
  "insight_count": 83
}
```

Multiple work directories can be aggregated with `--glob 'out/run_*' --aggregate metrics_timeseries.json` to enable longitudinal tracking.

## Removal Criteria Definition
An item is eligible for deletion when: (a) replacement has been stable for ≥ 1 minor release, (b) no open issues referencing the old path, and (c) a tag prior to removal exists.

---
Questions? Open an issue referencing this document.
