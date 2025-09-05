from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import time

from ..config import (
    Config, 
    Recommendation, 
    TelemetryData, 
    AdvisorReport,
    SequenceInfo
)

class PolicyEngine:
    """Engine for generating optimization recommendations based on current state."""
    
    def __init__(self, config: Config):
        self.config = config
        self.last_high_utilization_time: Optional[float] = None
        
    def analyze(self, telemetry: TelemetryData) -> AdvisorReport:
        """Analyze current state and generate recommendations."""
        recommendations: List[Recommendation] = []
        notes: List[str] = []
        
        # Check HBM utilization
        hbm_util = telemetry.hbm_utilization
        if hbm_util > self.config.budgets.hbm_util_target:
            if self.last_high_utilization_time is None:
                self.last_high_utilization_time = time.time()
                notes.append(f"HBM utilization {hbm_util:.1%} exceeds target {self.config.budgets.hbm_util_target:.0%}")
            
            # Generate recommendations based on policy
            self._add_eviction_recommendations(telemetry, recommendations)
            
            if hbm_util > 0.95:
                notes.append("Critical: HBM utilization > 95% - immediate action recommended")
        else:
            self.last_high_utilization_time = None
            notes.append("System within target utilization")
        
        # Check latency SLO
        if telemetry.p95_latency_ms > self.config.slo.latency_p95_ms:
            notes.append(f"P95 latency {telemetry.p95_latency_ms:.1f}ms exceeds SLO {self.config.slo.latency_p95_ms}ms")
            self._add_latency_recommendations(telemetry, recommendations)
        
        return AdvisorReport(
            hbm_utilization=hbm_util,
            hbm_used_gb=telemetry.hbm_used_gb,
            p95_latency_ms=telemetry.p95_latency_ms,
            sequences=telemetry.sequences,
            recommendations=recommendations,
            notes=notes
        )
    
    def _add_eviction_recommendations(
        self, 
        telemetry: TelemetryData,
        recommendations: List[Recommendation]
    ) -> None:
        """Add recommendations for evicting sequences from HBM."""
        if not telemetry.sequences:
            return
            
        # Sort sequences by age (oldest first)
        sequences_by_age = sorted(
            telemetry.sequences,
            key=lambda x: x.get('last_accessed', 0),
            reverse=False
        )
        
        # Estimate potential savings from evicting older sequences
        tokens_to_evict = 0
        for seq in sequences_by_age:
            if seq.get('last_accessed', 0) < time.time() - 60:  # Older than 1 minute
                tokens_to_evict += seq.get('length_tokens', 0)
        
        if tokens_to_evict > 0:
            # Rough estimate: 2 bytes per parameter * sequence length
            estimated_savings = (tokens_to_evict * 2) / (1024 ** 3)  # GB
            
            recommendations.append(Recommendation(
                action="evict_old_sequences",
                detail=f"Evict {len([s for s in sequences_by_age if s.get('last_accessed', 0) < time.time() - 60])} old sequences",
                estimated_hbm_savings_gb=estimated_savings,
                risk="low"
            ))
    
    def _add_latency_recommendations(
        self,
        telemetry: TelemetryData,
        recommendations: List[Recommendation]
    ) -> None:
        """Add recommendations for reducing latency."""
        # Simple recommendation: increase the keep_recent_tokens to reduce evictions
        current = self.config.policy.keep_recent_tokens
        recommendations.append(Recommendation(
            action="increase_keep_recent_tokens",
            detail=f"Increase keep_recent_tokens from {current} to {int(current * 1.5)}",
            estimated_hbm_savings_gb=0,  # This would actually increase usage
            risk="medium"
        ))
        
        # If we have many small sequences, suggest batching
        if len(telemetry.sequences) > 10:
            avg_tokens = sum(s.get('length_tokens', 0) for s in telemetry.sequences) / len(telemetry.sequences)
            if avg_tokens < 100:
                recommendations.append(Recommendation(
                    action="enable_batching",
                    detail=f"Enable batching for {len(telemetry.sequences)} small sequences (avg {avg_tokens:.1f} tokens)",
                    estimated_hbm_savings_gb=0.1,  # Placeholder
                    risk="low"
                ))
