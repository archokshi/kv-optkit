#!/usr/bin/env python3
"""
CPU-only sidecar validation for KV-OptKit.

This script simulates a burst of sequences via the sidecar lifecycle endpoints,
then exercises Advisor and Autopilot. It is safe to run without a GPU.

Usage:
  python scripts/sidecar_validate.py --server http://localhost:9001 --seqs 5 --tokens 1024

You should see in QuickView:
- Sequences populated
- Advisor recommendations
- Guard + Last Apply banners after applying
"""
import argparse
import time
import uuid
import random
from typing import Dict, Any

import requests


def post(base: str, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{base}{path}", json=json, timeout=10)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


def get(base: str, path: str) -> Dict[str, Any]:
    r = requests.get(f"{base}{path}", timeout=10)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:9001", help="KV-OptKit server base URL")
    ap.add_argument("--seqs", type=int, default=5, help="Number of sequences to simulate")
    ap.add_argument("--tokens", type=int, default=1024, help="Initial tokens per sequence")
    ap.add_argument("--delta", type=int, default=128, help="Generated tokens per update")
    args = ap.parse_args()

    base = args.server.rstrip("/")

    # 1) Create sequences
    seq_ids = []
    for i in range(args.seqs):
        sid = f"req-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        seq_ids.append(sid)
        post(base, "/sequences/start", {"sequence_id": sid, "total_tokens": args.tokens})

    # 2) Update a few times
    rnd = random.Random(42)
    for _ in range(3):
        for sid in list(seq_ids):
            post(base, "/sequences/update", {"sequence_id": sid, "delta_tokens": rnd.randint(1, args.delta)})
        time.sleep(0.2)

    # 3) Finish half of them
    for sid in seq_ids[: len(seq_ids)//2]:
        post(base, "/sequences/finish", {"sequence_id": sid})

    # 4) Fetch telemetry and advisor report
    tel = get(base, "/telemetry")
    rep = get(base, "/advisor/report")

    # 5) Apply a plan (if advisor has recs) via Autopilot
    apply_resp = None
    try:
        apply_resp = post(base, "/autopilot/plan", {"allowed_actions": ["EVICT", "OFFLOAD", "QUANTIZE"], "dry_run": False})
    except Exception as e:
        apply_resp = {"error": str(e)}

    # 6) Guard + last apply status
    guard = get(base, "/guard/status")
    last = get(base, "/apply/last")

    print({
        "telemetry": {
            "hbm_used_gb": tel.get("hbm_used_gb"),
            "hbm_total_gb": tel.get("hbm_total_gb") or tel.get("hbm_capacity_gb"),
            "p95_latency_ms": tel.get("p95_latency_ms"),
            "total_sequences": tel.get("total_sequences") or len(rep.get("sequences", [])),
        },
        "advisor_recs": len(rep.get("recommendations", [])),
        "autopilot": apply_resp if isinstance(apply_resp, dict) else apply_resp,
        "guard": guard,
        "last_apply": last,
    })


if __name__ == "__main__":
    main()
