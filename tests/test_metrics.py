from fastapi.testclient import TestClient
from kvopt.server.main import app
from kvopt.server.metrics import update_from_telemetry
import threading
import time


def test_metrics_endpoint_basic():
    # Seed some metrics
    update_from_telemetry({
        "hbm_utilization": 0.82,
        "hbm_used_gb": 115.3,
        "p95_latency_ms": 1850,
        "tokens_evicted": 10,
        "tokens_quantized": 20,
        "reuse_hits": 2,
        "reuse_misses": 1,
        "applies": 1,
        "rollbacks": 0,
    })
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    # content type should be Prometheus exposition format
    ctype = r.headers.get("content-type", "")
    assert "text/plain" in ctype and "version=0.0.4" in ctype
    body = r.text
    # HELP/TYPE headers must exist for at least a couple of metrics
    assert "# HELP kvopt_hbm_utilization" in body
    assert "# TYPE kvopt_hbm_utilization gauge" in body
    assert "# TYPE kvopt_tokens_evicted_total counter" in body
    assert "kvopt_hbm_utilization" in body
    assert "kvopt_hbm_used_gb" in body
    assert "kvopt_p95_latency_ms" in body
    assert "kvopt_ttft_ms" in body
    assert "kvopt_ddr_utilization" in body
    assert "kvopt_ddr_used_gb" in body
    assert "kvopt_reuse_hits_total" in body


def test_metric_update_semantics_monotonic_and_guards():
    client = TestClient(app)
    # initial seed
    update_from_telemetry({
        "hbm_utilization": 0.0,
        "hbm_used_gb": 0.0,
        "p95_latency_ms": 1000,
        "ttft_ms": 500,
        "ddr_used_gb": 0.0,
        "tokens_evicted": 5,
        "tokens_quantized": 10,
    })
    r1 = client.get("/metrics")
    assert r1.status_code == 200
    text1 = r1.text
    # bump values
    update_from_telemetry({
        "hbm_utilization": 0.5,
        "hbm_used_gb": 10.0,
        "p95_latency_ms": 900,  # can go down
        "ttft_ms": 400,          # can go down
        "ddr_used_gb": 3.0,
        "tokens_evicted": 2,
        "tokens_quantized": 1,
    })
    r2 = client.get("/metrics")
    text2 = r2.text
    # Extract helper
    def get_metric(txt: str, name: str) -> float:
        for line in txt.splitlines():
            if line.startswith(name + " "):
                return float(line.split()[1])
        return float("nan")
    # Gauges reflect new values
    assert get_metric(text2, "kvopt_hbm_used_gb") >= get_metric(text1, "kvopt_hbm_used_gb")
    assert get_metric(text2, "kvopt_ddr_used_gb") >= get_metric(text1, "kvopt_ddr_used_gb")
    # Counters are monotonic
    assert get_metric(text2, "kvopt_tokens_evicted_total") >= get_metric(text1, "kvopt_tokens_evicted_total")
    assert get_metric(text2, "kvopt_tokens_quantized_total") >= get_metric(text1, "kvopt_tokens_quantized_total")


def test_metrics_concurrent_scrapes():
    client = TestClient(app)
    update_from_telemetry({"hbm_used_gb": 1.0})
    results = []
    errors = []

    def worker():
        try:
            r = client.get("/metrics")
            results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
    assert all(r.status_code == 200 for r in results)
    lengths = [len(r.text) for r in results]
    assert max(lengths) - min(lengths) < 1024  # allow small variance
