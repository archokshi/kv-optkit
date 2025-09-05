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
from kvopt.adapters.sim_adapter import SimAdapter
from kvopt.adapters.vllm_adapter import VLLMAdapter
from kvopt.policy_engine import PolicyEngine
from kvopt.agent import ActionExecutor, Guard
from kvopt.plugin_manager import PluginManager
from .metrics import update_from_telemetry, generate_metrics_response

# Import routers
from .routers import advisor, autopilot

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup initialization
    await startup_event()
    yield
    # Teardown (none for now)


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

# Global state
_config: Optional[Config] = None
_adapter: Optional[Any] = None
_policy_engine: Optional[PolicyEngine] = None
_action_executor: Optional[ActionExecutor] = None
_plugin_manager: Optional[PluginManager] = None
_guard: Optional[Guard] = None


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
        
        # Initialize plugin manager
        _plugin_manager = PluginManager(_config)
        _plugin_manager.initialize_plugins()
        logger.info("Plugin manager initialized")
        
        # Initialize advisor router with plugin manager and config
        advisor.init_advisor_router(_plugin_manager, _config)
        logger.info("Advisor router initialized")
        
        # Initialize adapter based on configuration
        if _config.adapter.type == "sim":
            _adapter = SimAdapter(_config.adapter.model_dump())
        elif _config.adapter.type == "vllm":
            _adapter = VLLMAdapter(_config.adapter.model_dump())
        else:
            raise ValueError(f"Unsupported adapter type: {_config.adapter.type}")
        
        logger.info(f"Initialized {_config.adapter.type} adapter")
        
        # Initialize policy engine
        _policy_engine = PolicyEngine(_config.policy)
        logger.info("Policy engine initialized")
        
        # Initialize action executor
        _action_executor = ActionExecutor(_adapter)
        logger.info("Action executor initialized")
        
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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "kvopt.server.main:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
        log_level="info"
    )


def run():
    """Console entrypoint: run the API server."""
    import uvicorn

    uvicorn.run(
        "kvopt.server.main:app",
        host="0.0.0.0",
        port=9000,
        log_level="info"
    )
