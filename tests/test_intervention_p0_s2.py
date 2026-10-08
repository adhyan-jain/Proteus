"""The S2 gate reuses the frozen L.1 rules; only the criteria's scenario name differs."""
from dataclasses import asdict

import proteus.intervention.p0 as p0
from proteus.intervention.p0_s2 import s2_criteria
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import SCENARIOS
from proteus.intervention.validity import P0Criteria, spec_rules_sha256


def test_s2_criteria_change_only_the_scenario_and_are_restored():
    original = p0.P0Criteria
    with s2_criteria():
        c = p0.P0Criteria()
        assert c.scenario == "S2"
        a, b = asdict(c), asdict(P0Criteria())
        assert {k for k in a if a[k] != b[k]} == {"scenario"}
        assert c.digest() != P0Criteria().digest()
    assert p0.P0Criteria is original and p0.P0Criteria().scenario == "S1"


def test_the_preregistered_s2_configuration_is_recognised_and_s1_is_unchanged():
    c = P0Criteria(scenario="S2")
    ok, problems = p0.check_preregistered(SCENARIOS["S2"], c.budgets, c.seeds, InterventionParams(), c)
    assert ok and not problems
    ok1, _ = p0.check_preregistered(SCENARIOS["S1"], (25, 100), (0, 1, 2, 3, 4), InterventionParams(),
                                    P0Criteria())
    assert ok1
    bad, problems = p0.check_preregistered(SCENARIOS["S2"], (25, 100), (0, 1, 2, 3, 4),
                                           InterventionParams(), P0Criteria())
    assert not bad and any("scenario" in p for p in problems)
    assert spec_rules_sha256() == "779e679aa006afafc1caa79acdc4c3b659ec151a241b81e7dd4224011aabb11e"
