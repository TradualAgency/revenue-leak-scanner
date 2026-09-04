"""Admission rules for manually-supplied competitors.

The anchor case is the bug this module exists to kill: an operator pasting a full URL
used to have it appended verbatim to `selected_domains`, after which `measure.py` built
`https://https://shop.nl` and the competitor was silently recorded as unreachable.
"""

from app.competitor_benchmark.seeds import resolve_seeds
from app.domains import normalize_competitor_input

STORE = "store.nl"


def _codes(outcomes):
    return [o.code for o in outcomes]


def test_full_url_is_normalized_to_a_bare_domain():
    accepted, outcomes = resolve_seeds(["https://shop.nl"], STORE, [], limit=8)

    assert accepted == ["shop.nl"]
    assert outcomes[0].code == "normalized"
    assert outcomes[0].status == "accepted"
    # The regression guard: nothing with a scheme may ever reach the measurement path.
    assert "://" not in accepted[0]


def test_url_with_path_query_and_casing_collapses_to_the_host():
    accepted, _ = resolve_seeds(["HTTPS://WWW.Shop.NL/collections/all?x=1"], STORE, [], limit=8)
    assert accepted == ["shop.nl"]


def test_www_and_bare_variants_are_one_competitor():
    accepted, outcomes = resolve_seeds(["www.x.nl", "x.nl"], STORE, [], limit=8)

    assert accepted == ["x.nl"]
    assert _codes(outcomes) == ["normalized", "duplicate"]


def test_duplicate_against_the_existing_set_is_a_noop():
    accepted, outcomes = resolve_seeds(["https://a.nl/"], STORE, existing=["a.nl"], limit=8)

    assert accepted == []
    assert outcomes[0].code == "duplicate"


def test_the_store_itself_is_always_rejected():
    accepted, outcomes = resolve_seeds(
        ["WWW.STORE.NL/collections/all?x=1"], STORE, [], limit=8,
    )

    assert accepted == []
    assert outcomes[0].code == "self"
    assert outcomes[0].status == "rejected"


def test_same_brand_is_a_warning_not_a_rejection():
    # `is_same_brand` is substring containment and produces false positives, so a fuzzy
    # match must not block a competitor the operator explicitly asked for.
    accepted, outcomes = resolve_seeds(["shop.store.nl"], STORE, [], limit=8)

    assert accepted == ["shop.store.nl"]
    assert outcomes[0].code == "same_brand"
    assert outcomes[0].status == "warning"


def test_blocklisted_marketplace_is_admitted_with_a_warning():
    accepted, outcomes = resolve_seeds(["amazon.nl"], STORE, [], limit=8)

    assert accepted == ["amazon.nl"]
    assert outcomes[0].code == "blocklist"
    assert outcomes[0].status == "warning"
    assert "marketplace" in outcomes[0].message_nl


def test_overflow_past_the_limit_is_reported_not_silently_dropped():
    raw = [f"c{i}.nl" for i in range(10)]
    accepted, outcomes = resolve_seeds(raw, STORE, [], limit=8)

    assert len(accepted) == 8
    assert _codes(outcomes)[8:] == ["over_limit", "over_limit"]
    assert "limiet van 8" in outcomes[8].message_nl


def test_limit_accounts_for_domains_already_on_the_run():
    accepted, outcomes = resolve_seeds(
        ["new1.nl", "new2.nl"], STORE, existing=[f"e{i}.nl" for i in range(7)], limit=8,
    )

    assert accepted == ["new1.nl"]
    assert outcomes[1].code == "over_limit"


def test_garbage_input_is_rejected_as_invalid():
    raw = ["", "   ", "not a domain", "http://", "1.2.3.4", "localhost", "nl", "."]
    accepted, outcomes = resolve_seeds(raw, STORE, [], limit=8)

    assert accepted == []
    assert _codes(outcomes) == ["invalid"] * len(raw)


def test_accepted_domains_keep_input_order():
    accepted, _ = resolve_seeds(["c.nl", "a.nl", "b.nl"], STORE, [], limit=8)
    assert accepted == ["c.nl", "a.nl", "b.nl"]


def test_normalize_preserves_store_subdomains_on_shared_platforms():
    # Rolling `acme.myshopify.com` up to `myshopify.com` would measure Shopify itself.
    assert normalize_competitor_input("https://acme.myshopify.com/") == "acme.myshopify.com"
