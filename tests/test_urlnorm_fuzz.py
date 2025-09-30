import random, string
from core.urlnorm import normalize_url, canonical_url, in_scope

SEED = "https://example.com/"

ALPH = string.ascii_letters + string.digits


def rand_path():
    segs = ["".join(random.choice(ALPH) for _ in range(random.randint(1,8))) for _ in range(random.randint(1,5))]
    return "/".join(segs)


def rand_query():
    if random.random() < 0.3:
        return ""
    pairs = []
    for _ in range(random.randint(1,4)):
        k = "".join(random.choice(ALPH.lower()) for _ in range(random.randint(1,6)))
        v = "".join(random.choice(ALPH) for _ in range(random.randint(0,4)))
        pairs.append(f"{k}={v}")
    return "?" + "&".join(pairs)


def rand_fragment():
    if random.random() < 0.5:
        return ""
    return "#" + "".join(random.choice(ALPH) for _ in range(random.randint(1,6)))


def rand_href():
    # Mix of relative and absolute, with tracking params sometimes
    base = "" if random.random() < 0.5 else SEED
    path = rand_path()
    q = rand_query()
    frag = rand_fragment()
    href = base + path + q + frag
    # inject tracking param sometimes
    if random.random() < 0.3:
        if "?" in href:
            href += "&utm_source=test"
        else:
            href += "?utm_source=test"
    return href


def test_normalize_fuzz_idempotent():
    random.seed(1234)
    for _ in range(500):
        h = rand_href()
        n1 = normalize_url(SEED, h)
        n2 = normalize_url(SEED, n1)  # re-normalize normalized output
        assert n1 == n2, f"Normalization not idempotent for {h} => {n1} vs {n2}"
        c = canonical_url(n1)
        c2 = canonical_url(c)
        assert c == c2
        # Ensure no fragments or utm_source
        assert "#" not in n1
        assert "utm_source" not in n1.lower()
        # in_scope should not throw
        in_scope(SEED, n1)
