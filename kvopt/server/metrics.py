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

# Engine hook activity metrics
engine_alloc_bytes = Counter(
    "kvopt_engine_alloc_bytes_total",
    "Total bytes reported allocated by engine hooks",
    registry=registry,
)
engine_free_bytes = Counter(
    "kvopt_engine_free_bytes_total",
    "Total bytes reported freed by engine hooks",
    registry=registry,
)
engine_page_moves = Counter(
    "kvopt_engine_page_moves_total",
    "Total number of page/block move events reported by engine hooks",
    registry=registry,
)
engine_page_moved_bytes = Counter(
    "kvopt_engine_page_moved_bytes_total",
    "Total bytes moved across tiers as reported by engine hooks",
    registry=registry,
)

# Governor throttle events
governor_throttle_events = Counter(
    "kvopt_governor_throttle_events_total",
    "Total number of times the OFFLOAD governor reduced a requested transfer",
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

# Apply outcome counters
apply_success = Counter(
    "kvopt_apply_success_total",
    "Total successful plan applies",
    registry=registry,
)
apply_fail = Counter(
    "kvopt_apply_fail_total",
    "Total failed plan applies",
    registry=registry,
)

# Governor metrics
offload_governed_bytes = Counter(
    "kvopt_offload_governed_bytes_total",
    "Total bytes governed (capped) by the OFFLOAD bandwidth governor",
    registry=registry,
)
offload_tick_cap_bytes = Gauge(
    "kvopt_offload_tick_cap_bytes",
    "Per-tick OFFLOAD byte cap enforced by the governor",
    registry=registry,
)

# Example histogram for latency distribution (not heavily used in tests)
latency_hist = Histogram(
    "kvopt_latency_ms_hist",
    "Latency histogram in ms",
    buckets=(50, 100, 200, 500, 1000, 2000, 5000),
    registry=registry,
)

# Ensure key observability metrics are present in exports even before telemetry updates
# Some Prometheus clients only emit samples after first set/inc; touch them with zero.
try:
    governor_throttle_events.inc(0.0)
    offload_governed_bytes.inc(0.0)
    offload_tick_cap_bytes.set(0.0)
except Exception:
    # Best effort; if client internals change, avoid breaking imports
    pass


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
    # Governor keys (optional)
    if "offload_governed_bytes" in t:
        offload_governed_bytes.inc(float(t["offload_governed_bytes"]))
    if "offload_tick_cap_bytes" in t:
        offload_tick_cap_bytes.set(float(t["offload_tick_cap_bytes"]))


def generate_metrics_response() -> (bytes, str):
    """Return (payload, content_type) for FastAPI Response."""
    return generate_latest(registry), CONTENT_TYPE_LATEST


def _read_counter(c) -> float:
    try:
        # prometheus_client stores value in _value; guard access
        return float(c._value.get())  # type: ignore[attr-defined]
    except Exception:
        try:
            return float(c._value.get())
        except Exception:
            return 0.0


def _read_gauge(g) -> float:
    try:
        return float(g._value.get())  # type: ignore[attr-defined]
    except Exception:
        return 0.0


def snapshot_engine_activity() -> dict:
    """Return a JSON-friendly snapshot of engine hook and governor metrics."""
    return {
        "engine_alloc_bytes_total": _read_counter(engine_alloc_bytes),
        "engine_free_bytes_total": _read_counter(engine_free_bytes),
        "engine_page_moves_total": _read_counter(engine_page_moves),
        "engine_page_moved_bytes_total": _read_counter(engine_page_moved_bytes),
        "governor_throttle_events_total": _read_counter(governor_throttle_events),
        "offload_governed_bytes_total": _read_counter(offload_governed_bytes),
        "offload_tick_cap_bytes": _read_gauge(offload_tick_cap_bytes),
    }
