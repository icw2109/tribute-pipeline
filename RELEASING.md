## Releasing

Step-by-step to cut a reproducible release without tag/version drift.

1. Update Version:
   - Edit `pyproject.toml` `version = "X.Y.Z"`.
   - Update `CHANGELOG.md` with new section `[X.Y.Z] - YYYY-MM-DD` summarizing Added / Changed / Fixed / Deprecated.
2. Commit:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release X.Y.Z: <short summary>"
   ```
3. Smoke Test From Commit (before tagging):
   ```bash
   python -m venv _reltest && source _reltest/bin/activate  # Windows: _reltest\Scripts\Activate
   pip install "tribute-pipeline @ git+https://github.com/<owner>/tribute-pipeline.git@<commit_sha>"
   tribute-e2e --url https://example.org --maxPages 3 --maxDepth 1
   ```
   Ensure: outputs appear under CWD `out/run_*`; no `[scrape] FAILED CMD src/cli/...` errors.
4. Tag:
   ```bash
   git tag vX.Y.Z
   git push origin main
   git push origin vX.Y.Z
   ```
5. Post-Tag Verification:
   Fresh venv install using the tag. Confirm wheel shows `tribute_pipeline-X.Y.Z`.
6. (Optional) Announce / Update README quick install snippet.
7. If a mistake occurs (wrong code in tag): bump to new patch version; do not retcon existing public tag.

Checklist (tick before tagging):
- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG updated
- [ ] Commit pushed
- [ ] Smoke test from commit hash passes
- [ ] Tag created & pushed
- [ ] Fresh tag install shows correct version
