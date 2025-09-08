"""
Advisor Router

This module provides API endpoints for getting optimization recommendations
based on the current system state and plugin metrics.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import logging

from kvopt.config import (
    AdvisorReport,
    Recommendation,
    Config,
)
from kvopt.plugin_manager import PluginManager

router = APIRouter(prefix="/advisor", tags=["advisor"])
logger = logging.getLogger(__name__)

# Global state for plugin manager and config
plugin_manager: Optional[PluginManager] = None
config: Optional[Config] = None

def init_advisor_router(plugin_mgr: PluginManager, cfg: Config):
    """Initialize the advisor router with plugin manager and config."""
    global plugin_manager, config
    plugin_manager = plugin_mgr
    config = cfg
    logger.info("Advisor router initialized with plugin manager and config")

@router.get("/report", response_model=AdvisorReport)
async def get_advisor_report() -> Dict[str, Any]:
    """
    Get optimization recommendations and system status.
    
    Returns:
        AdvisorReport: Current system status and optimization recommendations
    """
    if not plugin_manager or not config:
        raise HTTPException(status_code=503, detail="Advisor not initialized")

    try:
        # Initialize all data structures at the top of the try block
        plugin_metrics: Dict[str, Any] = {}
        system_metrics: Dict[str, Any] = {}
        sequences_list: List[dict] = []

        # Get metrics from all plugins
        for plugin in plugin_manager:
            try:
                metrics = getattr(plugin, 'get_metrics', lambda: None)()
                plugin_id = getattr(plugin, 'plugin_id', plugin.__class__.__name__)
                if metrics:
                    plugin_metrics[plugin_id] = metrics
            except Exception as e:
                logger.warning(f"Failed to get metrics from plugin {getattr(plugin, 'plugin_id', 'unknown')}: {e}")

        # Get live telemetry from the adapter
        try:
            from kvopt.server.main import _adapter
            if _adapter is not None and hasattr(_adapter, "get_telemetry"):
                system_metrics = _adapter.get_telemetry() or {}
            else:
                system_metrics = get_system_metrics()
        except Exception:
            system_metrics = get_system_metrics()

        # Derive or backfill required fields for response model compatibility
        try:
            if "hbm_utilization" not in system_metrics:
                used = float(system_metrics.get("hbm_used_gb", 0.0) or 0.0)
                total = float(system_metrics.get("hbm_total_gb", 0.0) or 0.0)
                system_metrics["hbm_utilization"] = (used / total) if total > 0 else 0.0
            if "p95_latency_ms" not in system_metrics:
                system_metrics["p95_latency_ms"] = 0.0
        except Exception:
            # Never fail the endpoint on derivation errors; defaults already handle safety
            system_metrics.setdefault("hbm_utilization", 0.0)
            system_metrics.setdefault("p95_latency_ms", 0.0)

        # Get sequence snapshot
        try:
            from kvopt.server.main import _adapter
            if _adapter is not None:
                seqs = getattr(_adapter, "get_sequences", lambda: [])()
                for s in seqs or []:
                    seq_id = s.get("sequence_id") or s.get("seq_id") or s.get("id")
                    length_tokens = s.get("total_tokens") or s.get("length_tokens") or 0
                    sequences_list.append({
                        "seq_id": str(seq_id) if seq_id is not None else "unknown",
                        "length_tokens": int(length_tokens),
                    })
        except Exception as e:
            logger.debug(f"Unable to include sequences snapshot: {e}")

        # Generate recommendations
        raw_recommendations = generate_recommendations(plugin_metrics, system_metrics, sequences_list)

        # Map recommendations to the expected schema
        recommendations: List[Dict[str, Any]] = []
        for rec in raw_recommendations or []:
            recommendations.append({
                "action": rec.get("type", "unknown"),
                "detail": rec.get("message", rec.get("details", "")),
                "estimated_hbm_savings_gb": float(rec.get("estimated_hbm_savings_gb", 0.0)),
                "risk": rec.get("severity", "low"),
                # Preserve structured details for UIs (e.g., target_sequence, ranges)
                "details": rec.get("details", {}),
            })

        # Combine into the final report
        report = {
            **system_metrics,
            "sequences": sequences_list,
            "recommendations": recommendations,
            "plugin_metrics": plugin_metrics,
            "notes": [],
        }

        return report

    except Exception as e:
        logger.error(f"Error generating advisor report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating advisor report: {e}")

from pydantic import BaseModel

class ApplyRequest(BaseModel):
    target_hbm_util: float | None = 0.7
    max_actions: int | None = 3
    dry_run: bool | None = False
    allowed_actions: List[str] | None = None

@router.post("/apply")
async def apply_from_advisor(body: ApplyRequest | None = None) -> Dict[str, Any]:
    """Create and execute an optimization plan based on current advisor recommendations.

    Internally forwards to the Autopilot router to avoid duplicating logic.
    """
    try:
        # Import the autopilot creation endpoint and its request model
        from .autopilot import create_plan, PlanRequest

        payload = PlanRequest(
            target_hbm_util=(body.target_hbm_util if body and body.target_hbm_util is not None else 0.7),
            max_actions=(body.max_actions if body and body.max_actions is not None else 3),
            dry_run=(body.dry_run if body and body.dry_run is not None else False),
            allowed_actions=(body.allowed_actions if body else None),
        )

        # Delegate to the autopilot plan creation logic
        result = await create_plan(payload)
        return {"status": "ok", "plan": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"apply_from_advisor failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def generate_recommendations(
    plugin_metrics: Dict[str, Dict[str, Any]], 
    system_metrics: Dict[str, Any], 
    sequences: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Generate optimization recommendations based on plugin metrics and system state, with estimated savings."""
    recommendations: List[Dict[str, Any]] = []

    # Helper: attempt to read adapter config for bytes_per_token and default quant factor
    def get_adapter_params() -> tuple[float, float]:
        bpt = 0.0001
        qfactor = 0.5
        try:
            from kvopt.adapters.sim_adapter import SimAdapter
            inst = getattr(SimAdapter, "_instance", None)
            if inst is not None:
                bpt = float(getattr(inst, "_bytes_per_token", bpt))
                # default quantization factor from config, if present
                cfg = getattr(inst, "config", {}) or {}
                qfactor = float(cfg.get("quantization_factor", qfactor))
        except Exception:
            pass
        return bpt, qfactor

    bytes_per_token, default_q = get_adapter_params()

    # LMCache integration intentionally removed for now (Phase extracted)
    # If/when LMCache returns, wire its recommendations behind a feature flag in a dedicated module.

    # Check KIVI metrics
    kivi_metrics = plugin_metrics.get("kivi")
    if kivi_metrics:
        compression_ratio = kivi_metrics.get("compression_ratio", 1.0)
        if compression_ratio < 2.0:  # Low compression
            recommendations.append({
                "type": "quantization_optimization",
                "severity": "low",
                "message": "Low compression ratio with current quantization settings.",
                "details": {
                    "current_ratio": compression_ratio,
                    "suggested_action": "Consider using lower bitwidth or adjusting quantization parameters"
                },
                "estimated_hbm_savings_gb": 0.0,
            })

    # Generate recommendations based on system telemetry
    hbm_util = float(system_metrics.get("hbm_utilization", 0.0) or 0.0)
    p95 = float(system_metrics.get("p95_latency_ms", 0.0) or 0.0)

    # QUANTIZE largest sequence when utilization is above a small threshold
    if sequences and hbm_util > 0.005:
        largest = max(sequences, key=lambda s: s.get("length_tokens", 0))
        seq_id = largest.get("seq_id")
        tokens = int(largest.get("length_tokens", 0))
        est_gb = tokens * bytes_per_token * (1.0 - default_q)
        recommendations.append({
            "type": "QUANTIZE",
            "severity": "medium",
            "message": f"HBM utilization is elevated. Quantize the largest sequence {seq_id} to reduce memory.",
            "details": {
                "target_sequence": seq_id,
                "suggested_factor": default_q,
            },
            "estimated_hbm_savings_gb": float(round(est_gb, 4)),
        })

    # OFFLOAD half of the second-largest sequence at higher utilization
    if len(sequences) > 1 and hbm_util > 0.0075:
        sorted_seqs = sorted(sequences, key=lambda s: s.get("length_tokens", 0), reverse=True)
        second = sorted_seqs[1]
        seq_id = second.get("seq_id")
        tokens = int(second.get("length_tokens", 0)) // 2  # offload half
        est_gb = tokens * bytes_per_token  # assume qscale ~ 1.0 for estimate
        recommendations.append({
            "type": "OFFLOAD",
            "severity": "low",
            "message": f"HBM util is above target. Offload half of sequence {seq_id} to DDR to free HBM.",
            "details": {
                "target_sequence": seq_id,
                "range": "0..50%",
            },
            "estimated_hbm_savings_gb": float(round(est_gb, 4)),
        })

    # EVICT a small prefix of the third-largest under high latency + util
    if len(sequences) > 2 and (hbm_util > 0.008 or p95 > 20.0):
        sorted_seqs = sorted(sequences, key=lambda s: s.get("length_tokens", 0), reverse=True)
        third = sorted_seqs[2]
        seq_id = third.get("seq_id")
        evict_tokens = min(100, int(third.get("length_tokens", 0)))
        est_gb = evict_tokens * bytes_per_token
        recommendations.append({
            "type": "EVICT",
            "severity": "medium",
            "message": f"Latency/utilization suggests evicting a small prefix of {seq_id} to free hot HBM.",
            "details": {
                "target_sequence": seq_id,
                "range_tokens": evict_tokens,
            },
            "estimated_hbm_savings_gb": float(round(est_gb, 4)),
        })

    return recommendations

def get_system_metrics() -> Dict[str, float]:
    """Get current system metrics (simplified example)."""
    # In a real system, these would come from telemetry collection
    return {
        "hbm_utilization": 0.75,  # 75% HBM utilization
        "hbm_used_gb": 120.5,      # 120.5 GB of HBM used
        "p95_latency_ms": 45.2     # 45.2ms p95 latency
    }
