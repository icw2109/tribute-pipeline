from __future__ import annotations
"""Lightweight metrics extraction utilities.

Parses:
  - Percentages: 12%, 7.5%
  - Currency magnitudes: $50M, $1.2B, USD 300k, 500k USD
  - Plain numbers that look like years: 1999..2199 (kept as year)

Return shape per metric:
  {"surface": str, "value": float|int, "kind": "percent|currency|year|number", "unit": str|None}

Magnitude suffixes M/B/K interpreted as *1e6 / 1e9 / 1e3.
Simplistic disambiguation; we keep transparent and deterministic.
"""
from dataclasses import dataclass
from typing import List, Dict, Iterable
import re

PERCENT_RE = re.compile(r"(?P<num>\d{1,3}(?:\.\d+)?)[ ]?%")
# Currency: (symbol OR code) required to reduce noise; optional magnitude suffix.
CurrencyCode = r"USD|EUR|GBP"
# Pattern groups: symbol-form OR code-leading OR number + suffix + code trailing
CURRENCY_RE = re.compile(
    rf"((?P<sym>[$€£])\s?(?P<num>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)(?P<suffix>[kKmMbB])?)|"
    rf"((?P<code>{CurrencyCode})\s?(?P<num2>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)(?P<suffix2>[kKmMbB])?)|"
    rf"((?P<num3>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)(?P<suffix3>[kKmMbB])\s?(?P<code3>{CurrencyCode}))"
)
YEAR_RE = re.compile(r"\b(19|20|21)\d{2}\b")
DATE_RANGE_RE = re.compile(r"\b\d{2}-\d{2}\b")  # e.g., 09-18 (skip as date fragment)
GENERIC_NUM_RE = re.compile(r"\b\d{2,3}(?:,\d{3})*(?:\.\d+)?\b")  # min length 2 to reduce stray digits

SUFFIX_MULT = {'k':1e3,'m':1e6,'b':1e9}

@dataclass
class Metric:
    surface: str
    value: float
    kind: str
    unit: str | None


def _to_float(num: str) -> float:
    return float(num.replace(',', ''))


def extract_metrics(text: str) -> List[Metric]:
    metrics: List[Metric] = []
    seen_spans: set[tuple[int,int]] = set()

    # Skip date range fragments early (mark spans so parts not individually counted)
    for dm in DATE_RANGE_RE.finditer(text):
        span = dm.span()
        seen_spans.add(span)
        # Also mark the individual day/month components so they are not picked up separately
        inner = dm.group(0)
        start = span[0]
        parts = inner.split('-')
        offset = 0
        for part in parts:
            part_len = len(part)
            seen_spans.add((start + offset, start + offset + part_len))
            offset += part_len + 1  # include separator

    # Percentages
    for m in PERCENT_RE.finditer(text):
        span = m.span()
        if span in seen_spans: continue
        seen_spans.add(span)
        value = float(m.group('num'))
        metrics.append(Metric(surface=m.group(0), value=value, kind='percent', unit='%'))

    # Currency patterns
    for m in CURRENCY_RE.finditer(text):
        gd = m.groupdict()
        raw_num = gd.get('num') or gd.get('num2') or gd.get('num3')
        if not raw_num:
            continue
        suffix = (gd.get('suffix') or gd.get('suffix2') or gd.get('suffix3') or '').lower()
        mult = SUFFIX_MULT.get(suffix, 1.0)
        value = _to_float(raw_num) * mult
        code = gd.get('code') or gd.get('code2') or gd.get('code3')
        sym = gd.get('sym')
        unit = code or sym or None
        metrics.append(Metric(surface=m.group(0).strip(), value=value, kind='currency', unit=unit))

    # Years
    for m in YEAR_RE.finditer(text):
        span = m.span()
        if span in seen_spans: continue
        seen_spans.add(span)
        yr = int(m.group(0))
        metrics.append(Metric(surface=m.group(0), value=yr, kind='year', unit=None))

    # Generic numbers (that are not already captured as part of currency/percent/year)
    for m in GENERIC_NUM_RE.finditer(text):
        span = m.span()
        if span in seen_spans: continue
        seen_spans.add(span)
        surface = m.group(0)
        # Filter out leading zeros and very small contextless numbers < 10 unless decimal
        if re.fullmatch(r"0+", surface):
            continue
        val = _to_float(surface)
        if val < 10 and '.' not in surface:  # treat small integers as noise
            continue
        # Skip 2-digit numbers that are adjacent to date separators (likely date fragments)
        if len(surface) == 2:
            s, e = span
            prev_char = text[s-1] if s > 0 else ''
            next_char = text[e] if e < len(text) else ''
            if prev_char in '-/' or next_char in '-/':
                continue
        metrics.append(Metric(surface=surface, value=val, kind='number', unit=None))

    return metrics

__all__ = ['Metric','extract_metrics']
