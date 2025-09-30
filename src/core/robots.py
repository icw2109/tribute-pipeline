from __future__ import annotations
from urllib import robotparser
from urllib.parse import urlparse
from functools import lru_cache
import requests

MALFORMED_HINTS = (
    '<!DOCTYPE html', '<html', '<head', '<body'
)

@lru_cache(maxsize=32)
def _get_rp(robots_url: str) -> robotparser.RobotFileParser:
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        pass
    return rp

def _looks_like_html(text: str) -> bool:
    lt = text.lower()
    return any(h in lt for h in MALFORMED_HINTS)

def can_fetch(user_agent: str, url: str, fallback_allow: bool = False) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    rp = _get_rp(robots_url)
    try:
        allowed = rp.can_fetch(user_agent, url)
        if fallback_allow:
            # Conditions to allow:
            # 1. No rules parsed (entries empty & default None)
            # 2. robots fetch 4xx/5xx OR HTML without 'user-agent:' directive
            try:
                resp = requests.get(robots_url, timeout=8)
                text = resp.text if resp is not None else ''
                ua_present = 'user-agent:' in text.lower()
                malformed = _looks_like_html(text) and not ua_present
                status_block = resp.status_code >= 400
                no_rules = (not rp.entries and rp.default_entry is None)
                if no_rules and (status_block or malformed):
                    return True
            except Exception:
                # network error while fallback flag set -> allow
                return True
        return allowed
    except Exception:
        return True
