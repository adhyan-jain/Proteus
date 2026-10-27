"""Ground-truth per-flow log written AT THE TRAFFIC SOURCE (JSONL, one line per flow).

Every traffic generator, benign or attack, calls FlowLog.flow(...) around each flow it starts. Labels therefore never come
from IP heuristics. Time is time.time() (same clock as the loopback control-channel sniffer in run_benign.py).
Line schema: {"t0","t1","src_ip","dst_ip","proto","sport","dport","cls","family","run"}; cls is "benign" or "attack".
Attack tooling is chosen and run by the lab owner; this module only records what that tooling emitted.
"""
import json
import threading
import time


class FlowLog:
    def __init__(self, path, run):
        self.f, self.run, self.lock = open(path, "a", buffering=1), run, threading.Lock()

    def flow(self, src_ip, dst_ip, proto, dport, cls, family, sport=None):
        return _Flow(self, dict(src_ip=src_ip, dst_ip=dst_ip, proto=proto, sport=sport, dport=dport, cls=cls,
                                family=family, run=self.run))

    def _write(self, rec):
        with self.lock:
            self.f.write(json.dumps(rec) + "\n")


class _Flow:
    def __init__(self, log, rec):
        self.log, self.rec = log, rec

    def __enter__(self):
        self.rec["t0"] = time.time()
        return self

    def __exit__(self, *exc):
        self.rec["t1"] = time.time()
        self.log._write(self.rec)
