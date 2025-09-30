"""Environment sanity check.
Run: python scripts/env_check.py
Outputs JSON with:
  activeVenv: path guess
  pythonVersion
  corePackages (present/missing + version)
  optionalPackages (advanced features)
  gpuAvailable (torch.cuda.is_available if torch present)
  warnings
"""
from __future__ import annotations
import json, sys, importlib, os, platform

CORE = [
    ("requests", None),
    ("beautifulsoup4", "bs4"),
    ("lxml", None),
    ("scikit-learn", "sklearn"),
    ("tqdm", None),
    ("numpy", None),
]
OPTIONAL = [
    ("sentence-transformers", "sentence_transformers"),
    ("transformers", None),
    ("torch", None),
    ("pandas", None),
]

def detect_pkg(dist_name: str, import_name: str | None):
    mod_name = import_name or dist_name.replace('-', '_')
    try:
        mod = importlib.import_module(mod_name)
        ver = getattr(mod, '__version__', 'unknown')
        return {"name": dist_name, "import": mod_name, "present": True, "version": ver}
    except Exception:
        return {"name": dist_name, "import": mod_name, "present": False}

def main():
    data = {}
    data['pythonVersion'] = sys.version.split()[0]
    data['platform'] = platform.platform()
    data['executable'] = sys.executable
    data['activeVenv'] = os.environ.get('VIRTUAL_ENV') or 'UNKNOWN'
    data['corePackages'] = [detect_pkg(*c) for c in CORE]
    data['optionalPackages'] = [detect_pkg(*c) for c in OPTIONAL]
    # GPU check
    gpu = None
    try:
        import torch  # type: ignore
        if hasattr(torch, 'cuda'):
            gpu = bool(torch.cuda.is_available())
    except Exception:
        gpu = None
    data['gpuAvailable'] = gpu
    warnings = []
    if data['activeVenv'] == 'UNKNOWN':
        warnings.append('Not running inside a detected virtual environment (VIRTUAL_ENV unset).')
    missing_core = [p['name'] for p in data['corePackages'] if not p['present']]
    if missing_core:
        warnings.append(f"Missing core packages: {missing_core}")
    data['warnings'] = warnings
    print(json.dumps(data, indent=2))

if __name__ == '__main__':
    main()