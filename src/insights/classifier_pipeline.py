from __future__ import annotations
"""Unified classifier pipeline orchestrating heuristic, self-train, embeddings, and zero-shot.

Usage pattern:
    from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig
    cfg = PipelineConfig(enable_self_train=True, enable_zero_shot=False)
    pipe = ClassifierPipeline(cfg, self_train_model_path='models/selftrain_embed')
    result = pipe.classify_text("Some insight text ...")

Output schema (dict):
  {
    'text': str,
    'label': 'Risk|Advantage|Neutral',
    'labelTag': str,
    'rationale': str,
    'confidence': float,
    'debug': {...}  # only if debug enabled
  }

Goals:
  * Centralize fusion logic
  * Provide consistent rationale across minimal and advanced modes
  * Hide internal complexity behind a light config dataclass
"""
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import json, os, functools, re

from .heuristic import heuristic_classify
from .rationale import build_rationale

try:  # optional self-train
    from .self_train_infer import SelfTrainModel
except Exception:  # pragma: no cover
    SelfTrainModel = None  # type: ignore

try:  # optional zero-shot
    from .zero_shot import zero_shot_classify
except Exception:  # pragma: no cover
    def zero_shot_classify(text: str, model_name: str = "facebook/bart-large-mnli"):
        return {"label": "Neutral", "available": False, "scores": {"Risk": 0.33, "Advantage": 0.33, "Neutral": 0.34}}


@dataclass
class PipelineConfig:
    strong_rule_threshold: float = 0.75
    model_floor: float = 0.55
    enable_self_train: bool = True
    enable_zero_shot: bool = False
    zero_shot_model: str = "facebook/bart-large-mnli"
    zero_shot_primary: bool = False  # If True, run zero-shot first and use heuristic only for signals/tag & risk override
    risk_override_threshold: float = 0.55  # threshold for promoting Risk if heuristic strong but NLI disagrees
    enable_margin_gating: bool = False     # lock in NLI label if margin >= margin_threshold
    margin_threshold: float = 0.15         # NLI top1 - top2 score needed to lock label
    enable_conflict_dampener: bool = False # reduce confidence when sources disagree with low margin
    conflict_dampener: float = 0.05        # amount to subtract from confidence in conflict cases
    enable_provisional_risk: bool = False  # add provisional Risk label similar to Advantage logic
    rationale_limit: int = 180
    debug: bool = False


