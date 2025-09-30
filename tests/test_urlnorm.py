from core.urlnorm import normalize_url, in_scope, canonical_url

SEED = "https://example.com/"

def test_normalize_removes_fragment_and_tracking():
    u = normalize_url(SEED, "https://example.com/Path/Page?utm_source=abc&x=1#section")
    assert u == "https://example.com/Path/Page?x=1"

def test_in_scope_root_and_subdomain():
    assert in_scope(SEED, "https://example.com/other")
    assert in_scope(SEED, "https://sub.example.com/thing")
    assert not in_scope(SEED, "https://notexample.org/")

def test_canonical_url_trailing_slash():
    assert canonical_url("https://example.com/path/") == "https://example.com/path"
    assert canonical_url("https://example.com/") == "https://example.com/"
