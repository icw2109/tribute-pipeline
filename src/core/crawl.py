from __future__ import annotations
import time
import collections
import requests
import hashlib
from typing import TypedDict, Optional, Deque, Iterable, Set, Tuple, Callable, Dict, Any
from bs4 import BeautifulSoup
from .urlnorm import normalize_url, in_scope, canonical_url
from .config import CrawlConfig
from .boilerplate import extract_title_and_text
from .robots import can_fetch

class PageRecord(TypedDict):
    url: str
    title: str
    text: str
    depth: int
    discoveredFrom: Optional[str]

class CrawlStats(TypedDict):
    fetched_ok: int
    skipped_robots: int
    skipped_off_scope: int
    skipped_non_html: int
    errors_fetch: int
    duplicates: int
    enqueued: int

MAX_PAGES_DEFAULT = 50
MAX_DEPTH_DEFAULT = 2
PER_PAGE_LINK_CAP_DEFAULT = 25
MIN_RPS_DEFAULT = 1.0  # >= 1 req/sec polite
# UA now comes from CrawlConfig

BLOCKED_SCHEMES = ("mailto:", "tel:", "javascript:")

def _same_domain_links(base_url: str, soup: BeautifulSoup, seed: str, per_page_cap: int, extra_scope_hosts: tuple[str, ...] = ()) -> list[str]:
    """Collect same-domain (or extra-scope host) links up to per_page_cap.

    Prior to extra scope host feature we only admitted links whose registrable domain
    matched the seed. When a site has migrated (seed redirects) we may want to include
    a second explicit host. The crawl loop already re-checks scope before enqueueing,
    but filtering here ensures we generate candidates in the first place.
    """
    from urllib.parse import urlparse
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        if href.startswith(BLOCKED_SCHEMES):
            continue
        nu = normalize_url(base_url, href)
        # Fast path original in-scope
        if in_scope(seed, nu):
            links.append(nu)
            continue
        if extra_scope_hosts:
            host = (urlparse(nu).hostname or '').lower()
            for h in extra_scope_hosts:
                if host == h or host.endswith('.' + h):
                    links.append(nu)
                    break
    uniq = sorted(dict.fromkeys(links))
    return uniq[:per_page_cap]

