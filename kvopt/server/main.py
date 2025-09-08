"""
KV-OptKit Server

This module implements the FastAPI-based HTTP server for KV-OptKit.
"""
import os
import logging
from fastapi import FastAPI, Depends, HTTPException, status, Response
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from kvopt.config import Config
from kvopt import __version__
from kvopt.adapters import create_adapter
from kvopt.policy_engine import PolicyEngine
from kvopt.agent import ActionExecutor, Guard
from kvopt.plugin_manager import PluginManager
from .metrics import update_from_telemetry, generate_metrics_response, snapshot_engine_activity

# Import routers
from .routers import advisor, autopilot, sim, sequences
from .routers import quickview
from .routers import dev_hooks as dev_hooks_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup initialization
    try:
        await startup_event()
        yield
        # Teardown (none for now)
    except Exception as e:
        logger.error(f"Error during startup: {e}")

app = FastAPI(
    title="KV-OptKit API",
    description="API for KV cache optimization in large language models",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(advisor.router)
app.include_router(autopilot.router)  # Add Autopilot router
app.include_router(sim.router)  # Add Simulator router for demo endpoints
app.include_router(quickview.router)  # Add QuickView at '/'
app.include_router(sequences.router)  # Sidecar sequence lifecycle endpoints
if os.getenv("KVOPT_DEV", "0").lower() in ("1", "true", "yes"):
    app.include_router(dev_hooks_router.router)  # Development-only hooks

# Global state
_config: Optional[Config] = None
_adapter: Optional[Any] = None
_policy_engine: Optional[PolicyEngine] = None
_action_executor: Optional[ActionExecutor] = None
_plugin_manager: Optional[PluginManager] = None
_guard: Optional[Guard] = None
_last_apply: Optional[Dict[str, Any]] = None
_allow_apply: bool = True


@app.get("/adapter/info")
def get_adapter_info() -> Dict[str, Any]:
    """Return adapter type and capability list for UI and debugging."""
    try:
        name = _config.adapter.type if _config and _config.adapter else "unknown"
        caps = sorted(list((_adapter.capabilities() if _adapter else set()) or []))
        return {"name": name, "capabilities": caps}
    except Exception:
        return {"name": "unknown", "capabilities": []}


@app.get("/server/status")
def get_server_status() -> Dict[str, Any]:
    """Return high-level runtime status for QuickView header."""
    try:
        name = _config.adapter.type if _config and _config.adapter else "unknown"
        caps = sorted(list((_adapter.capabilities() if _adapter else set()) or []))
        mode = name
        # Demo sequences flag (for vLLM adapter)
        demo = False
        try:
            demo = bool(getattr(_adapter, "config", {}).get("demo_generate_sequences", False))
        except Exception:
            demo = False
        # Sequence count if adapter exposes get_sequences
        seq_count = 0
        try:
            if _adapter and hasattr(_adapter, "get_sequences"):
                seq_count = len(_adapter.get_sequences() or [])
        except Exception:
            seq_count = 0
        return {
            "adapter": name,
            "capabilities": caps,
            "mode": mode,
            "demo_sequences": demo,
            "sequence_count": seq_count,
            "allow_apply": bool(_allow_apply),
        }
    except Exception:
        return {"adapter": "unknown", "capabilities": [], "mode": "unknown", "demo_sequences": False, "sequence_count": 0, "allow_apply": False}


@app.post("/server/allow_apply")
def set_allow_apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle global allow_apply flag for Autopilot execute."""
    global _allow_apply
    try:
        allow = bool(payload.get("allow"))
        _allow_apply = allow
        return {"ok": True, "allow_apply": _allow_apply}
    except Exception as e:
        return {"ok": False, "error": str(e), "allow_apply": _allow_apply}

@app.get("/guard/status")
def get_guard_status() -> Dict[str, Any]:
    """Return guard aggregated metrics and paused flag (if available)."""
    try:
        metrics = _guard.get_metrics_summary() if _guard else {"total_plans": 0}
        # For now, paused is inferred from a placeholder flag; default False
        return {"paused": False, "metrics": metrics}
    except Exception:
        return {"paused": False, "metrics": {}}


@app.get("/apply/last")
def get_last_apply() -> Dict[str, Any]:
    return _last_apply or {}

class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    adapter: str


def get_config() -> Config:
    """Get the current configuration."""
    if _config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration not initialized"
        )
    return _config


def get_adapter() -> Any:
    """Get the current adapter instance."""
    if _adapter is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Adapter not initialized"
        )
    return _adapter


def get_policy_engine() -> PolicyEngine:
    """Get the policy engine instance."""
    if _policy_engine is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Policy engine not initialized"
        )
    return _policy_engine


def get_plugin_manager() -> PluginManager:
    """Get the plugin manager instance."""
    if _plugin_manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Plugin manager not initialized"
        )
    return _plugin_manager


def get_action_executor() -> ActionExecutor:
    """Get the action executor instance."""
    if _action_executor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Action executor not initialized"
        )
    return _action_executor


def get_guard() -> Guard:
    """Get the guard instance."""
    if _guard is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Guard not initialized"
        )
    return _guard


# Add dependencies to FastAPI's dependency injection system
app.dependency_overrides[Config] = get_config
app.dependency_overrides[Any] = get_adapter  # For Adapter type
app.dependency_overrides[PluginManager] = get_plugin_manager
app.dependency_overrides[PolicyEngine] = get_policy_engine
app.dependency_overrides[ActionExecutor] = get_action_executor
app.dependency_overrides[Guard] = get_guard  # Add Guard dependency


async def startup_event():
    """Initialize the application on startup."""
    global _config, _adapter, _policy_engine, _action_executor, _plugin_manager, _guard
    
    try:
        # Load configuration
        config_path = os.getenv("KVOPT_CONFIG", "config/config.yaml")
        _config = Config.from_yaml(config_path)
        # Optional override: adapter type via env for zero-friction switching
        if os.getenv("KVOPT_ADAPTER"):
            try:
                _config.adapter.type = os.getenv("KVOPT_ADAPTER").lower()
                logger.info(f"Overriding adapter.type via KVOPT_ADAPTER={_config.adapter.type}")
            except Exception:
                logger.warning("KVOPT_ADAPTER set but could not override adapter.type; using config file value")
        
        # Initialize plugin manager
        _plugin_manager = PluginManager(_config)
        _plugin_manager.initialize_plugins()
        logger.info("Plugin manager initialized")
        
        # Initialize advisor router with plugin manager and config
        advisor.init_advisor_router(_plugin_manager, _config)
        logger.info("Advisor router initialized")
        
        # Initialize adapter based on configuration
        adapter_cfg = _config.adapter.model_dump()
        # Optional demo sequences for vLLM adapter to visualize sequences without engine hooks
        try:
            if os.getenv("KVOPT_DEMO_SEQS", "0").lower() in ("1", "true", "yes"):
                adapter_cfg["demo_generate_sequences"] = True
        except Exception:
            pass
        atype = _config.adapter.type
        _adapter = create_adapter(atype, adapter_cfg)
        
        logger.info(f"Initialized {_config.adapter.type} adapter with capabilities: {sorted(list(_adapter.capabilities() or []))}")
        
        # Initialize policy engine
        _policy_engine = PolicyEngine(_config.policy)
        logger.info("Policy engine initialized")
        
        # Initialize action executor
        _action_executor = ActionExecutor(_adapter)
        logger.info("Action executor initialized")

        # Apply global allow_apply from env (KVOPT_ALLOW_APPLY), default true
        try:
            val = os.getenv("KVOPT_ALLOW_APPLY", "1").lower()
            globals()["_allow_apply"] = (val in ("1", "true", "yes"))
        except Exception:
            pass
        
        # Initialize guard
        _guard = Guard()
        
        logger.info("KV-OptKit server initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize KV-OptKit server: {e}")
        raise


@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify server is working."""
    return {"message": "Server is working!"}

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": __version__,
        "adapter": _adapter.__class__.__name__ if _adapter else "none"
    }


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    """Kubernetes-style health endpoint (alias of /health)."""
    return await health_check()


