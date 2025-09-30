# Labeling Guidelines (v1.0 Draft)

These guidelines govern human annotation of insight sentences.

## Classes

1. Advantage  
   Positive benefit, differentiator, or efficiency gain.  
   Examples:  
   - "Restaking enables reuse of staked capital across services."  
   - "Design reduces fragmentation for operators."  
   Exclude: Roadmap promises, speculative hype.

2. Risk  
   Potential or realized negative outcome (loss, penalty, exploit, uncertainty).  
   Examples:  
   - "Operators face slashing if commitments are missed."  
   - "Economic security can be diluted by excessive rehypothecation."  
   Priority: Risk overrides Advantage if both equally central.

3. Neutral  
   Descriptive factual statements without clear positive or negative framing.  
   Examples:  
   - "EigenLayer allows operators to register services."  
   - "The module requires a minimum stake."  
   Exclude: Generic marketing fluff without factual claim (discard instead of labeling).

## Decision Rules

- Mechanism + Benefit? If explanatory semantics dominate → Neutral; otherwise → Advantage.
- Mechanism + Downside? If a concrete negative conditional or penalty appears → Risk.
- Numbers alone with no contextual claim → Discard or merge with adjacent sentence.
- Multi-Claim Sentences: If two separable claims, manually split before labeling.

## Multi-Sentence Merges

If extraction merged two short sentences into one candidate:
- Keep if they jointly form one atomic idea (claim + qualifier).
- Otherwise manually split and label individually (update the dataset accordingly).

## Edge Cases

| Case | Guidance |
|------|----------|
| Roadmap timeline + feature | Prefer Neutral unless explicit benefit stated | 
| Token emission benefit claim | Advantage unless warning attached, then Risk | 
| Security audit mention only | Neutral (unless boasting security superiority → Advantage) |
| Slashing described as deterrent | Risk |
| Comparative statement ("more scalable") | Advantage (require comparative anchor or mechanism) |

## Fields Required Per Labeled Row

```
{
  "id": <int>,
  "text": "...",
  "label": "Advantage|Risk|Neutral",
  "sourceUrl": "https://...",
  "candidateType": "metric|risk|roadmap|adoption|tokenomics|security|other",
  "qualityScore": <float>,
  "provenance": "scraped",   // must remain 'scraped' for real data
  "sample_phase": "seed|uncertainty|diversity|heuristic",
  "annotator": "<initials>",
  "taxonomyVersion": "v1.0-draft",
  "rationale_gold": "(optional one-line why label chosen)",
  "notes": "(optional)"
}
```

## Annotation Process

1. Open `data/seed_batch.v1.jsonl` in an editor supporting JSONL.
2. For each row add `label`, `annotator`, and optionally `rationale_gold`.
3. Skip rows you believe are non-insights; mark with `label` = "Neutral" only if descriptive; otherwise remove from the file (track removed count).
4. Save incremental progress frequently.
5. When done: run stratified split script to generate train/dev/test (dev/test small at seed stage is fine).

## Quality Control

- Spot review 10 random labels after each batch.
- Maintain a changelog if a guideline reinterpretation occurs; do NOT retroactively change previously frozen test labels without version bump.

## Versioning

- Current taxonomy version: `v1.0-draft` (update to `v1.0` after first 200 example freeze).
- If definitions change materially, increment minor version (v1.1) and record diffs in a CHANGELOG section.

## Rejection Reasons (If Removing a Row)
- Duplicate wording of earlier labeled row.
- Pure navigation/UI text.
- Marketing slogan with no technical / economic claim.
- Fragment missing necessary context to understand claim.

## Post-Seed Next Steps

- Train initial model with metadata + calibration.
- Run uncertainty sampling to assemble next batch.
- Iterate until each class ≥ ~40 examples or performance plateaus.

---

Questions or ambiguous cases should be logged in `ANNOTATION_NOTES.md` (create if absent) for resolution before next batch.
