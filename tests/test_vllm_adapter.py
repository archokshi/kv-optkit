import math

from kvopt.adapters.vllm_adapter import VLLMAdapter


def _approx(a: float, b: float, rel: float = 1e-3) -> bool:
    denom = max(1.0, abs(a), abs(b))
    return abs(a - b) <= rel * denom


def test_offload_bandwidth_governor_limits_span():
    # Configure small bytes/token and very small bandwidth to force limiting
    cfg = {
        "bytes_per_token": 1e-6,          # GB per token (~1 KB)
        "offload_bw_gbps": 1e-3,         # 0.001 GB/s (~1 MB/s)
        "governor_tick_ms": 1000.0,      # 1 second window
        "hbm_used_gb": 10.0,
        "hbm_capacity_gb": 80.0,
    }
    ad = VLLMAdapter(cfg)

    # Large token span should be capped by the governor
    start, end = 0, 100_000
    before = ad._est_hbm_used_gb
    ok = ad.execute_action({
        "action_type": "OFFLOAD",
        "sequence_id": "s1",
        "start_token": start,
        "end_token": end,
    })
    assert ok is True
    after = ad._est_hbm_used_gb

    # Compute expected cap: max_bytes = bw * tick
    # tokens_per_tick = max_bytes / bpt_bytes
    bpt_gb = float(cfg["bytes_per_token"])               # GB per token
    bpt_bytes = bpt_gb * (1024 ** 3)
    max_bytes = float(cfg["offload_bw_gbps"]) * 1e9 * (cfg["governor_tick_ms"] / 1000.0)
    max_tokens_this_tick = int(max_bytes / bpt_bytes) if bpt_bytes > 0 else 0
    limited_tokens = min(end - start, max_tokens_this_tick)
    expected_savings_gb = limited_tokens * bpt_gb

    assert after <= before  # usage should drop or stay same
    assert _approx(before - after, expected_savings_gb, rel=5e-3)


def test_apply_plan_rollback_on_failure():
    cfg = {
        "bytes_per_token": 1e-6,
        "offload_bw_gbps": 1e-3,
        "governor_tick_ms": 1000.0,
        "hbm_used_gb": 5.0,
        "hbm_capacity_gb": 80.0,
    }
    ad = VLLMAdapter(cfg)

    # First action should reduce, second is invalid -> triggers rollback
    plan = {
        "actions": [
            {"action_type": "OFFLOAD", "sequence_id": "s1", "start_token": 0, "end_token": 10_000},
            {"action_type": "UNKNOWN",  "sequence_id": "s1", "start_token": 0, "end_token": 10},
        ]
    }
    before = ad._est_hbm_used_gb
    ok, err = ad.apply_plan(plan, shadow_mode=False)
    assert ok is False
    assert isinstance(err, str) and err
    after = ad._est_hbm_used_gb

    # After rollback, usage should be (approximately) restored
    assert _approx(after, before, rel=1e-6)
