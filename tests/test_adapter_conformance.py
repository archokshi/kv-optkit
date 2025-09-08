import os
import types
from typing import Dict, Any

import pytest

from kvopt.adapters import ADAPTER_REGISTRY


KNOWN_ACTIONS = {"EVICT", "OFFLOAD", "QUANTIZE", "REUSE"}


def _mk_config(adapter_name: str) -> Dict[str, Any]:
    # Provide minimal sane defaults used by multiple adapters
    return {
        "hbm_capacity_gb": 80.0,
        "bytes_per_token": 0.0001,
        "p95_latency_ms": 30.0,
    }


@pytest.mark.parametrize("adapter_name", sorted(ADAPTER_REGISTRY.keys()))
def test_adapter_basic_contract(adapter_name: str):
    adapter_cls = ADAPTER_REGISTRY[adapter_name]
    adapter = adapter_cls(_mk_config(adapter_name))

    # capabilities() must be a set and subset of KNOWN_ACTIONS
    caps = adapter.capabilities() or set()
    assert isinstance(caps, set)
    assert caps.issubset(KNOWN_ACTIONS)

    # get_sequences() must return a list
    seqs = adapter.get_sequences()
    assert isinstance(seqs, list)

    # get_telemetry() must return a dict with core keys or backfillable data
    telem = adapter.get_telemetry()
    assert isinstance(telem, dict)
    # Accept either 'hbm_total_gb' or legacy 'hbm_capacity_gb'
    total_key = "hbm_total_gb" if "hbm_total_gb" in telem else "hbm_capacity_gb"
    assert total_key in telem
    # Used key may not exist in SIM initially; treat missing as allowed but type-check if present
    if "hbm_used_gb" in telem:
        assert isinstance(telem["hbm_used_gb"], (int, float))
    # p95 may be provided; if present must be numeric
    if "p95_latency_ms" in telem:
        assert isinstance(telem["p95_latency_ms"], (int, float))

    # execute_action() must return a bool; unsupported actions should be False
    res = adapter.execute_action({
        "action_type": "UNSUPPORTED_TEST_ACTION",
        "sequence_id": "seq_test",
    })
    assert isinstance(res, bool)
    # Not strictly required to be False, but recommended; most adapters will return False.
