"""ADIN taxonomy: controlled label + sub-tag enumeration and validation.

This module centralizes the Advantage / Risk / Neutral sub-category tags
used for downstream reporting so classification output is guaranteed to
emit only allowed values. Keeping it isolated makes future taxonomy
updates (add/remove/rename) explicit and versioned.

Design principles:
  * Narrow surface: expose frozen sets + simple helpers.
  * Pure functions (no side effects) so easily testable.
  * Version string to attach to outputs / model metadata for drift tracking.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Set

TAXONOMY_VERSION = "adin.v2"  # expanded investor-centric tags


class TopLevel(Enum):
    Advantage = "Advantage"
    Risk = "Risk"
    Neutral = "Neutral"


# Sub-tag sets (strings kept human-readable for reporting)
ADVANTAGE_TAGS: Set[str] = frozenset({
    "Traction",              # User / adoption / usage metrics
    "Partners",              # Integrations, alliances
    "Security/Audit",        # Completed audits, formal verification
    "Token Utility",         # Governance / staking / fee burn utility claims
    "Performance",           # Throughput / latency / cost improvements
    "Team",                  # Team experience, hires
    "Technology Edge",       # Novel tech / cryptography / architecture advantage
    "Economics/Pricing",     # Revenue model, fee structure, margins
    "Market Position"        # TAM, market share, strategic positioning
})

RISK_TAGS: Set[str] = frozenset({
    "Regulatory",            # Legal / compliance / jurisdiction uncertainty
    "Centralization",        # Validator / control concentration
    "Security/Slash",        # Exploits, slashing, vulnerabilities
    "Token Supply",          # Emissions, unlocks, dilution
    "Competition",           # Competitive threats / overlap
    "Economic Risk",         # Revenue decline, unsustainable incentives
    "Execution Risk"         # Delays, missed milestones
})

NEUTRAL_TAGS: Set[str] = frozenset({
    "Mechanics",             # How the system works (restaking flow etc.)
    "Architecture",          # Design / components / modules
    "Roadmap",               # Future milestones / timelines
    "Governance Process",    # Proposal / voting process description
    "Tokenomics Summary",    # Descriptive token distribution / roles
    "Resource Allocation"    # Budget, grant distribution neutral statements
})

ALL_TAGS: Set[str] = frozenset().union(ADVANTAGE_TAGS, RISK_TAGS, NEUTRAL_TAGS)


def tag_group(tag: str) -> TopLevel | None:
    """Return the top-level group for a tag or None if unknown."""
    if tag in ADVANTAGE_TAGS:
        return TopLevel.Advantage
    if tag in RISK_TAGS:
        return TopLevel.Risk
    if tag in NEUTRAL_TAGS:
        return TopLevel.Neutral
    return None


def validate(label: str, tag: str) -> bool:
    """Validate consistency of (label, tag).

    Rules:
      * Tag must be in controlled set.
      * label must equal tag_group(tag) (except allowing Neutral label for any Neutral tag).
    """
    try:
        top = TopLevel(label)
    except ValueError:
        return False
    group = tag_group(tag)
    return group is not None and group == top


def assert_valid(label: str, tag: str) -> None:
    if not validate(label, tag):  # pragma: no cover (exception path trivial)
        raise ValueError(f"Invalid (label, tag) pair: {label}, {tag}")


def taxonomy_summary() -> dict:
    return {
        "version": TAXONOMY_VERSION,
        "advantage": sorted(ADVANTAGE_TAGS),
        "risk": sorted(RISK_TAGS),
        "neutral": sorted(NEUTRAL_TAGS),
        "all": sorted(ALL_TAGS),
    }


__all__ = [
    "TAXONOMY_VERSION",
    "TopLevel",
    "ADVANTAGE_TAGS",
    "RISK_TAGS",
    "NEUTRAL_TAGS",
    "ALL_TAGS",
    "tag_group",
    "validate",
    "assert_valid",
    "taxonomy_summary",
]
