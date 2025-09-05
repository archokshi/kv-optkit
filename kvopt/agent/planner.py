"""
Minimal Planner for KV-OptKit Phase 3 tests.

Produces a simple Plan composed of QUANTIZE actions after preferring REUSE implicitly
(i.e., planner itself doesn't create REUSE actions; reuse is opportunistic via plugins),
then applies quantization until the estimated HBM utilization is under target.

This is intentionally lightweight to support unit/integration tests.
"""
from dataclasses import dataclass
from typing import List, Dict, Any

from .actions import Action, ActionType, KVRef, Plan


@dataclass
class PlannerInputs:
    hbm_util_current: float  # e.g., 0.92
    hbm_util_target: float   # e.g., 0.85
    sequences: List[str]     # sequence ids eligible for actions


class Planner:
    def __init__(self, quantize_scale: float = 0.1):
        # scale ~ proxy for accuracy cost per QUANTIZE action
        self.quantize_scale = float(quantize_scale)

    def make_plan(self, inputs: PlannerInputs) -> Plan:
        # If already under target, return empty, low-impact plan
        if inputs.hbm_util_current <= inputs.hbm_util_target:
            return Plan(
                actions=[],
                priority="low",
                estimated_hbm_reduction=0.0,
                estimated_accuracy_impact=0.0,
                id="plan_ok",
            )

        # Create one QUANTIZE action per sequence until we estimate crossing target
        actions: List[Action] = []
        needed_delta = max(0.0, inputs.hbm_util_current - inputs.hbm_util_target)

        # Simple heuristic: each action reduces util by a small fixed amount
        per_action_reduction = 0.02  # 2% per action (demo-only)
        est_reduction = 0.0

        for sid in inputs.sequences:
            actions.append(
                Action(
                    action_type=ActionType.QUANTIZE,
                    target=KVRef(sequence_id=sid),
                    params={"bitwidth": 4, "scale": self.quantize_scale},
                )
            )
            est_reduction += per_action_reduction
            if est_reduction >= needed_delta:
                break

        est_acc_impact = max(0.0, len(actions) * self.quantize_scale * 0.01)

        return Plan(
            actions=actions,
            priority="medium" if actions else "low",
            estimated_hbm_reduction=est_reduction,
            estimated_accuracy_impact=est_acc_impact,
            id="plan_quantize",
        )
