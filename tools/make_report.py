import argparse
import os
from pathlib import Path
from typing import Optional, List, Dict
import requests
import pandas as pd
import matplotlib.pyplot as plt
import time

DEF_CHART_DIR = Path("outputs/charts")
# Backward-compatible alias used in plotting code
CHART_DIR = DEF_CHART_DIR
REPORT_PATH_DEFAULT = Path("outputs/run_report.md")


def _ensure_dirs():
    DEF_CHART_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH_DEFAULT.parent.mkdir(parents=True, exist_ok=True)


def _write_md(out_path: Path, content: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def _parse_prometheus_text(text: str) -> dict:
    metrics = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        try:
            k, v = line.split(None, 1)
            metrics[k] = float(v.strip())
        except Exception:
            continue
    return metrics


def _sample_live_metrics(base_url: str, samples: int, interval_s: float) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for i in range(max(1, samples)):
        resp = requests.get(f"{base_url}/metrics", timeout=5)
        resp.raise_for_status()
        m = _parse_prometheus_text(resp.text)
        rows.append({
            "hbm_gb": m.get("kvopt_hbm_used_gb", float("nan")),
            "p95_ms": m.get("kvopt_p95_latency_ms", float("nan")),
            "ttft_s": (m.get("kvopt_ttft_ms", float("nan")) / 1000.0) if m.get("kvopt_ttft_ms") is not None else float("nan"),
            "ddr_gb": m.get("kvopt_ddr_used_gb", float("nan")),
            # counters
            "evicted": m.get("kvopt_tokens_evicted_total", float("nan")),
            "quantized": m.get("kvopt_tokens_quantized_total", float("nan")),
            "reuse_hits": m.get("kvopt_reuse_hits_total", float("nan")),
            "reuse_misses": m.get("kvopt_reuse_misses_total", float("nan")),
            "applies": m.get("kvopt_autopilot_applies_total", float("nan")),
            "rollbacks": m.get("kvopt_autopilot_rollbacks_total", float("nan")),
        })
        if i < samples - 1:
            time.sleep(interval_s)
    return rows


def _summarize_before_after(df: pd.DataFrame):
    mid = len(df) // 2 if len(df) > 1 else 1
    before = df.iloc[:mid]
    after = df.iloc[mid:]
    summary = {
        "hbm_gb_before": before["hbm_gb"].mean() if "hbm_gb" in df else float("nan"),
        "hbm_gb_after": after["hbm_gb"].mean() if "hbm_gb" in df else float("nan"),
        "ddr_gb_before": before["ddr_gb"].mean() if "ddr_gb" in df else float("nan"),
        "ddr_gb_after": after["ddr_gb"].mean() if "ddr_gb" in df else float("nan"),
        "p95_before": before["p95_ms"].mean() if "p95_ms" in df else float("nan"),
        "p95_after": after["p95_ms"].mean() if "p95_ms" in df else float("nan"),
        "ttft_before": before["ttft_s"].mean() if "ttft_s" in df else float("nan"),
        "ttft_after": after["ttft_s"].mean() if "ttft_s" in df else float("nan"),
    }
    return summary


def _plots(df: pd.DataFrame):
    if "hbm_gb" in df:
        plt.figure(); df["hbm_gb"].plot(title="HBM (GB)"); plt.ylabel("GB"); plt.tight_layout(); plt.savefig(CHART_DIR/"hbm.png"); plt.close()
    if "p95_ms" in df:
        plt.figure(); df["p95_ms"].plot(title="P95 Latency (ms)"); plt.ylabel("ms"); plt.tight_layout(); plt.savefig(CHART_DIR/"latency.png"); plt.close()
    if "ttft_s" in df:
        plt.figure(); df["ttft_s"].hist(); plt.title("TTFT (s)"); plt.xlabel("s"); plt.tight_layout(); plt.savefig(CHART_DIR/"ttft.png"); plt.close()
    if "ddr_gb" in df:
        plt.figure(); df["ddr_gb"].plot(title="DDR (GB)"); plt.ylabel("GB"); plt.tight_layout(); plt.savefig(CHART_DIR/"ddr.png"); plt.close()


def generate_report(source: str, out: Path, csv_path: Optional[Path] = None, base_url: str = "http://localhost:8000", samples: int = 2, interval_s: float = 1.0) -> Path:
    _ensure_dirs()
    df = None
    if source == "file":
        if not csv_path:
            raise ValueError("--from file requires --csv path")
        df = pd.read_csv(csv_path)
    elif source == "live":
        rows = _sample_live_metrics(base_url, samples=samples, interval_s=interval_s)
        df = pd.DataFrame(rows)
    else:
        raise ValueError("source must be 'live' or 'file'")

    _plots(df)
    s = _summarize_before_after(df)

    # Counters delta table (if present)
    def _delta(col: str) -> float:
        return float(df[col].iloc[-1] - df[col].iloc[0]) if col in df and len(df[col]) >= 2 else float("nan")
    deltas = {
        "evicted": _delta("evicted"),
        "quantized": _delta("quantized"),
        "reuse_hits": _delta("reuse_hits"),
        "reuse_misses": _delta("reuse_misses"),
        "applies": _delta("applies"),
        "rollbacks": _delta("rollbacks"),
    }

    go = (s.get("p95_after", 1e9) <= 2000)
    md = f"""# KV-OptKit Run Report
## Summary
HBM before: {s['hbm_gb_before']:.2f} GB → after: {s['hbm_gb_after']:.2f} GB
DDR before: {s['ddr_gb_before']:.2f} GB → after: {s['ddr_gb_after']:.2f} GB
P95 latency: {s['p95_before']:.1f} ms → {s['p95_after']:.1f} ms
TTFT: {s['ttft_before']:.2f} s → {s['ttft_after']:.2f} s

## Go/No-Go
Result: {'PASS' if go else 'FAIL'} (threshold: P95 ≤ 2000 ms)

## Action Counters (Δ over window)
| Metric | Delta |
|---|---:|
| Tokens Evicted | {deltas['evicted']:.0f} |
| Tokens Quantized | {deltas['quantized']:.0f} |
| Reuse Hits | {deltas['reuse_hits']:.0f} |
| Reuse Misses | {deltas['reuse_misses']:.0f} |
| Autopilot Applies | {deltas['applies']:.0f} |
| Autopilot Rollbacks | {deltas['rollbacks']:.0f} |

## Charts
![HBM trend](charts/hbm.png)
![P95 latency](charts/latency.png)
![TTFT](charts/ttft.png)
![DDR trend](charts/ddr.png)
"""
    _write_md(out, md)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="source", choices=["live", "file"], required=True)
    parser.add_argument("--out", dest="out", default=str(REPORT_PATH_DEFAULT))
    parser.add_argument("--csv", dest="csv", default=None)
    parser.add_argument("--base", dest="base", default="http://localhost:8000", help="Base URL for live mode, default http://localhost:8000")
    parser.add_argument("--samples", dest="samples", type=int, default=6, help="Live mode: number of samples to collect (default 6)")
    parser.add_argument("--interval", dest="interval", type=float, default=5.0, help="Live mode: seconds between samples (default 5.0)")
    args = parser.parse_args()

    out_path = Path(args.out)
    csv_path = Path(args.csv) if args.csv else None
    generate_report(args.source, out_path, csv_path, base_url=args.base, samples=args.samples, interval_s=args.interval)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
