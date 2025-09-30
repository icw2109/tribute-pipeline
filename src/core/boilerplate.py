from __future__ import annotations
from bs4 import BeautifulSoup
import re

BLOCK_SELECTORS = [
    "script","style","noscript","template",
    "header","nav","footer","aside",
    "[role=navigation]","[role=banner]","[role=contentinfo]",
    ".cookie",".cookies",".banner",".modal",".sidebar",".hero"
]

def extract_title_and_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    for sel in BLOCK_SELECTORS:
        for node in soup.select(sel):
            try:
                node.decompose()
            except Exception:
                pass
    title = ""
    if soup.title and soup.title.string:
        try:
            title = soup.title.string.strip()[:300]
        except Exception:
            title = ""
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text
