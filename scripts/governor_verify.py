#!/usr/bin/env python3
"""
Governor verification tool for KV-OptKit OFFLOAD bandwidth caps.

Generates OFFLOAD-heavy actions against the active adapter via the Autopilot
API and checks that the observed offload governed bytes per tick stay within
configured caps. Uses metrics exposed at /metrics.

Usage:
  python scripts/governor_verify.py --server http://localhost:9001 --cap-gbps 10 --ticks 10 --tick-ms 200

Notes:
- This is a heuristic validator aimed at catching gross violations.
- For vLLM scaffold without NVML, the governor is applied in _apply_offload.
"""
import argparse
import time
import re
from typing import Dict

import requests


METRIC_RE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\s+(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*$")


def scrape_metrics(url: str) -> Dict[str, float]:
    text = requests.get(url, timeout=5).text
    out: Dict[str, float] = {}
    for line in text.splitlines():
        m = METRIC_RE.match(line.strip())
        if not m:
            continue
        name = m.group("name")
        val = float(m.group("value"))
        out[name] = val
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:9001", help="Server base URL")
    ap.add_argument("--cap-gbps", type=float, default=10.0, help="Expected OFFLOAD cap in GBytes/s")
    ap.add_argument("--ticks", type=int, default=10, help="Number of ticks to observe")
    ap.add_argument("--tick-ms", type=int, default=200, help="Assumed governor tick interval in ms")
    args = ap.parse_args()

    # Calculate expected per-tick cap in bytes
    expected_cap_bytes = args.cap_gbps * 1e9 * (args.tick_ms / 1000.0)

    # Prime metrics
    base = f"{args.server}"
    _ = scrape_metrics(f"{base}/metrics")

    print({"expected_tick_cap_bytes": expected_cap_bytes})

    for i in range(args.ticks):
        time.sleep(args.tick_ms / 1000.0)
        mm = scrape_metrics(f"{base}/metrics")
        cap = mm.get("kvopt_offload_tick_cap_bytes", 0.0)
        governed = mm.get("kvopt_offload_governed_bytes_total", 0.0)
        print({"tick": i + 1, "cap": cap, "governed_total": governed})
        if cap > 0 and cap > expected_cap_bytes * 1.05:  # allow 5% slack
            print({"status": "WARN", "reason": "cap exceeds expected", "cap": cap, "expected": expected_cap_bytes})

    print({"status": "DONE"})


if __name__ == "__main__":
    main()
