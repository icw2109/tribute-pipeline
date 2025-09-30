from __future__ import annotations
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from typing import Iterable

TRACKING_PARAMS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","ref","ref_src","gclid"}

def normalize_url(base: str, href: str) -> str:
    """Resolve relative → absolute, drop fragments & tracking, normalize scheme/host.

    Keeps original path casing (server sensitivity unknown) but lowercases scheme+netloc.
    Removes known marketing query params; preserves order via re-encoding.
    """
    absu = urljoin(base, href)
    u = urlparse(absu)
    u = u._replace(fragment="")
    q = [ (k, v) for k, v in parse_qsl(u.query, keep_blank_values=False) if k.lower() not in TRACKING_PARAMS ]
    if q:
        u = u._replace(query=urlencode(q, doseq=True))
    else:
        u = u._replace(query="")
    u = u._replace(scheme=u.scheme.lower(), netloc=u.netloc.lower())
    return urlunparse(u)

def registrable(seed_url: str) -> str:
    return urlparse(seed_url).hostname or ""

def in_scope(seed_url: str, candidate: str) -> bool:
    host = (urlparse(candidate).hostname or "").lower()
    root = registrable(seed_url).lower()
    return host == root or host.endswith("." + root)

def canonical_url(u: str) -> str:
    """Apply additional lightweight canonical rules beyond normalize_url.

    - Remove trailing slash if path length > 1 and endswith('/').
    - Lowercase host already handled by normalize_url.
    """
    p = urlparse(u)
    path = p.path
    if path.endswith('/') and len(path) > 1:
        path = path.rstrip('/')
    p = p._replace(path=path or '/')
    return urlunparse(p)
