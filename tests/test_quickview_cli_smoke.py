import os
from unittest import mock

from fastapi.testclient import TestClient


def test_quickview_and_endpoints_load():
    # Ensure SIM adapter for deterministic test
    os.environ["KVOPT_ADAPTER"] = "sim"
    os.environ["KVOPT_PORT"] = "9001"

    # Import app after env is set so lifespan uses these values
    from kvopt.server.main import app

    with TestClient(app) as client:
        # QuickView page should load
        r = client.get("/")
        assert r.status_code == 200
        assert "KV-OptKit QuickView" in r.text

        # Telemetry should be available
        rt = client.get("/telemetry")
        assert rt.status_code == 200
        assert isinstance(rt.json(), dict)

        # Advisor report should be available and well-formed
        rr = client.get("/advisor/report")
        assert rr.status_code == 200
        data = rr.json()
        assert "hbm_utilization" in data
        assert "recommendations" in data
        assert "sequences" in data


def test_cli_autopilot_smoke():
    # Patch subprocess.call so we don't actually run PowerShell in tests
    with mock.patch("subprocess.call", return_value=0) as sp_call:
        from kvopt import cli
        rc = cli.autopilot([])
        assert rc == 0
        sp_call.assert_called()


def test_cli_module_loads():
    # Basic import smoke and function presence
    from kvopt import cli

    assert callable(cli.serve)
    assert callable(cli.quickstart)
    assert callable(cli.autopilot)
    assert callable(cli.sidecar)
