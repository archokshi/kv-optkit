"""
Additional targeted tests for LMCachePlugin.
Covers min_sequence_length gating and explicit hit/miss accounting using fakeredis.
"""
import pytest
import os

pytestmark = pytest.mark.skipif(os.getenv("KVOPT_LMCACHE", "0") != "1", reason="LMCache disabled (set KVOPT_LMCACHE=1 to enable tests)")

from kvopt.plugins.lmcache_plugin import LMCachePlugin


def test_min_sequence_length_gating_no_side_effects():
    plugin = LMCachePlugin({
        'backend': 'fakeredis://',
        'min_sequence_length': 5,
    })
    plugin.on_startup()

    try:
        seq_id = 'seq-1'
        short_tokens = [1, 2, 3, 4]  # len < min_sequence_length
        kv_data = {'mock': True}

        # Below min length: no cache access, no hit/miss increments
        assert plugin.check_cache(seq_id, short_tokens) is None
        plugin.update_cache(seq_id, short_tokens, kv_data)

        metrics = plugin.get_metrics()
        assert metrics['hits'] == 0
        assert metrics['misses'] == 0

        # At/above threshold should participate in cache
        ok_tokens = [1, 2, 3, 4, 5]
        assert plugin.check_cache(seq_id, ok_tokens) is None  # first miss increments misses
        plugin.update_cache(seq_id, ok_tokens, kv_data)
        cached = plugin.check_cache(seq_id, ok_tokens)
        assert cached is not None

        metrics = plugin.get_metrics()
        assert metrics['misses'] >= 1
        assert metrics['hits'] >= 1
    finally:
        plugin.on_shutdown()


def test_cache_by_content_with_different_sequence_ids():
    plugin = LMCachePlugin({
        'backend': 'fakeredis://',
        'min_sequence_length': 1,
    })
    plugin.on_startup()

    try:
        tokens = [9, 8, 7, 6]
        plugin.update_cache('seq-A', tokens, {'mock': True})
        # Different sequence id but same tokens should hit due to content-based keying
        cached = plugin.check_cache('seq-B', tokens)
        assert cached is not None
        assert cached.get('token_count') == len(tokens)
    finally:
        plugin.on_shutdown()
