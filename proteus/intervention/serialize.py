"""Strict-JSON serialisation for intervention results (SPEC v1.1, P0 result files).

`Decision.as_dict()` and the metric reports legitimately contain NaN ("this quantity was not
measurable": no benign rows, no D_gate evidence, ...). Python's default `json.dumps` would emit the
bare token `NaN`, which is not JSON and which many parsers silently turn into a number. This module
never does that:

  * every output is produced with `allow_nan=False`, so a stray non-finite float can only reach the
    file through the explicit marker below;
  * a non-finite float becomes `{"__nonfinite__": "nan" | "inf" | "-inf"}` -- not `null`, not 0, not
    any sentinel number -- so "not measurable" stays distinguishable from "missing" and from every
    real value; `from_jsonable` restores the float;
  * unknown types raise `TypeError` instead of being stringified, so nothing is silently dropped or
    coerced.
"""
import json
import math
import os
from dataclasses import fields, is_dataclass
from pathlib import Path

import numpy as np

NONFINITE_KEY = "__nonfinite__"
_TOKENS = {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf")}


def _nonfinite_token(x):
    if math.isnan(x):
        return "nan"
    return "inf" if x > 0 else "-inf"


def to_jsonable(obj, _path="$"):
    """Convert `obj` into plain JSON types. Non-finite floats become explicit markers."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else {NONFINITE_KEY: _nonfinite_token(obj)}
    if isinstance(obj, np.generic):
        return to_jsonable(obj.item(), _path)
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist(), _path)
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name), f"{_path}.{f.name}")
                for f in fields(obj)}
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, np.generic):
                k = k.item()
            if not isinstance(k, (str, int)) or isinstance(k, bool):
                raise TypeError(f"{_path}: dict key {k!r} ({type(k).__name__}) is not str or int")
            key = str(k)
            if key == NONFINITE_KEY:
                raise TypeError(f"{_path}: dict key {NONFINITE_KEY!r} is reserved")
            if key in out:
                raise TypeError(f"{_path}: duplicate key {key!r} after str() conversion")
            out[key] = to_jsonable(v, f"{_path}.{key}")
        return out
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v, f"{_path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, (set, frozenset)):
        return [to_jsonable(v, _path) for v in sorted(obj)]
    raise TypeError(f"{_path}: cannot serialise {type(obj).__name__} (no silent str() fallback)")


def dumps_strict(obj, **kwargs):
    """Strict JSON text. Key order is preserved (callers rely on it to put validity before H1)."""
    kwargs.setdefault("indent", 1)
    return json.dumps(to_jsonable(obj), allow_nan=False, **kwargs)


def from_jsonable(obj):
    """Inverse of the non-finite marker: restores floats, leaves everything else as is."""
    if isinstance(obj, dict):
        if set(obj) == {NONFINITE_KEY}:
            return _TOKENS[obj[NONFINITE_KEY]]
        return {k: from_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_jsonable(v) for v in obj]
    return obj


def _refuse_constant(name):
    raise ValueError(f"non-strict JSON constant {name!r} in result file")


def loads_strict(text):
    """Parse JSON and refuse the non-standard NaN / Infinity tokens."""
    return json.loads(text, parse_constant=_refuse_constant)


def write_json(path, obj):
    """Atomic strict-JSON write (tmp file + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dumps_strict(obj)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return path
