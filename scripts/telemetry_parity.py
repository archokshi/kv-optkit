#!/usr/bin/env python3
"""
Telemetry parity checker for KV-OptKit.

Compares adapter-reported telemetry at /telemetry with NVML (if available) and
reports whether the difference is within a specified tolerance (default 5%).

Usage:
  python scripts/telemetry_parity.py --server http://localhost:9001 --device 0 --tolerance 0.05
"""
import argparse
import sys
import math
import time
from typing import Optional

import requests

try:
    import pynvml  # type: ignore
except Exception:
    pynvml = None  # type: ignore

# Optional ROCm SMI
try:
    import rocm_smi_lib as rsmi  # type: ignore
except Exception:
    rsmi = None  # type: ignore

# Optional torch CUDA
try:
    import torch  # type: ignore
except Exception:
    torch = None  # type: ignore


def get_nvml_mem_gb(device_index: int) -> Optional[tuple[float, float]]:
    if pynvml is None:
        return None
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_gb = float(mem.total) / (1024**3)
        used_gb = float(mem.used) / (1024**3)
        return used_gb, total_gb
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def get_rocm_mem_gb(device_index: int) -> Optional[tuple[float, float]]:
    if rsmi is None:
        return None
    try:
        rsmi.rsmi_init(0)
        try:
            dv = int(device_index)
            used = rsmi.rsmi_dev_memory_usage_get(dv, rsmi.RSMI_MEM_TYPE_VRAM)
            total = rsmi.rsmi_dev_memory_total_get(dv, rsmi.RSMI_MEM_TYPE_VRAM)
            total_gb = float(total) / (1024**3)
            used_gb = float(used) / (1024**3)
            return used_gb, total_gb
        finally:
            try:
                rsmi.rsmi_shut_down()
            except Exception:
                pass
    except Exception:
        return None


def get_torch_cuda_mem_gb() -> Optional[tuple[float, float]]:
    if torch is None:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        free_b, total_b = torch.cuda.mem_get_info()  # type: ignore[attr-defined]
        total_gb = float(total_b) / (1024**3)
        used_gb = float(total_b - free_b) / (1024**3)
        return used_gb, total_gb
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:9001", help="Server base URL")
    ap.add_argument("--device", type=int, default=0, help="GPU device index for NVML")
    ap.add_argument("--tolerance", type=float, default=0.05, help="Allowed relative delta (e.g., 0.05 for 5%)")
    args = ap.parse_args()

    # Fetch telemetry
    t = requests.get(f"{args.server}/telemetry", timeout=5).json()
    used = float(t.get("hbm_used_gb") or 0.0)
    total = float(t.get("hbm_total_gb") or t.get("hbm_capacity_gb") or 0.0)
    if total <= 0:
        print("ERROR: Telemetry did not report total HBM.")
        sys.exit(2)

    # Try NVML, then ROCm SMI, then torch CUDA
    nv = get_nvml_mem_gb(args.device)
    ro = None if nv is not None else get_rocm_mem_gb(args.device)
    tc = None if (nv is not None or ro is not None) else get_torch_cuda_mem_gb()
    if nv is None and ro is None and tc is None:
        print("WARN: No vendor telemetry source available (NVML/ROCm/torch). Telemetry sample:")
        print({"hbm_used_gb": used, "hbm_total_gb": total})
        sys.exit(0)

    ref_used, ref_total = (nv or ro or tc)
    # Compare used and total separately
    def rel_delta(a: float, b: float) -> float:
        denom = max(1e-9, max(abs(a), abs(b)))
        return abs(a - b) / denom

    du = rel_delta(used, ref_used)
    dt = rel_delta(total, ref_total)

    ok = du <= args.tolerance and dt <= args.tolerance
    status = "PASS" if ok else "FAIL"
    print(
        {
            "status": status,
            "tolerance": args.tolerance,
            "telemetry": {"used_gb": used, "total_gb": total},
            "reference": {"used_gb": ref_used, "total_gb": ref_total, "source": "nvml" if nv else ("rocm" if ro else "torch_cuda")},
            "delta": {"used": du, "total": dt},
        }
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
