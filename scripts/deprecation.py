"""Helper utilities for standardized deprecation warnings.

Usage:
    from scripts.deprecation import emit_deprecation
    emit_deprecation('run_all.py', 'python scripts/run_pipeline.py --url <seed> --all', '0.3.0')
"""
from __future__ import annotations
import warnings

def emit_deprecation(thing: str, replacement: str, removal_version: str, category=DeprecationWarning):
    """Emit a formatted deprecation warning.

    Parameters
    ----------
    thing : str
        The deprecated command, symbol, or file name.
    replacement : str
        The recommended alternative usage.
    removal_version : str
        Target version where removal will occur.
    category : Warning subclass
        Defaults to DeprecationWarning; can be changed for escalations.
    """
    msg = (
        f"'{thing}' is deprecated and will be removed in version {removal_version}. "
        f"Use: {replacement}"
    )
    warnings.warn(msg, category=category, stacklevel=2)
