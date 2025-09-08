import os
import time
from fastapi.testclient import TestClient

# Ensure adapter is vllm (CPU-safe) and demo sequences are off for this test
os.environ["KVOPT_ADAPTER"] = "vllm"
os.environ["KVOPT_DEMO_SEQS"] = "0"

from kvopt.server.main import app  # noqa: E402

def test_sidecar_sequence_lifecycle_and_advisor_apply():
    client = TestClient(app)

    # Start a sequence
    sid = f"req-{int(time.time()*1000)}"
    r = client.post("/sequences/start", json={"sequence_id": sid, "total_tokens": 512})
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # Update a few times
    for _ in range(3):
        r = client.post("/sequences/update", json={"sequence_id": sid, "delta_tokens": 64})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    # Advisor report should include sequences list (may be in report)
    r = client.get("/advisor/report")
    assert r.status_code == 200
    rep = r.json()
    assert isinstance(rep, dict)
    # Sequences may be embedded in report depending on pipeline; tolerate empty but ensure no error
    assert "recommendations" in rep

    # Apply a plan (non-dry-run) with required fields
    r = client.post("/autopilot/plan", json={
        "target_hbm_util": 0.75,
        "max_actions": 3,
        "priority": "medium",
        "allowed_actions": ["EVICT", "OFFLOAD", "QUANTIZE"],
        "dry_run": False
    })
    assert r.status_code == 200
    plan = r.json()
    assert isinstance(plan, dict)
    assert "plan_id" in plan

    # Finish the sequence
    r = client.post("/sequences/finish", json={"sequence_id": sid})
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # Guard status and last apply should be accessible
    r = client.get("/guard/status")
    assert r.status_code == 200
    r = client.get("/apply/last")
    assert r.status_code == 200
