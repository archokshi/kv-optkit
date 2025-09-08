"""
Policy Engine for KV-OptKit.

This module contains the PolicyEngine class which is responsible for generating
optimization plans based on the current system state and configuration.
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
import math

from kvopt.agent import Plan, Action, ActionType, KVRef
from kvopt.adapters.base import Adapter

logger = logging.getLogger(__name__)


class PlanPriority(str, Enum):
    """Priority levels for optimization plans."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PlanRequest:
    """Request for generating an optimization plan."""
    telemetry: Dict[str, Any]
    target_hbm_util: float
    max_actions: int
    priority: PlanPriority = PlanPriority.MEDIUM


class PolicyEngine:
    """
    Policy engine for generating optimization plans.
    
    The policy engine is responsible for analyzing the current system state
    and generating a sequence of actions to optimize KV cache usage.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the policy engine.
        
        Args:
            config: Configuration dictionary
        """
        self.config = {
            "target_hbm_utilization": 0.8,
            "min_accuracy_threshold": 0.9,
            "max_actions_per_plan": 20,
            "action_priority": ["REUSE", "EVICT", "OFFLOAD", "QUANTIZE"],
            "quantization_scales": [0.5, 0.25, 0.125],
            "min_sequence_length": 128,  # Minimum sequence length to consider for offloading
            "min_sequence_utilization": 0.1,  # Minimum utilization to consider a sequence for optimization
        }
        self.config.update(config)
        
        # Initialize action generators
        self._action_generators = {
            "REUSE": self._generate_reuse_actions,
            "EVICT": self._generate_evict_actions,
            "OFFLOAD": self._generate_offload_actions,
            "QUANTIZE": self._generate_quantize_actions,
        }
    
    def build_plan(
        self,
        telemetry: Dict[str, Any],
        target_hbm_util: Optional[float] = None,
        max_actions: Optional[int] = None,
        priority: PlanPriority = PlanPriority.MEDIUM,
        allowed_actions: Optional[List[str]] = None,
    ) -> Plan:
        """
        Build an optimization plan based on the current system state.
        
        Args:
            telemetry: Current system telemetry
            target_hbm_util: Target HBM utilization (0.0 to 1.0)
            max_actions: Maximum number of actions to include in the plan
            priority: Priority level for the plan
            
        Returns:
            Plan: The generated optimization plan
        """
        # Use defaults if not specified
        target_hbm_util = target_hbm_util or self.config["target_hbm_utilization"]
        max_actions = max_actions or self.config["max_actions_per_plan"]
        
        # Create plan request
        request = PlanRequest(
            telemetry=telemetry,
            target_hbm_util=target_hbm_util,
            max_actions=max_actions,
            priority=priority
        )
        
        # Generate actions based on priority
        actions = []
        remaining_actions = max_actions
        
        # Determine generation order honoring allowed_actions if provided
        gen_order = list(self.config["action_priority"]) if isinstance(self.config.get("action_priority"), list) else ["REUSE","EVICT","OFFLOAD","QUANTIZE"]
        if allowed_actions:
            allowed = {a.upper() for a in allowed_actions}
            gen_order = [a for a in gen_order if a.upper() in allowed]

        for action_type in gen_order:
            if remaining_actions <= 0:
                break
                
            # Generate actions of this type
            new_actions = self._action_generators[action_type](request, remaining_actions)
            
            # Add to plan
            actions.extend(new_actions)
            remaining_actions -= len(new_actions)
        
        # Calculate estimated impact
        estimated_hbm_reduction = self._estimate_hbm_reduction(actions, telemetry)
        estimated_accuracy_impact = self._estimate_accuracy_impact(actions, telemetry)
        
        # Create and return the plan
        return Plan(
            actions=actions,
            priority=priority,
            estimated_hbm_reduction=estimated_hbm_reduction,
            estimated_accuracy_impact=estimated_accuracy_impact
        )
    
    def _generate_evict_actions(
        self,
        request: PlanRequest,
        max_actions: int
    ) -> List[Action]:
        """Generate actions to evict sequences from the KV cache."""
        actions = []
        sequences = request.telemetry.get("sequences", [])
        
        # Sort sequences by least recently used (LRU) or another heuristic
        # For now, we'll use a simple random selection
        candidates = []
        
        for seq in sequences:
            seq_id = seq.get("id")
            seq_len = seq.get("length", 0)
            
            # Skip sequences that are too short or don't have an ID
            if not seq_id or seq_len < self.config["min_sequence_length"]:
                continue
            
            # Calculate sequence utilization
            seq_util = seq.get("utilization", 0.0)
            if seq_util < self.config["min_sequence_utilization"]:
                continue
                
            candidates.append((seq_id, seq_util, seq_len))
        
        # Sort candidates by utilization (lowest first)
        candidates.sort(key=lambda x: x[1])
        
        # Generate evict actions for the top candidates
        for seq_id, _, _ in candidates[:max_actions]:
            actions.append(Action(
                action_type=ActionType.EVICT,
                target=KVRef(sequence_id=seq_id),
                params={"reason": "low_utilization"}
            ))
        
        return actions

    def _generate_reuse_actions(
        self,
        request: PlanRequest,
        max_actions: int
    ) -> List[Action]:
        """Generate REUSE actions (KV cache reuse hints). Does not reduce HBM directly.
        We prefer long, repeated sequences if telemetry provides repetition hints.
        """
        actions: List[Action] = []
        sequences = request.telemetry.get("sequences", [])
        # Prefer longer sequences; if a sequence carries a 'repeat' hint, prioritize it
        candidates: List[tuple[str, int, int]] = []  # (id, length, repeat_score)
        for seq in sequences:
            seq_id = seq.get("id")
            seq_len = seq.get("length", 0)
            if not seq_id or seq_len < self.config["min_sequence_length"]:
                continue
            repeat = int(seq.get("repeat", 0))
            candidates.append((seq_id, seq_len, repeat))
        # Sort by repeat desc, then length desc
        candidates.sort(key=lambda x: (-x[2], -x[1]))
        for seq_id, _, _ in candidates[:max_actions]:
            actions.append(Action(
                action_type=ActionType.REUSE,
                target=KVRef(sequence_id=seq_id),
                params={"hint": "enable_reuse"}
            ))
        return actions
    
    def _generate_offload_actions(
        self,
        request: PlanRequest,
        max_actions: int
    ) -> List[Action]:
        """Generate actions to offload sequences to DDR."""
        actions = []
        sequences = request.telemetry.get("sequences", [])
        
        # Get current HBM utilization
        hbm_util = request.telemetry.get("hbm_utilization", 1.0)
        
        # If we're already below target, no need to offload
        if hbm_util <= request.target_hbm_util:
            return actions
        
        # Calculate how much we need to offload (in bytes or tokens)
        # For simplicity, we'll use a token-based approach
        total_tokens = sum(seq.get("length", 0) for seq in sequences)
        target_tokens = total_tokens * (1 - request.target_hbm_util)
        
        # Sort sequences by size (largest first)
        candidates = []
        
        for seq in sequences:
            seq_id = seq.get("id")
            seq_len = seq.get("length", 0)
            
            # Skip sequences that are too short or don't have an ID
            if not seq_id or seq_len < self.config["min_sequence_length"]:
                continue
            
            # Skip sequences that are already offloaded
            if seq.get("tier") == "DDR":
                continue
                
            candidates.append((seq_id, seq_len))
        
        # Sort by sequence length (descending)
        candidates.sort(key=lambda x: -x[1])
        
        # Generate offload actions until we've reached our target or max actions
        offloaded_tokens = 0
        
        for seq_id, seq_len in candidates:
            if len(actions) >= max_actions or offloaded_tokens >= target_tokens:
                break
                
            actions.append(Action(
                action_type=ActionType.OFFLOAD,
                target=KVRef(sequence_id=seq_id),
                params={"tier": "DDR"}
            ))
            
            offloaded_tokens += seq_len
        
        return actions
    
    def _generate_quantize_actions(
        self,
        request: PlanRequest,
        max_actions: int
    ) -> List[Action]:
        """Generate actions to quantize sequences in the KV cache."""
        actions = []
        sequences = request.telemetry.get("sequences", [])
        
        # Get current HBM utilization
        hbm_util = request.telemetry.get("hbm_utilization", 1.0)
        
        # If we're already below target, no need to quantize
        if hbm_util <= request.target_hbm_util:
            return actions
        
        # Sort sequences by size (largest first)
        candidates = []
        
        for seq in sequences:
            seq_id = seq.get("id")
            seq_len = seq.get("length", 0)
            
            # Skip sequences that are too short or don't have an ID
            if not seq_id or seq_len < self.config["min_sequence_length"]:
                continue
            
            # Skip sequences that are already quantized
            if seq.get("qscale", 1.0) < 1.0:
                continue
                
            candidates.append((seq_id, seq_len))
        
        # Sort by sequence length (descending)
        candidates.sort(key=lambda x: -x[1])
        
        # Generate quantize actions
        for seq_id, _ in candidates[:max_actions]:
            # Choose a random quantization scale
            qscale = random.choice(self.config["quantization_scales"])
            
            actions.append(Action(
                action_type=ActionType.QUANTIZE,
                target=KVRef(sequence_id=seq_id),
                params={"scale": qscale}
            ))
        
        return actions
    
    def _estimate_hbm_reduction(
        self,
        actions: List[Action],
        telemetry: Dict[str, Any]
    ) -> float:
        """Estimate the HBM reduction from a list of actions."""
        # This is a simplified estimation
        total_reduction = 0.0
        sequences = {seq["id"]: seq for seq in telemetry.get("sequences", [])}
        
        for action in actions:
            seq_id = action.target.sequence_id
            seq = sequences.get(seq_id)
            
            if not seq:
                continue
                
            seq_len = seq.get("length", 0)
            
            if action.action_type == ActionType.REUSE:
                # REUSE does not reduce HBM; may reduce compute/latency only
                total_reduction += 0.0
            
            if action.action_type == ActionType.EVICT:
                total_reduction += seq_len
            elif action.action_type == ActionType.OFFLOAD:
                # Offloading reduces HBM usage by the sequence size
                total_reduction += seq_len * 0.8  # Assume 20% metadata overhead
            elif action.action_type == ActionType.QUANTIZE:
                # Quantization reduces size by the scale factor
                scale = action.params.get("scale", 0.5)
                total_reduction += seq_len * (1.0 - scale)
        
        # Convert to percentage of total HBM
        total_hbm = telemetry.get("hbm_capacity_bytes", 1)
        return total_reduction / total_hbm if total_hbm > 0 else 0.0
    
    def _estimate_accuracy_impact(
        self,
        actions: List[Action],
        telemetry: Dict[str, Any]
    ) -> float:
        """Estimate the accuracy impact of a list of actions."""
        # This is a simplified estimation
        total_impact = 0.0
        sequences = {seq["id"]: seq for seq in telemetry.get("sequences", [])}
        
        for action in actions:
            seq_id = action.target.sequence_id
            seq = sequences.get(seq_id)
            
            if not seq:
                continue
                
            seq_len = seq.get("length", 0)
            
            if action.action_type == ActionType.REUSE:
                # Assume negligible accuracy impact for reuse hints
                total_impact += 0.0
            
            if action.action_type == ActionType.EVICT:
                # Eviction has the highest impact
                total_impact += seq_len * 0.01  # 1% impact per token
            elif action.action_type == ActionType.OFFLOAD:
                # Offloading has a moderate impact
                total_impact += seq_len * 0.005  # 0.5% impact per token
            elif action.action_type == ActionType.QUANTIZE:
                # Quantization has a lower impact
                scale = action.params.get("scale", 0.5)
                total_impact += seq_len * (1.0 - scale) * 0.01  # Scale impact by quantization factor
        
        # Normalize to [0, 1] range
        total_tokens = sum(seq.get("length", 0) for seq in sequences.values())
        return min(1.0, total_impact / total_tokens if total_tokens > 0 else 0.0)
    
    @classmethod
    def get_current(cls) -> 'PolicyEngine':
        """Get the current policy engine instance."""
        # This is a simplified implementation
        # In a real application, this would use a dependency injection system
        return cls({})
