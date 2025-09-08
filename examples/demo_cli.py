#!/usr/bin/env python3
"""
KV-OptKit Demo CLI

A small CLI to interact with the simulator and advisor endpoints for local demos.

Usage examples:
  python examples/demo_cli.py reset
  python examples/demo_cli.py submit --seq seq_1 --tokens 2000
  python examples/demo_cli.py quantize --seq seq_1 --start 0 --end 999 --factor 0.5
  python examples/demo_cli.py offload --seq seq_2 --start 0 --end 799
  python examples/demo_cli.py evict --seq seq_2 --start 800 --end 1599
"""
import argparse
import json
import sys
from typing import Any, Dict

import requests

def get_parser():
    parser = argparse.ArgumentParser(description="KV-OptKit Demo CLI")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("reset").set_defaults(func=cmd_reset)

    p_sub = subparsers.add_parser("submit")
    p_sub.add_argument("--seq", required=True)
    p_sub.add_argument("--tokens", required=True, type=int)
    p_sub.set_defaults(func=cmd_submit)

    p_fin = subparsers.add_parser("finish")
    p_fin.add_argument("--seq", required=True)
    p_fin.set_defaults(func=cmd_finish)

    subparsers.add_parser("telemetry").set_defaults(func=cmd_telemetry)
    subparsers.add_parser("sequences").set_defaults(func=cmd_sequences)
    subparsers.add_parser("report").set_defaults(func=cmd_report)

    p_q = subparsers.add_parser("quantize")
    p_q.add_argument("--seq", required=True)
    p_q.add_argument("--start", required=True, type=int)
    p_q.add_argument("--end", required=True, type=int)
    p_q.add_argument("--factor", required=True, type=float)
    p_q.set_defaults(func=cmd_quantize)

    p_dq = subparsers.add_parser("dequantize")
    p_dq.add_argument("--seq", required=True)
    p_dq.add_argument("--start", required=True, type=int)
    p_dq.add_argument("--end", required=True, type=int)
    p_dq.set_defaults(func=cmd_dequantize)

    p_off = subparsers.add_parser("offload")
    p_off.add_argument("--seq", required=True)
    p_off.add_argument("--start", required=True, type=int)
    p_off.add_argument("--end", required=True, type=int)
    p_off.set_defaults(func=cmd_offload)

    p_evict = subparsers.add_parser("evict")
    p_evict.add_argument("--seq", required=True)
    p_evict.add_argument("--start", required=True, type=int)
    p_evict.add_argument("--end", required=True, type=int)
    p_evict.set_defaults(func=cmd_evict)

    return parser


def post(path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    r = requests.post(f"{BASE}{path}", json=payload or {})
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        print(r.text)
        return {}


def get(path: str) -> Dict[str, Any]:
    r = requests.get(f"{BASE}{path}")
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        print(r.text)
        return {}


def cmd_reset(_args: argparse.Namespace) -> None:
    post("/sim/reset")
    print("Simulator reset.")


def cmd_submit(args: argparse.Namespace) -> None:
    out = post("/sim/submit", {"seq_id": args.seq, "tokens": args.tokens})
    print(json.dumps(out, indent=2))


def cmd_finish(args: argparse.Namespace) -> None:
    r = requests.delete(f"{BASE}/sim/finish/{args.seq}")
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


def cmd_telemetry(_args: argparse.Namespace) -> None:
    out = get("/sim/telemetry")
    print(json.dumps(out, indent=2))


def cmd_sequences(_args: argparse.Namespace) -> None:
    out = get("/sim/sequences")
    print(json.dumps(out, indent=2))


def cmd_report(_args: argparse.Namespace) -> None:
    out = get("/advisor/report")
    print(json.dumps(out, indent=2))


def cmd_quantize(args: argparse.Namespace) -> None:
    out = post("/sim/quantize", {
        "seq_id": args.seq,
        "start_token": args.start,
        "end_token": args.end,
        "factor": args.factor,
    })
    print(json.dumps(out, indent=2))


def cmd_dequantize(args: argparse.Namespace) -> None:
    out = post("/sim/dequantize", {
        "seq_id": args.seq,
        "start_token": args.start,
        "end_token": args.end,
    })
    print(json.dumps(out, indent=2))


def cmd_offload(args: argparse.Namespace) -> None:
    out = post("/sim/offload", {
        "seq_id": args.seq,
        "start_token": args.start,
        "end_token": args.end,
    })
    print(json.dumps(out, indent=2))


def cmd_evict(args: argparse.Namespace) -> None:
    out = post("/sim/evict", {
        "seq_id": args.seq,
        "start_token": args.start,
        "end_token": args.end,
    })
    print(json.dumps(out, indent=2))


def main(argv: list[str]) -> int:
    import os
    parser = get_parser()
    args = parser.parse_args(argv)
    port = int(os.environ.get("KVOPT_PORT", 9001))
    global BASE
    BASE = f"http://localhost:{port}"

    try:
        args.func(args)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\nResponse: {getattr(e.response, 'text', '')}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
