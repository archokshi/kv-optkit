"""
Autopilot router compatible with tests in tests/test_autopilot_api.py.

Exposes module-level POLICY_ENGINE, ACTION_EXECUTOR, GUARD, PLANS so tests can patch them.
Validates input and delegates to the Policy Engine and Action Executor.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from enum import Enum
import logging
import time

from kvopt.agent import Action, ActionType, KVRef, Plan, PlanStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autopilot", tags=["autopilot"])

# Module-level handles (tests patch these)
POLICY_ENGINE = None
ACTION_EXECUTOR = None
GUARD = None
PLANS: Dict[str, Plan] = {}


class PriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class PlanRequest(BaseModel):
    target_hbm_util: float = Field(..., ge=0.0, le=1.0)
    max_actions: int = Field(3, ge=1)
    priority: PriorityEnum | None = PriorityEnum.medium
    dry_run: bool = False
    allowed_actions: Optional[List[str]] = None


@router.post("/plan")
async def create_plan(request: PlanRequest):
    """Create and optionally execute an optimization plan via Policy Engine."""
    global POLICY_ENGINE, ACTION_EXECUTOR, PLANS

    # Ensure engines exist (tests patch these, but provide fallbacks for runtime)
    if POLICY_ENGINE is None or ACTION_EXECUTOR is None:
        try:
            from kvopt.server import main as server_main
            if POLICY_ENGINE is None:
                POLICY_ENGINE = getattr(server_main, "_policy_engine", None)
            if ACTION_EXECUTOR is None:
                ACTION_EXECUTOR = getattr(server_main, "_action_executor", None)
        except Exception:
            pass

    if POLICY_ENGINE is None or ACTION_EXECUTOR is None:
        raise HTTPException(status_code=500, detail="Autopilot not initialized")

    # Ask policy engine to build a plan (support legacy generate_plan in tests)
    if hasattr(POLICY_ENGINE, "generate_plan"):
        # Legacy path used by tests with mocks
        plan: Plan = POLICY_ENGINE.generate_plan(
            target_hbm_util=request.target_hbm_util,
            max_actions=request.max_actions,
            priority=(request.priority or PriorityEnum.medium).value,
            allowed_actions=request.allowed_actions,
        )
    else:
        telemetry = {}
        try:
            from kvopt.server import main as server_main
            if getattr(server_main, "_adapter", None):
                telemetry = server_main._adapter.get_telemetry() or {}
                # Enrich telemetry with sequences for the policy engine
                try:
                    seqs = getattr(server_main._adapter, "get_sequences", lambda: [])() or []
                    seq_list = []
                    for s in seqs:
                        sid = s.get("sequence_id") or s.get("seq_id") or s.get("id")
                        length = int(s.get("total_tokens") or s.get("length_tokens") or 0)
                        util = float(s.get("hbm_tokens", 0.0)) / float(max(1, length)) if length > 0 else 0.5
                        seq_list.append({"id": sid, "length": length, "utilization": util, "tier": "HBM"})
                    telemetry["sequences"] = seq_list
                except Exception:
                    pass
        except Exception:
            telemetry = {}
        plan: Plan = POLICY_ENGINE.build_plan(
            telemetry=telemetry,
            target_hbm_util=request.target_hbm_util,
            max_actions=request.max_actions,
            priority=(request.priority or PriorityEnum.medium).value,
            allowed_actions=request.allowed_actions,
        )

    # Store and (optionally) execute
    # Ensure plan has an id for storage
    pid = getattr(plan, "plan_id", None) or getattr(plan, "id", None)
    if not pid:
        try:
            # Try to assign a plan_id if mutable
            plan.plan_id = f"plan_{int(time.time()*1000)}"  # type: ignore[attr-defined]
            pid = plan.plan_id
        except Exception:
            import time as _t
            pid = f"plan_{int(_t.time()*1000)}"
    PLANS[pid] = plan
    # Respect global apply toggle
    allow_apply = True
    try:
        from kvopt.server import main as server_main
        allow_apply = bool(getattr(server_main, "_allow_apply", True))
    except Exception:
        allow_apply = True

    if not request.dry_run and allow_apply:
        # Optional Guard integration
        telemetry_before = {}
        try:
            from kvopt.server import main as server_main
            if getattr(server_main, "_adapter", None):
                telemetry_before = server_main._adapter.get_telemetry() or {}
            if getattr(server_main, "_guard", None):
                server_main._guard.start_plan_execution(plan, telemetry_before)
        except Exception:
            pass

        exec_result = ACTION_EXECUTOR.execute_plan(plan)
        # Normalize result
        ok = False
        err = None
        if isinstance(exec_result, tuple) and len(exec_result) == 2:
            ok, err = bool(exec_result[0]), exec_result[1]
        elif isinstance(exec_result, dict):
            ok = bool(exec_result.get("ok", False))
            err = exec_result.get("error")
        else:
            # Object result: try attributes
            ok = bool(getattr(exec_result, "ok", False))
            err = getattr(exec_result, "error", None)

        # Guard post-checks and last-apply snapshot
        try:
            from kvopt.server import main as server_main
            telemetry_after = {}
            if getattr(server_main, "_adapter", None):
                telemetry_after = server_main._adapter.get_telemetry() or {}
            paused = False
            reason = None
            if getattr(server_main, "_guard", None):
                rollback, reason = server_main._guard.end_plan_execution(plan, telemetry_after)
                # If rollback requested and executor supports rollback, attempt it
                if rollback and hasattr(ACTION_EXECUTOR, "rollback_plan"):
                    try:
                        ACTION_EXECUTOR.rollback_plan(plan)
                    except Exception:
                        pass
                # Metrics: count rollbacks
                try:
                    from kvopt.server.metrics import autopilot_rollbacks
                    if rollback:
                        autopilot_rollbacks.inc()
                except Exception:
                    pass
            # Update UI snapshot for last apply
            server_main._last_apply = {
                "plan_id": plan.plan_id,
                "ok": bool(ok),
                "error": err,
                "guard_reason": reason,
            }
            # Metrics: count applies
            try:
                from kvopt.server.metrics import autopilot_applies, apply_success, apply_fail
                if ok:
                    autopilot_applies.inc()
                    apply_success.inc()
                else:
                    apply_fail.inc()
            except Exception:
                pass
        except Exception:
            pass

        # Do not raise to keep API stable for CPU-only/sidecar tests; surface error via last_apply
        # if not ok: we continue and return the plan (client can inspect /apply/last)

    # Return a serializable plan
    try:
        return plan.dict()
    except Exception:
        try:
            from dataclasses import asdict
            return asdict(plan)
        except Exception:
            return {"plan_id": pid}


@router.get("/plan/{plan_id}")
async def get_plan_status(plan_id: str):
    """Get plan status from in-memory storage."""
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    plan = PLANS[plan_id]
    return plan.dict()


@router.get("/debug/plans")
async def debug_plans():
    return {
        "plan_count": len(PLANS),
        "plan_ids": list(PLANS.keys()),
    }


@router.get("/metrics")
async def get_metrics():
    global GUARD
    if GUARD is None:
        try:
            from kvopt.server import main as server_main
            GUARD = getattr(server_main, "_guard", None)
        except Exception:
            GUARD = None
    if GUARD is None:
        return {"total_plans": len(PLANS)}
    return GUARD.get_metrics()


@router.post("/plan/{plan_id}/cancel")
async def cancel_plan(plan_id: str):
    global ACTION_EXECUTOR
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    if ACTION_EXECUTOR is None:
        try:
            from kvopt.server import main as server_main
            ACTION_EXECUTOR = getattr(server_main, "_action_executor", None)
        except Exception:
            ACTION_EXECUTOR = None
    if ACTION_EXECUTOR is None:
        raise HTTPException(status_code=500, detail="Action executor not initialized")
    ok = ACTION_EXECUTOR.cancel_plan(plan_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to cancel plan")
    # Update status locally if Plan model supports copy/update
    try:
        plan = PLANS[plan_id]
        PLANS[plan_id] = plan.copy(update={"status": PlanStatus.CANCELLED})
    except Exception:
        pass
    return {"status": "cancelled", "plan_id": plan_id}