@app.get("/telemetry")
async def get_telemetry(adapter: Any = Depends(get_adapter)):
    """Get current telemetry data from the adapter."""
    return adapter.get_telemetry()


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.
    Updates metrics from current telemetry (best effort) before exporting.
    """
    try:
        if _adapter is not None:
            telemetry = _adapter.get_telemetry()
            update_from_telemetry(telemetry)
    except Exception:
        # Best-effort update; continue to export whatever is present
        pass
    payload, content_type = generate_metrics_response()
    return Response(content=payload, media_type=content_type)


@app.get("/metrics/snapshot")
async def metrics_snapshot():
    """JSON snapshot of selected metrics for QuickView."""
    try:
        if _adapter is not None:
            telemetry = _adapter.get_telemetry()
            update_from_telemetry(telemetry)
    except Exception:
        pass
    return snapshot_engine_activity()


@app.get("/debug/routes")
async def list_routes():
    """Temporary diagnostic endpoint: list all registered routes."""
    try:
        return sorted([getattr(r, 'path', str(r)) for r in app.routes])
    except Exception as e:
        return {"error": str(e)}




def run():
    """Console entrypoint: run the API server."""
    import uvicorn
    import os

    port = int(os.environ.get("KVOPT_PORT", 9000))

    uvicorn.run(
        "kvopt.server.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    run()
