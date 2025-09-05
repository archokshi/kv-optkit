"""
Prometheus metrics collector for KV-OptKit.
"""
from typing import Dict, Any
from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Use a module-level registry to simplify imports in tests and app
registry = CollectorRegistry()

# Gauges
hbm_utilization = Gauge(
    "kvopt_hbm_utilization",
    "HBM memory utilization (0-1)",
    registry=registry,
)
hbm_used_gb = Gauge(
    "kvopt_hbm_used_gb",
    "HBM memory used in GB",
    registry=registry,
)
p95_latency = Gauge(
    "kvopt_p95_latency_ms",
    "P95 latency in milliseconds",
    registry=registry,
)
ttft_ms = Gauge(
    "kvopt_ttft_ms",
    "Time to first token (milliseconds)",
    registry=registry,
)
ddr_utilization = Gauge(
    "kvopt_ddr_utilization",
    "DDR memory utilization (0-1)",
    registry=registry,
)
ddr_used_gb = Gauge(
    "kvopt_ddr_used_gb",
    "DDR memory used in GB",
    registry=registry,
)

# Counters
tokens_evicted = Counter(
    "kvopt_tokens_evicted_total",
    "Total tokens evicted",
    registry=registry,
)
tokens_quantized = Counter(
    "kvopt_tokens_quantized_total",
    "Total tokens quantized",
    registry=registry,
)
reuse_hits = Counter(
    "kvopt_reuse_hits_total",
    "Total reuse cache hits",
    registry=registry,
)
reuse_misses = Counter(
    "kvopt_reuse_misses_total",
    "Total reuse cache misses",
    registry=registry,
)
autopilot_applies = Counter(
    "kvopt_autopilot_applies_total",
    "Total Autopilot applies",
    registry=registry,
)
autopilot_rollbacks = Counter(
    "kvopt_autopilot_rollbacks_total",
    "Total Autopilot rollbacks",
    registry=registry,
)

# Example histogram for latency distribution (not heavily used in tests)
latency_hist = Histogram(
    "kvopt_latency_ms_hist",
    "Latency histogram in ms",
    buckets=(50, 100, 200, 500, 1000, 2000, 5000),
    registry=registry,
)


def update_from_telemetry(t: Dict[str, Any]) -> None:
    """Update metrics from adapter telemetry dict.
    Expected keys (optional): hbm_utilization (0-1), hbm_used_gb, p95_latency_ms,
    tokens_evicted, tokens_quantized, reuse_hits, reuse_misses, applies, rollbacks.
    """
    if t is None:
        return
    if "hbm_utilization" in t:
        hbm_utilization.set(float(t["hbm_utilization"]))
    if "hbm_used_gb" in t:
        hbm_used_gb.set(float(t["hbm_used_gb"]))
    if "p95_latency_ms" in t:
        p95_latency.set(float(t["p95_latency_ms"]))
        latency_hist.observe(float(t["p95_latency_ms"]))
    if "ttft_ms" in t:
        ttft_ms.set(float(t["ttft_ms"]))
    if "ddr_utilization" in t:
        ddr_utilization.set(float(t["ddr_utilization"]))
    if "ddr_used_gb" in t:
        ddr_used_gb.set(float(t["ddr_used_gb"]))
    if "tokens_evicted" in t:
        tokens_evicted.inc(float(t["tokens_evicted"]))
    if "tokens_quantized" in t:
        tokens_quantized.inc(float(t["tokens_quantized"]))
    if "reuse_hits" in t:
        reuse_hits.inc(float(t["reuse_hits"]))
    if "reuse_misses" in t:
        reuse_misses.inc(float(t["reuse_misses"]))
    if "applies" in t:
        autopilot_applies.inc(float(t["applies"]))
    if "rollbacks" in t:
        autopilot_rollbacks.inc(float(t["rollbacks"]))


def generate_metrics_response() -> (bytes, str):
    """Return (payload, content_type) for FastAPI Response."""
    return generate_latest(registry), CONTENT_TYPE_LATEST
