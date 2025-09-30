from __future__ import annotations
"""Ensemble routing logic for multi-tier classification.

Order:
 1. Heuristic rules (fast, deterministic)
 2. Self-trained pseudo model (if loaded and ruleStrength < rule_strong threshold)
 3. Zero-shot NLI fallback (if enabled and model confidence < model_floor OR label Neutral with low rule strength)

Returns a unified record with provenance fields.
"""
from typing import Optional, Dict, Any
from .heuristic import heuristic_classify
from .self_train_infer import SelfTrainModel
from .zero_shot import zero_shot_classify
from .rationale import build_rationale

class EnsembleClassifier:
    def __init__(self, self_train_model_path: Optional[str] = None, config: Optional[dict] = None):
        self.model = SelfTrainModel(self_train_model_path) if self_train_model_path else None
        self.cfg = config or {}
        # Defaults
        self.rule_strong = self.cfg.get('ruleStrongThreshold', 0.75)
        self.model_floor = self.cfg.get('modelFloor', 0.55)
        self.enable_zero_shot = self.cfg.get('enableZeroShot', False)
        self.zero_shot_model = self.cfg.get('zeroShotModel', 'facebook/bart-large-mnli')

    def classify(self, text: str, debug: bool=False, explain_top_k: int=5) -> Dict[str, Any]:
        heur = heuristic_classify(text)
        provenance = ['heuristic']
        final = heur['label']
        tag = heur['tag']
        model_probs = None
        model_label = None
        nli = None

        # If heuristic very strong, accept
        if heur['ruleStrength'] >= self.rule_strong or self.model is None:
            final_conf = heur['ruleStrength']
            rationale = build_rationale(
                label=final,
                tag=tag,
                signals=heur['signals'],
                rule_strength=heur['ruleStrength'],
                model_prob=None,
                nli_supported=False,
                limit=180,
            )
            return {
                'label': final,
                'labelTag': tag,
                'tag': tag,  # legacy key retained
                'strategy': 'heuristic',
                'ruleStrength': heur['ruleStrength'],
                'signals': heur['signals'],
                'modelProbs': model_probs,
                'nli': nli,
                'finalConfidence': round(final_conf,3),
                'confidence': round(final_conf,3),
                'rationale': rationale,
                'topFeatures': None,
                'provenance': provenance
            }

        # Self-train model stage
        pred = self.model.predict([text])[0]
        model_probs = pred['probs']
        model_label = pred['label']
        provenance.append('self-train')
        final = model_label  # override if heuristic weak
        top_features = None
        if debug:
            try:
                top_features = self.model.explain_top_features(text, top_k=explain_top_k)
            except Exception:
                top_features = None

        top_prob = max(model_probs.values()) if model_probs else 0.0
        # fallback condition: uncertain OR neutral & low rule strength
        need_nli = self.enable_zero_shot and (top_prob < self.model_floor or (final == 'Neutral' and heur['ruleStrength'] < 0.4))
        if need_nli:
            nli = zero_shot_classify(text, self.zero_shot_model)
            provenance.append('zero-shot')
            final = nli['label']

        # Neutral backstop: if still Risk or Advantage with very low model confidence and weak rules, reconsider
        if final != 'Neutral' and heur['ruleStrength'] < 0.3 and model_probs:
            top_prob = max(model_probs.values())
            if top_prob < 0.5 and not any(sig in ('slashing','exploit','attack') for sig in heur['signals']):
                final = 'Neutral'
                provenance.append('neutral-backstop')

        # Confidence aggregation
        top_prob = max(model_probs.values()) if model_probs else 0.0
        final_conf = max(heur['ruleStrength'], top_prob)
        if nli and nli.get('available') and nli.get('label') == final:
            nli_score = nli['scores'].get(final, 0)
            # bounded boost
            boost = min(0.1, max(0.0, nli_score - final_conf))
            final_conf = min(1.0, final_conf + boost)

        rationale = build_rationale(
            label=final,
            tag=tag,
            signals=heur['signals'],
            rule_strength=heur['ruleStrength'],
            model_prob=top_prob,
            nli_supported=bool(nli and nli.get('available') and nli.get('label') == final),
            limit=180,
        )
        return {
            'label': final,
            'labelTag': tag,
            'tag': tag,  # legacy compatibility
            'strategy': 'ensemble',
            'ruleStrength': heur['ruleStrength'],
            'signals': heur['signals'],
            'modelProbs': model_probs,
            'nli': nli,
            'finalConfidence': round(final_conf,3),
            'confidence': round(final_conf,3),
            'rationale': rationale,
            'topFeatures': top_features,
            'provenance': provenance
        }

__all__ = ["EnsembleClassifier"]
