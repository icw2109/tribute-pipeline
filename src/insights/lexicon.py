"""Lexicon and taxonomy management for classification.

This module externalizes the vocabulary / pattern sets used by the
heuristic + ML hybrid classifier so they can be versioned and, later,
optionally loaded from a JSON file supplied by the user.

Design goals:
  * Provide a strongly typed, immutable in-memory representation.
  * Stable hashing so a trained model can record which lexicon version
    it depended on (for reproducibility & drift detection).
  * Safe defaults embedded in code (zero config path) while allowing
    future override via load_lexicon(path).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Set
import json
import hashlib


@dataclass(frozen=True)
class Lexicon:
    risk_terms: Set[str]
    weak_risk_terms: Set[str]
    advantage_terms: Set[str]
    negation_terms: Set[str]
    comparative_terms: Set[str]
    performance_terms: Set[str]
    partner_terms: Set[str]
    risk_context_terms: Set[str]
    taxonomy_tags: Set[str]
    version: str = "0.1"

    def hash(self) -> str:
        """Deterministic content hash (sha256 of sorted tokens).

        Used to bind a trained ML artifact to a specific lexicon.
        """
        parts: Iterable[Iterable[str]] = [
            sorted(self.risk_terms),
            sorted(self.weak_risk_terms),
            sorted(self.advantage_terms),
            sorted(self.negation_terms),
            sorted(self.comparative_terms),
            sorted(self.performance_terms),
            sorted(self.partner_terms),
            sorted(self.risk_context_terms),
            sorted(self.taxonomy_tags),
            [self.version],
        ]
        h = hashlib.sha256()
        for group in parts:
            for token in group:
                h.update(token.encode("utf-8"))
            h.update(b"|")
        return h.hexdigest()[:16]


DEFAULT_LEXICON = Lexicon(
    risk_terms={
        "risk","risks","slashing","slashed","penalty","penalties","penalized","exploit",
        "exploits","vulnerability","vulnerabilities","attack","attacks","downtime","loss",
        "uncertainty","regulatory","liability","slash","seize","seizure","slashable"
    },
    weak_risk_terms={"audit","audited","bug","bugs","issue","issues"},
    advantage_terms={
        "growth","increase","increased","increasing","scaling","scalable","partnership","partnerships",
        "integration","integrations","adoption","adopted","launch","launched","innovative","efficiency",
        "efficient","performance","improvement","improved","unique","differentiated","restaking",
        "throughput","scalability","expansion","expanded","expanding","milestone","decentralized",
        "decentralization","upgrade","upgraded","reduction","reduced","optimize","optimized","optimization"
    },
    negation_terms={"no","not","without","never","none","lack","lacking"},
    comparative_terms={
        "faster","fastest","slower","slower","higher","highest","lower","lowest","better","best",
        "worse","cheaper","cheapest","more","less","greater","smaller","larger","improved","increase",
        "decrease","reduced","reduction","x"  # 'x' in patterns like 10x
    },
    performance_terms={"throughput","latency","tps","mb/s","gb/s","scalability","cost","efficiency"},
    partner_terms={"partner","partners","partnership","integration","integrations"},
    risk_context_terms={"slashing","penalty","penalties","regulatory","risk","attack","downtime"},
    taxonomy_tags={
        "Performance","Adoption","Tokenomics","Roadmap","Security","Governance","Architecture",
        "Partnerships","Differentiation","Research","General"
    },
)


def load_lexicon(path: str | Path) -> Lexicon:
    """Load a lexicon from JSON file.

    Expected JSON schema keys mirror Lexicon field names (except version optional).
    Missing optional sets default to empty; required core sets raise if absent.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    def _set(key: str) -> Set[str]:
        return set(map(str.lower, data.get(key, [])))
    version = str(data.get("version", "custom"))
    return Lexicon(
        risk_terms=_set("risk_terms"),
        weak_risk_terms=_set("weak_risk_terms"),
        advantage_terms=_set("advantage_terms"),
        negation_terms=_set("negation_terms"),
        comparative_terms=_set("comparative_terms"),
        performance_terms=_set("performance_terms"),
        partner_terms=_set("partner_terms"),
        risk_context_terms=_set("risk_context_terms"),
        taxonomy_tags=_set("taxonomy_tags"),
        version=version,
    )


__all__ = ["Lexicon","DEFAULT_LEXICON","load_lexicon"]
