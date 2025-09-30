from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CrawlConfig:
    seed: str
    max_depth: int = 2
    max_pages: int = 50
    rps: float = 1.0
    per_page_cap: int = 25
    user_agent: str = "TributeTakehomeBot/0.1 (+you@example.com)"
    timeout: int = 15  # seconds
    retry_attempts: int = 3
    retry_backoff_base: float = 0.75  # seconds initial backoff
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    max_html_bytes: int | None = 800_000  # skip pages larger than this (approx 800KB) if set
    enable_content_dedupe: bool = True  # hash normalized text to avoid duplicate content pages
    robots_fallback_allow: bool = False  # if True, treat unparsable/malformed robots.txt responses as allow-all
    extra_scope_hosts: tuple[str, ...] = ()  # additional hostnames explicitly allowed (exact or their subdomains)
    browser_headers: bool = False  # if True, add common browser Accept / Accept-Language headers
