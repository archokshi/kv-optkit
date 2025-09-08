import pytest
import os

pytestmark = pytest.mark.skipif(os.getenv("KVOPT_LMCACHE", "0") != "1", reason="LMCache disabled for this release (set KVOPT_LMCACHE=1 to enable tests)")

from kvopt.plugins.lmcache_plugin import LMCachePlugin


def test_lmcache_miss_then_hit_with_fakeredis():
    plugin = LMCachePlugin({
        "backend": "fakeredis://",
        "enabled": True,
        "min_sequence_length": 1,
        "ttl": 10,
    })
    plugin.on_startup()

    seq = "s1"
    tokens = [1, 2, 3, 4]

    # First check: miss
    assert plugin.check_cache(seq, tokens) is None
    assert plugin.get_metrics()["misses"] == 1

    # Update and check: hit
    plugin.update_cache(seq, tokens, {"dummy": True})
    cached = plugin.check_cache(seq, tokens)
    assert isinstance(cached, dict)
    assert cached["sequence_id"] == seq
    assert cached["token_count"] == len(tokens)

    m = plugin.get_metrics()
    assert m["hits"] == 1
    assert m["misses"] == 1
