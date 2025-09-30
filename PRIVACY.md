# Privacy & Data Handling

## Scope
This project processes publicly available website content strictly for deriving non-personal, aggregate business insights.

## Collection
- Only pages within the configured domain scope and up to a depth limit are fetched.
- Robots.txt directives are honored (disallowed paths are skipped).
- Requests are rate-limited (default 1 RPS) to avoid undue load.

## Exclusion & Filtering
- Non-HTML content is skipped.
- Excessively large HTML pages beyond configured size threshold are skipped.
- Boilerplate (navigation, cookie banners) is removed heuristically.

## Personally Identifiable Information (PII)
- Basic scrubbing replaces email addresses and phone-like numeric strings with placeholders: `[REDACTED_EMAIL]`, `[REDACTED_PHONE]` before classification output.
- No attempt is made to store or redistribute raw HTML beyond immediate processing.
- Additional patterns (wallet addresses, national IDs) can be added in `ClassifierPipeline._scrub_pii` if needed.

## Storage & Artifacts
- Output artifacts (`scraped_pages.jsonl`, `insights_raw.jsonl`, `insights_classified.jsonl`) contain only derived textual insight snippets and aggregate metadata.
- `run_manifest.json` includes environment & config metadata, not raw page content.
- No user accounts, authentication tokens, or session data are processed.

## Retention
- Raw HTML is not archived; only cleaned text relevant to insight extraction is kept transiently in memory.
- Derivative JSONL files can be purged at user discretion; no hidden caches are created.

## Compliance & Ethics
- The system is intended for analytical due diligence; do not apply to sites forbidding automated access.
- Users are responsible for ensuring jurisdictional compliance for any downstream data use.

## Reporting
If potentially sensitive content is discovered unexpectedly, remove associated lines and retrain/re-run classification without them.

## Future Hardening (Suggested)
- Add checksum log of redacted patterns to quantify PII removal.
- Expand scrubbing to cover additional sensitive patterns (e.g., physical addresses) if encountered.
