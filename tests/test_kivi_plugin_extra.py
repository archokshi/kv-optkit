"""
Additional targeted tests for KIVIPlugin.
Covers dequantize without prior quantize, sanity on shapes/types, and failure fallback.
"""
import numpy as np
import pytest

from kvopt.plugins.kivi_plugin import KIVIPlugin


@pytest.fixture
def sample_kv_data_small():
    return {
        'k': np.random.rand(2, 2, 4).astype(np.float32),
        'v': np.random.rand(2, 2, 4).astype(np.float32),
    }


def test_dequantize_without_prior_quantize_returns_original(sample_kv_data_small):
    plugin = KIVIPlugin({'min_tokens': 0})
    plugin.on_startup()
    try:
        # No quantization performed -> dequantize should just return input
        out = plugin.dequantize(sample_kv_data_small, layer_idx=0, token_pos=0)
        # Should be the same object or equal by reference/values
        assert out is sample_kv_data_small or (
            np.array_equal(out['k'], sample_kv_data_small['k']) and
            np.array_equal(out['v'], sample_kv_data_small['v'])
        )
    finally:
        plugin.on_shutdown()


def test_quantize_preserves_metadata_and_types(sample_kv_data_small):
    plugin = KIVIPlugin({'bitwidth': 3, 'min_tokens': 0})
    plugin.on_startup()
    try:
        q = plugin.quantize(sample_kv_data_small, layer_idx=1, token_pos=5)
        # Expect dict entries with data/scale/zero_point/shape/bitwidth
        for key in ('k', 'v'):
            assert isinstance(q[key], dict)
            assert 'data' in q[key]
            assert 'scale' in q[key]
            assert 'zero_point' in q[key]
            assert 'shape' in q[key] and tuple(q[key]['shape']) == sample_kv_data_small[key].shape
            assert 'bitwidth' in q[key] and int(q[key]['bitwidth']) == 3
        # Dequantized shape equals original
        dq = plugin.dequantize(q, layer_idx=1, token_pos=5)
        assert dq['k'].shape == sample_kv_data_small['k'].shape
        assert dq['v'].shape == sample_kv_data_small['v'].shape
    finally:
        plugin.on_shutdown()


def test_quantize_failure_fallback_returns_input(sample_kv_data_small, monkeypatch):
    plugin = KIVIPlugin({'min_tokens': 0})
    plugin.on_startup()

    # Force an exception inside quantize by monkeypatching numpy prod to raise
    import numpy as _np
    def boom(*args, **kwargs):
        raise RuntimeError('boom')

    try:
        monkeypatch.setattr(_np, 'prod', boom)
        out = plugin.quantize(sample_kv_data_small, layer_idx=0, token_pos=0)
        # Should return original input on failure
        assert out is sample_kv_data_small
    finally:
        plugin.on_shutdown()
