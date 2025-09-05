import numpy as np

from kvopt.plugins.kivi_plugin import KIVIPlugin


def test_kivi_quantize_dequantize_roundtrip_within_tolerance():
    # Prepare mock KV tensors
    kv = {
        "k": np.random.randn(4, 8).astype(np.float32),
        "v": np.random.randn(4, 8).astype(np.float32),
    }

    plugin = KIVIPlugin({"bitwidth": 4, "enabled": True})
    plugin.on_startup()

    q = plugin.quantize(kv, layer_idx=10, token_pos=10_000)
    assert isinstance(q, dict)
    assert (10, 10_000) in plugin.quantized_blocks

    deq = plugin.dequantize(q, layer_idx=10, token_pos=10_000)

    # Shapes preserved
    assert deq["k"].shape == kv["k"].shape
    assert deq["v"].shape == kv["v"].shape

    # Quantization is lossy; check average relative error is bounded
    def rel_err(a, b):
        denom = np.maximum(1e-6, np.abs(a) + np.abs(b))
        return np.mean(np.abs(a - b) / denom)

    err_k = rel_err(kv["k"], deq["k"])
    err_v = rel_err(kv["v"], deq["v"])

    # 4-bit demo quantization should keep error reasonably bounded
    assert err_k < 0.25
    assert err_v < 0.25
