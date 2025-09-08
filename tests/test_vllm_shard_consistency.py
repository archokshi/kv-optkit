import math

from kvopt.adapters.vllm_adapter import VLLMAdapter


def _approx(a: float, b: float, rel: float = 1e-3) -> bool:
    denom = max(1.0, abs(a), abs(b))
    return abs(a - b) <= rel * denom


def test_plan_all_or_nothing_rollback_on_failure_multi_shard():
    cfg = {
        "bytes_per_token": 1e-6,          # GB per token (~1 KB)
        "offload_bw_gbps": 1e-3,         # cap to ensure governor logic runs
        "governor_tick_ms": 1000.0,      # 1 second window
        "hbm_used_gb": 7.5,
        "hbm_capacity_gb": 80.0,
    }
    ad = VLLMAdapter(cfg)

    # Two actions across hypothetical shard groups; second fails
    plan = {
        "actions": [
            {"action_type": "OFFLOAD", "sequence_id": "sA", "start_token": 0, "end_token": 50_000, "shard_group": "g0"},
            {"action_type": "UNKNOWN",  "sequence_id": "sB", "start_token": 0, "end_token": 10,     "shard_group": "g1"},
        ]
    }
    before = ad._est_hbm_used_gb
    ok, err = ad.apply_plan(plan, shadow_mode=False)
    assert ok is False
    assert isinstance(err, str) and err
    after = ad._est_hbm_used_gb

    # Entire plan must roll back to the pre-state (plan-level all-or-nothing)
    assert _approx(after, before, rel=1e-6)


def test_plan_success_multi_actions_no_rollback():
    # Make governor effectively non-limiting so savings add linearly
    cfg = {
        "bytes_per_token": 1e-6,
        "offload_bw_gbps": 1000.0,       # very high cap
        "governor_tick_ms": 1000.0,
        "hbm_used_gb": 10.0,
        "hbm_capacity_gb": 80.0,
    }
    ad = VLLMAdapter(cfg)

    actions = [
        {"action_type": "OFFLOAD", "sequence_id": "s1", "start_token": 0,     "end_token": 10_000},  # 0.01 GB
        {"action_type": "OFFLOAD", "sequence_id": "s2", "start_token": 0,     "end_token": 20_000},  # 0.02 GB
    ]
    before = ad._est_hbm_used_gb
    ok, err = ad.apply_plan({"actions": actions}, shadow_mode=False)
    assert ok is True
    assert err is None
    after = ad._est_hbm_used_gb

    expected_savings = 0.01 + 0.02  # GB
    assert after < before
    assert _approx(before - after, expected_savings, rel=5e-3)
