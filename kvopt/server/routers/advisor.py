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
        # Get metrics from all plugins
        plugin_metrics = {}
        for plugin in plugin_manager.get_all_plugins():
            try:
                metrics = plugin.get_metrics()
                if metrics:
                    plugin_metrics[plugin.plugin_id] = metrics
            except Exception as e:
                logger.warning(f"Failed to get metrics from plugin {plugin.plugin_id}: {e}")
        
        # Generate recommendations based on plugin metrics
        recommendations = generate_recommendations(plugin_metrics)
        
        # Get system metrics (simplified - in a real system, these would come from telemetry)
        system_metrics = get_system_metrics()
        
        # Combine into advisor report
        report = {
            "hbm_utilization": system_metrics.get("hbm_utilization", 0.0),
            "hbm_used_gb": system_metrics.get("hbm_used_gb", 0.0),
            "p95_latency_ms": system_metrics.get("p95_latency_ms", 0.0),
            "recommendations": recommendations,
            "plugin_metrics": plugin_metrics
        }
        
        return report
        
    except Exception as e:
        logger.error(f"Error generating advisor report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_recommendations(plugin_metrics: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate optimization recommendations based on plugin metrics."""
    recommendations = []
    
    # Check LMCache metrics
    lmcache_metrics = plugin_metrics.get("lmcache")
    if lmcache_metrics:
        hit_rate = lmcache_metrics.get("hit_rate", 0)
        if hit_rate < 0.3:  # Low hit rate
            recommendations.append({
                "type": "reuse_optimization",
                "severity": "medium",
                "message": "Low cache hit rate. Consider increasing cache size or tuning eviction policy.",
                "details": {
                    "current_hit_rate": hit_rate,
                    "suggested_action": "Increase cache size or adjust sequence length requirements"
                }
            })
    
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
                }
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
