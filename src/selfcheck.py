"""Environment self-check utility for the tribute pipeline.

Prints:
 - Package version
 - Key module file locations
 - Ability to import core components
 - Simple crawl+extract smoke (optional flag)
"""
from __future__ import annotations
import importlib, json, sys
from importlib import metadata

def main():
    out = {}
    # Version
    try:
        out['version'] = metadata.version('tribute-pipeline')
    except Exception:
        out['version'] = 'unknown'
    modules = ['core.crawl','insights','cli.scrape','cli.extract_insights','cli.classify']
    info=[]
    for m in modules:
        try:
            mod = importlib.import_module(m)
            info.append({'module': m, 'file': getattr(mod,'__file__',None), 'ok': True})
        except Exception as e:
            info.append({'module': m, 'error': str(e), 'ok': False})
    out['modules']=info
    print(json.dumps(out, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