class ClassifierPipeline:
    def __init__(self, config: PipelineConfig, self_train_model_path: Optional[str] = None):
        self.cfg = config
        self.model = None
        # Version metadata
        self.schema_version = "1.0"
        self.taxonomy_version = self._load_taxonomy_version()
        self.allowed_tags = self._load_tag_vocabulary()
        self.tag_vocabulary_version = self._load_tag_vocab_version()
        if self.cfg.enable_self_train and self_train_model_path:
            try:
                self.model = SelfTrainModel(self_train_model_path)  # type: ignore
            except Exception:
                self.model = None

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _load_taxonomy_version() -> str:
        """Attempt to read taxonomy.json for version; fallback to 'unknown'."""
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'taxonomy.json'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'taxonomy.json'),
        ]
        for path in candidates:
            try:
                with open(os.path.abspath(path), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    ver = data.get('version')
                    if isinstance(ver, str) and ver:
                        return ver
            except Exception:
                continue
        return 'unknown'

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _load_tag_vocabulary():
        path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'tag_vocabulary.json'))
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                allowed = data.get('allowed') or []
                if isinstance(allowed, list) and allowed:
                    return set(a.strip() for a in allowed if isinstance(a, str))
        except Exception:
            pass
        # Fallback minimal
        return {"Other"}

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _load_tag_vocab_version():
        path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'tag_vocabulary.json'))
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ver = data.get('version')
                if isinstance(ver, str) and ver:
                    return ver
        except Exception:
            pass
        return 'unknown'
        return 'unknown'

    def classify_text(self, text: str) -> Dict[str, Any]:
        # Basic PII scrubbing (emails, phone numbers). Extendable.
        original_text = text
        text = self._scrub_pii(text)
        heur = heuristic_classify(text)
        tag = heur.get('tag') or ''
        rule_strength = heur.get('ruleStrength', 0.0)
        signals = heur.get('signals', [])
        label = heur['label']
        model_prob = None
        model_probs = None
        nli = None
        provenance = []

        provisional_label = None
        original_nli_label = None

        if self.cfg.enable_zero_shot and self.cfg.zero_shot_primary:
            # Run zero-shot first for semantic grounding
            nli = zero_shot_classify(text, self.cfg.zero_shot_model)
            if nli and nli.get('available'):
                label = nli.get('label', label)
                original_nli_label = label
                provenance.append('zero-shot-primary')
                # Margin gating: lock NLI if confident margin
                if self.cfg.enable_margin_gating:
                    scores = nli.get('scores') or {}
                    if len(scores) >= 2:
                        sorted_scores = sorted(scores.values(), reverse=True)
                        if len(sorted_scores) >= 2 and (sorted_scores[0] - sorted_scores[1]) >= self.cfg.margin_threshold:
                            provenance.append('nli-margin-lock')
                            # mark as locked to avoid later neutral downgrade unless risk override triggers
                            nli_locked = True
                        else:
                            nli_locked = False
                    else:
                        nli_locked = False
                else:
                    nli_locked = False
            # Risk override: if heuristic saw strong risk signals but NLI chose Advantage/Neutral
            if heur['label'] == 'Risk' and rule_strength >= self.cfg.risk_override_threshold and label != 'Risk':
                label = 'Risk'
                provenance.append('risk-override')
            # Self-train (optional) can refine if enabled and heuristic weak & no override
            if self.model and self.cfg.enable_self_train and rule_strength < self.cfg.strong_rule_threshold:
                pred = self.model.predict([text])[0]
                model_probs = pred.get('probs')
                if model_probs:
                    model_prob = max(model_probs.values())
                # Only override if model_prob meaningfully high vs rule_strength
                if model_prob is not None and model_prob >= max(rule_strength, 0.5) and not (self.cfg.enable_margin_gating and 'nli-margin-lock' in provenance):
                    prev_label = label
                    label = pred.get('label', label)
                    if label != prev_label:
                        provenance.append('self-train-refine')
            # Provisional label logic: if final ends Neutral but NLI wanted Advantage retain NLI suggestion
            if label == 'Neutral' and original_nli_label == 'Advantage':
                provisional_label = 'Advantage'
                provenance.append('provisional-advantage')
            # Provisional risk logic (optional)
            if self.cfg.enable_provisional_risk and label != 'Risk' and heur['label'] == 'Risk' and rule_strength >= self.cfg.risk_override_threshold * 0.9:
                if label == 'Neutral':
                    provisional_label = provisional_label or 'Risk'
                    provenance.append('provisional-risk')
        else:
            # Original ordering: heuristic -> self-train -> zero-shot fallback
            if self.model and self.cfg.enable_self_train and rule_strength < self.cfg.strong_rule_threshold:
                pred = self.model.predict([text])[0]
                model_probs = pred.get('probs')
                if model_probs:
                    model_prob = max(model_probs.values())
                label = pred.get('label', label)
                provenance.append('self-train')
            # Fallback zero-shot condition
            if self.cfg.enable_zero_shot:
                top_p = model_prob if model_prob is not None else 0.0
                need_nli = (model_prob is not None and top_p < self.cfg.model_floor) or (rule_strength < 0.4 and label == 'Neutral')
                if need_nli:
                    nli = zero_shot_classify(text, self.cfg.zero_shot_model)
                    if nli and nli.get('available'):
                        label = nli.get('label', label)
                        provenance.append('zero-shot-fallback')

        # Confidence fusion (adapted for primary NLI)
        confidence_candidates = [rule_strength]
        if model_prob is not None:
            confidence_candidates.append(model_prob)
        if nli and nli.get('available') and nli.get('label') == label:
            scores = nli.get('scores') or {}
            nli_score = scores.get(label)
            if nli_score is not None:
                baseline = max(confidence_candidates)
                if nli_score > baseline:
                    # Up to +0.1 boost, same rule as before
                    boost = min(0.1, nli_score - baseline)
                    confidence_candidates.append(min(1.0, baseline + boost))
                else:
                    confidence_candidates.append(baseline)  # keep baseline
        base_conf = max(confidence_candidates)
        # Conflict dampener: if enabled and provenance shows both zero-shot and self-train adjustments without margin lock
        if self.cfg.enable_conflict_dampener:
            if any(p.startswith('self-train') for p in provenance) and any(p.startswith('zero-shot') for p in provenance) and 'nli-margin-lock' not in provenance:
                base_conf = max(0.0, base_conf - self.cfg.conflict_dampener)
        confidence = round(base_conf, 3)

        rationale = build_rationale(
            label=label,
            tag=tag,
            signals=signals,
            rule_strength=rule_strength,
            model_prob=model_prob,
            nli_supported=bool(nli and nli.get('available') and nli.get('label') == label),
            limit=self.cfg.rationale_limit,
            primary_nli=bool(self.cfg.enable_zero_shot and self.cfg.zero_shot_primary and nli and nli.get('available')),
        )

        record = {
            'text': text,
            'label': label,
            'labelTag': tag if tag in self.allowed_tags else 'Other',
            'rationale': rationale,
            'confidence': confidence,
            'schemaVersion': self.schema_version,
            'taxonomyVersion': self.taxonomy_version,
            'tagVocabularyVersion': self.tag_vocabulary_version,
        }
        if provisional_label and provisional_label != label:
            record['provisionalLabel'] = provisional_label
        if self.cfg.debug:
            record['debug'] = {
                'piiScrubbed': original_text != text,
                'ruleStrength': rule_strength,
                'signals': signals,
                'modelProb': model_prob,
                'modelProbs': model_probs,
                'nli': nli,
                'provenance': provenance,
                'config': asdict(self.cfg)
            }
        return record

    @staticmethod
    def _scrub_pii(text: str) -> str:
        # Email pattern
        email_pattern = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
        text = email_pattern.sub('[REDACTED_EMAIL]', text)
        # IPv4 addresses (do before phone so digits not consumed)
        ipv4_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        text = ipv4_pattern.sub('[REDACTED_IP]', text)
        # Phone (simple international + US patterns)
        phone_pattern = re.compile(r'(?:\+?\d[\s.-]?){7,15}(?:\d)')
        def repl_phone(m):
            digits = re.sub(r'\D','', m.group(0))
            return '[REDACTED_PHONE]' if len(digits) >= 7 else m.group(0)
        text = phone_pattern.sub(repl_phone, text)
        # Ethereum-style wallet addresses 0x + 40 hex
        wallet_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
        text = wallet_pattern.sub('[REDACTED_WALLET]', text)
        # Very naive BTC address pattern (base58 length 26-35)
        btc_pattern = re.compile(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b')
        text = btc_pattern.sub('[REDACTED_WALLET]', text)
        return text

__all__ = ["ClassifierPipeline", "PipelineConfig"]