def crawl(
    config: CrawlConfig,
    fetch_func: Callable[[requests.Session, str], requests.Response] | None = None,
    stats: Dict[str, int] | None = None,
    event_cb: Callable[[Dict[str, Any]], None] | None = None,
) -> Iterable[PageRecord]:
    """Yield PageRecord dicts in BFS order."""
    session = requests.Session()
    session.headers["User-Agent"] = config.user_agent
    if config.browser_headers:
        # Minimal common headers (avoid full fingerprinting complexity)
        session.headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        session.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        session.headers.setdefault("Connection", "keep-alive")

    seed = config.seed
    seed_norm = canonical_url(seed)
    q: Deque[Tuple[str, int, Optional[str]]] = collections.deque([(seed_norm, 0, None)])
    seen: Set[str] = {seed_norm}
    last_fetch = 0.0
    fetched = 0

    min_interval = 1.0 / max(config.rps, 1e-6)

    # stats initialization
    if stats is None:
        stats = {}
    stats.setdefault('fetched_ok', 0)
    stats.setdefault('skipped_robots', 0)
    stats.setdefault('skipped_off_scope', 0)
    stats.setdefault('skipped_non_html', 0)
    stats.setdefault('errors_fetch', 0)
    stats.setdefault('duplicates', 0)
    stats.setdefault('enqueued', 0)
    stats.setdefault('skipped_too_large', 0)
    stats.setdefault('duplicates_content', 0)
    content_hashes: Set[str] = set() if config.enable_content_dedupe else set()

    while q and fetched < config.max_pages:
        url, depth, parent = q.popleft()
        # Backward compatibility: allow monkeypatched can_fetch lacking new fallback_allow param
        try:
            allowed = can_fetch(config.user_agent, url, fallback_allow=config.robots_fallback_allow)
        except TypeError:
            allowed = can_fetch(config.user_agent, url)
        if not allowed:
            stats['skipped_robots'] += 1
            if event_cb:
                event_cb({"type":"robots_skip","url":url})
            continue

        # rate limiting
        now = time.monotonic()
        wait = min_interval - (now - last_fetch)
        if wait > 0:
            time.sleep(wait)

        attempt = 0
        resp = None
        while True:
            try:
                if fetch_func:
                    resp = fetch_func(session, url, timeout=config.timeout, allow_redirects=True)
                else:
                    resp = session.get(url, timeout=config.timeout, allow_redirects=True)
                status = getattr(resp, 'status_code', 0)
                if status in config.retry_statuses and attempt < config.retry_attempts - 1:
                    backoff = config.retry_backoff_base * (2 ** attempt)
                    if event_cb:
                        event_cb({"type":"retry","url":url,"status":status,"attempt":attempt+1,"backoff":backoff})
                    time.sleep(backoff)
                    attempt += 1
                    continue
                break
            except requests.RequestException as e:
                if attempt < config.retry_attempts - 1:
                    backoff = config.retry_backoff_base * (2 ** attempt)
                    if event_cb:
                        event_cb({"type":"retry_exception","url":url,"error":str(e),"attempt":attempt+1,"backoff":backoff})
                    time.sleep(backoff)
                    attempt += 1
                    continue
                else:
                    stats['errors_fetch'] += 1
                    if event_cb:
                        event_cb({"type":"error","phase":"fetch","url":url,"error":str(e)})
                    resp = None
                    break
        if resp is None:
            continue
        last_fetch = time.monotonic()
        # Scope re-check after redirects
        final_url = resp.url
        def _in_scope(url: str) -> bool:
            if in_scope(seed, url):
                return True
            if config.extra_scope_hosts:
                from urllib.parse import urlparse
                host = (urlparse(url).hostname or '').lower()
                for h in config.extra_scope_hosts:
                    if host == h or host.endswith('.' + h):
                        return True
            return False

        if not _in_scope(final_url):
            stats['skipped_off_scope'] += 1
            if event_cb:
                event_cb({"type":"off_scope","from":url,"final":final_url})
            continue
        ctype = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in ctype:
            stats['skipped_non_html'] += 1
            if event_cb:
                event_cb({"type":"non_html","url":final_url,"content_type":ctype})
            continue
        raw_html = resp.text
        # size guard
        if config.max_html_bytes is not None:
            size = len(raw_html.encode('utf-8', errors='ignore'))
            if size > config.max_html_bytes:
                stats['skipped_too_large'] += 1
                if event_cb:
                    event_cb({"type":"too_large","url":final_url,"bytes":size})
                continue

        title, text = extract_title_and_text(raw_html)

        # content hash dedupe (normalized by collapsing whitespace)
        if config.enable_content_dedupe:
            norm_for_hash = ' '.join(text.split())[:200000]  # limit huge texts before hashing
            h = hashlib.sha256(norm_for_hash.encode('utf-8', errors='ignore')).hexdigest()
            if h in content_hashes:
                stats['duplicates_content'] += 1
                if event_cb:
                    event_cb({"type":"duplicate_content","url":final_url})
                continue
            content_hashes.add(h)
        record = PageRecord(url=final_url, title=title, text=text, depth=depth, discoveredFrom=parent)
        if event_cb:
            event_cb({"type":"fetched","url":final_url,"depth":depth,"title_len":len(title),"text_len":len(text)})
        yield record
        fetched += 1
        stats['fetched_ok'] = fetched
        if depth >= config.max_depth:
            continue
        soup = BeautifulSoup(raw_html, "lxml")
        for nu in _same_domain_links(final_url, soup, seed, config.per_page_cap, config.extra_scope_hosts):
            nu_c = canonical_url(nu)
            # Re-scope check for extra hosts before enqueue
            if nu_c not in seen and _in_scope(nu_c):
                seen.add(nu_c)
                q.append((nu_c, depth + 1, final_url))
                stats['enqueued'] += 1
                if event_cb:
                    event_cb({"type":"enqueued","url":nu_c,"parent":final_url,"depth":depth+1})
            else:
                stats['duplicates'] += 1
                if event_cb:
                    event_cb({"type":"duplicate","url":nu_c})
