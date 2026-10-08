"""P0 on scenario S2 under the UNCHANGED section-L.1 rules (the P3 gate, SPEC v1.4).

    python -m proteus.intervention.p0_s2

`p0.run_p0` builds `P0Criteria()` internally and the frozen criteria name scenario S1, so a plain
`--scenario S2` run would be labelled "not preregistered". This wrapper swaps ONLY the criteria's
scenario field (budgets, seeds and every threshold stay the L.1 constants) for the duration of the
call and restores the original afterwards; `p0.py` itself is not modified.
"""
import proteus.config  # noqa: F401 -- must import before numpy/pandas/sklearn

import sys
from dataclasses import replace
from contextlib import contextmanager

import proteus.intervention.p0 as p0
from proteus.intervention.validity import P0Criteria


@contextmanager
def s2_criteria():
    original = p0.P0Criteria
    p0.P0Criteria = lambda: replace(original(), scenario="S2")
    try:
        yield
    finally:
        p0.P0Criteria = original


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    with s2_criteria():
        return p0.main(["--scenario", "S2", *argv])


if __name__ == "__main__":
    sys.exit(main())
