"""The action table: every finding has an action, and the ranking is euros per day."""

import re
from pathlib import Path

from app.full_audit.analyzers.actions import ACTIONS, FINDING_ACTIONS, build_action_list
from app.full_audit.schemas import FindingOut

_APP = Path(__file__).parent.parent / "app"


def test_every_registered_finding_has_an_action():
    """A new finding_id without an entry in FINDING_ACTIONS would silently drop out of
    the client's action list — fail here instead."""
    ids = set()
    for path in _APP.rglob("*.py"):
        ids |= set(re.findall(r'finding_id="([a-z_.]+)"', path.read_text(encoding="utf-8")))
    assert ids, "the scan must find the registered finding ids"
    assert ids - set(FINDING_ACTIONS) == set()
    assert set(FINDING_ACTIONS.values()) <= set(ACTIONS)


def _f(fid, low=None, high=None, **kw):
    return FindingOut(finding_id=fid, owning_layer=1, metric=fid, monthly_low=low,
                      monthly_high=high, priced=low is not None, **kw)


def test_findings_fixed_by_one_action_are_grouped_and_summed():
    actions = build_action_list([
        _f("perf.lcp_mobile", 1_000, 3_000),
        _f("adtraffic.post_click_bounce", 500, 1_000, confidence="high"),
    ])
    assert len(actions) == 1
    speed = actions[0]
    assert speed.action_key == "speed.lcp"
    assert (speed.monthly_low, speed.monthly_high) == (1_500, 4_000)
    assert speed.finding_ids == ["perf.lcp_mobile", "adtraffic.post_click_bounce"]
    assert speed.confidence == "medium"  # the weakest link


def test_actions_rank_by_euros_per_day_then_unpriced_last():
    actions = build_action_list([
        _f("perf.lcp_mobile", 2_000, 6_000),        # €6k / 15 days = 400/day
        _f("checkout.no_guest", 500, 1_000),        # €1k / 1 day = 1000/day
        _f("cro.social_proof", confidence="low", verify_manually=True, priority="high"),
        _f("perf.cls_mobile", status="good"),       # healthy: no action
    ])
    assert [a.action_key for a in actions] == ["checkout.guest", "speed.lcp", "cro.social_proof"]
    assert actions[-1].priced is False and actions[-1].verify_manually is True
