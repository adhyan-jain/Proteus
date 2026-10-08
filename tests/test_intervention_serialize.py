"""Strict-JSON serialisation: NaN is an explicit marker, never a number, never bare `NaN`."""
import json
import math
from dataclasses import dataclass

import numpy as np
import pytest

from proteus.intervention.promotion import CandidateReport, Decision
from proteus.intervention.serialize import (
    NONFINITE_KEY, dumps_strict, from_jsonable, loads_strict, to_jsonable, write_json)

NAN = float("nan")


def _nan_report():
    return CandidateReport(
        sanity_ok=True, sanity_msg="ok", utility_gain_point=NAN, utility_gain_lcb=NAN,
        delta_stable_f1_point=NAN, delta_stable_f1_ucb=NAN, delta_fpr_stable_point=NAN,
        delta_fpr_stable_ucb=NAN, delta_fpr_current_point=0.01, delta_fpr_current_ucb=0.02,
        utility_status="unmeasurable", stable_f1_status="unverifiable",
        fpr_stable_status="unverifiable", fpr_current_status="ok",
        failed=("utility", "stable_f1"), n_gate_rows=0, gate_support=(0, 0, 0),
        n_gate_region_rows=0, n_gate_benign=0, n_s_gate_rows=10, s_gate_support=(5, 5, 0),
        n_s_gate_benign=5, n_stable_classes=2)


def test_decision_with_nan_serialises_to_strict_json_with_explicit_markers():
    d = Decision(False, "utility_unmeasurable", None, _nan_report()).as_dict()
    text = dumps_strict(d)
    assert "NaN" not in text and "Infinity" not in text
    parsed = loads_strict(text)                               # a strict parser accepts it
    rep = parsed["report"]
    assert rep["utility_gain_lcb"] == {NONFINITE_KEY: "nan"}  # explicit, not null and not a number
    assert rep["delta_fpr_current_ucb"] == 0.02              # finite values are untouched
    assert rep["utility_status"] == "unmeasurable" and rep["failed"] == ["utility", "stable_f1"]


def test_nan_is_never_converted_to_a_number_and_roundtrips():
    out = to_jsonable({"a": NAN, "b": float("inf"), "c": float("-inf"), "d": [NAN, 1.5]})
    for v in (out["a"], out["b"], out["c"], out["d"][0]):
        assert isinstance(v, dict) and not isinstance(v, (int, float))
    back = from_jsonable(loads_strict(dumps_strict({"a": NAN, "b": float("inf"),
                                                    "c": float("-inf")})))
    assert math.isnan(back["a"]) and back["b"] == math.inf and back["c"] == -math.inf


def test_default_json_dumps_would_have_emitted_non_strict_nan():
    """Why this module exists: the stdlib default writes the bare token NaN."""
    assert "NaN" in json.dumps({"x": NAN})
    with pytest.raises(ValueError):
        loads_strict('{"x": NaN}')
    with pytest.raises(ValueError):
        json.dumps({"x": NAN}, allow_nan=False)


def test_numpy_dataclass_and_container_types():
    @dataclass
    class Inner:
        arr: np.ndarray
        flag: np.bool_

    out = to_jsonable({"i": np.int64(3), "f": np.float32(0.5), "n": np.float64("nan"),
                       "inner": Inner(np.array([1, 2]), np.bool_(True)), "s": {3, 1},
                       "t": (1, 2), 7: "int key", np.int64(8): "np key"})
    assert out["i"] == 3 and out["f"] == 0.5 and out["n"] == {NONFINITE_KEY: "nan"}
    assert out["inner"] == {"arr": [1, 2], "flag": True}
    assert out["s"] == [1, 3] and out["t"] == [1, 2] and out["7"] == "int key"
    assert out["8"] == "np key"
    json.dumps(out, allow_nan=False)


def test_unknown_types_and_bad_keys_raise_instead_of_being_stringified():
    class Model:
        pass

    with pytest.raises(TypeError, match=r"\$\.model"):
        to_jsonable({"model": Model()})
    with pytest.raises(TypeError):
        to_jsonable({(1, 2): "tuple key"})
    with pytest.raises(TypeError):
        to_jsonable({1: "a", "1": "b"})                       # collide after str()
    with pytest.raises(TypeError):
        to_jsonable({NONFINITE_KEY: 1})                       # reserved


def test_key_order_is_preserved_so_validity_can_precede_h1(tmp_path):
    path = write_json(tmp_path / "x.json", {"zeta": 1, "validity": 2, "h1": 3, "alpha": 4})
    assert list(json.loads(path.read_text())) == ["zeta", "validity", "h1", "alpha"]
    assert not list(tmp_path.glob("*.tmp"))                   # atomic write left no temp file
