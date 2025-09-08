from typing import Any, Dict, List, Optional
import threading
import time
import random

from .base import Adapter
from ..server.metrics import engine_alloc_bytes, engine_free_bytes, engine_page_moves, engine_page_moved_bytes


try:  # Optional NVML import; degrade gracefully if unavailable
    import pynvml  # type: ignore
except Exception:  # pragma: no cover
    pynvml = None  # type: ignore

# Optional ROCm SMI import; degrade gracefully
try:
    import rocm_smi_lib as rsmi  # type: ignore
except Exception:  # pragma: no cover
    rsmi = None  # type: ignore

# Optional torch import; degrade gracefully
try:
    import torch  # type: ignore
except Exception:  # pragma: no cover
    torch = None  # type: ignore


class VLLMAdapter(Adapter):
    """
    vLLM adapter (Phase 5 scaffold with NVML telemetry and transactional stubs).

    - Telemetry: best-effort NVML GPU memory stats (device 0) with graceful fallback.
    - Actions: transactional apply stubs for QUANTIZE / OFFLOAD / EVICT.
      These update an internal estimate of HBM usage to reflect changes.
      Real engine hooks can replace `_apply_*` methods in a later phase.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.__class__._instance = self

        # Internal estimated HBM usage (GB); used if NVML unavailable
        self._est_hbm_total_gb: float = float(self.config.get("hbm_capacity_gb") or 80.0)
        self._est_hbm_used_gb: float = float(self.config.get("hbm_used_gb") or 48.0)
        self._p95_latency_ms: float = float(self.config.get("p95_latency_ms") or 32.0)

        # Simple action log for transactional semantics (stack of dict entries)
        self._action_log: List[Dict[str, Any]] = []
        # Optional undo entries constructed from engine events or heuristics
        self._undo_log: List[Dict[str, Any]] = []
        # Bandwidth governor state (bytes within current tick window)
        self._bw_window_start: float = 0.0
        self._bw_window_bytes: float = 0.0

        # Minimal in-process sequence tracker (to be replaced by real engine hooks)
        # Map: seq_id -> {"total_tokens": int, "created_at": float, "last_accessed": float}
        self._sequences: Dict[str, Dict[str, Any]] = {}
        self._seq_lock = threading.Lock()
        # Hook target (engine) and event queue (if registered)
        self._engine: Optional[Any] = None
        self._event_queue: List[Dict[str, Any]] = []

        # NVML init (optional)
        self._nvml_handle: Optional[Any] = None
        try:
            if pynvml:
                pynvml.nvmlInit()
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._nvml_handle = None

        # Optional demo sequence generator to surface real-looking data in QuickView
        if bool(self.config.get("demo_generate_sequences", False)):
            self._start_demo_sequence_thread()

    @classmethod
    def current(cls) -> Optional["VLLMAdapter"]:
        """Return the process-global adapter instance if initialized."""
        return getattr(cls, "_instance", None)

    def _nvml_memory_gb(self) -> Optional[Dict[str, float]]:
        try:
            if not self._nvml_handle:
                return None
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            # Convert bytes to GB
            total_gb = float(mem.total) / (1024**3)
            used_gb = float(mem.used) / (1024**3)
            return {"total_gb": total_gb, "used_gb": used_gb}
        except Exception:
            return None

    def _rocm_memory_gb(self) -> Optional[Dict[str, float]]:
        try:
            if not rsmi:
                return None
            rsmi.rsmi_init(0)
            try:
                # Device 0 by default
                dv = 0
                used = rsmi.rsmi_dev_memory_usage_get(dv, rsmi.RSMI_MEM_TYPE_VRAM)
                total = rsmi.rsmi_dev_memory_total_get(dv, rsmi.RSMI_MEM_TYPE_VRAM)
                total_gb = float(total) / (1024**3)
                used_gb = float(used) / (1024**3)
                return {"total_gb": total_gb, "used_gb": used_gb}
            finally:
                try:
                    rsmi.rsmi_shut_down()
                except Exception:
                    pass
        except Exception:
            return None

    def _torch_cuda_memory_gb(self) -> Optional[Dict[str, float]]:
        try:
            if not torch or not torch.cuda.is_available():
                return None
            free_b, total_b = torch.cuda.mem_get_info()  # type: ignore[attr-defined]
            total_gb = float(total_b) / (1024**3)
            used_gb = float(total_b - free_b) / (1024**3)
            return {"total_gb": total_gb, "used_gb": used_gb}
        except Exception:
            return None

    def get_telemetry(self) -> Dict[str, Any]:
        # Prefer NVML, then ROCm SMI, then torch.cuda, else internal estimate
        nv = self._nvml_memory_gb()
        ro = None if nv else self._rocm_memory_gb()
        tc = None if (nv or ro) else self._torch_cuda_memory_gb()
        if nv:
            hbm_total = nv["total_gb"]
            hbm_used = nv["used_gb"]
        elif ro:
            hbm_total = ro["total_gb"]
            hbm_used = ro["used_gb"]
        elif tc:
            hbm_total = tc["total_gb"]
            hbm_used = tc["used_gb"]
        else:
            hbm_total = self._est_hbm_total_gb
            hbm_used = self._est_hbm_used_gb

        # Build lightweight sequence summaries for UI KPI
        seq_summaries: List[Dict[str, Any]] = []
        try:
            with self._seq_lock:
                for sid, s in self._sequences.items():
                    seq_summaries.append({
                        "id": sid,
                        "length": int(s.get("total_tokens", 0)),
                        "last_accessed": float(s.get("last_accessed", 0.0)),
                    })
        except Exception:
            seq_summaries = []

        return {
            "adapter": "vllm",
            "hbm_used_gb": hbm_used,
            "hbm_total_gb": hbm_total,
            "p95_latency_ms": self._p95_latency_ms,
            "sequences": seq_summaries,
            "total_sequences": len(seq_summaries),
        }

    def capabilities(self) -> set:
        """Initial vLLM capability set (expand as hooks land)."""
        return {"EVICT", "OFFLOAD"}

    # ---- Transactional apply stubs ----
    def execute_action(self, action: Dict[str, Any]) -> bool:
        try:
            atype = (action.get("action_type") or action.get("type") or "").upper()
            seq = str(action.get("sequence_id", ""))
            start = int(action.get("start_token", 0) or 0)
            end = int(action.get("end_token", 0) or 0)
            factor = float(action.get("factor", action.get("scale", 0.5)) or 0.5)

            delta_gb = 0.0
            if atype == "QUANTIZE":
                delta_gb = self._apply_quantize(seq, start, end, factor)
            elif atype == "OFFLOAD":
                delta_gb = self._apply_offload(seq, start, end)
            elif atype == "EVICT":
                delta_gb = self._apply_evict(seq, start, end)
            else:
                # Unknown action; treat as no-op
                return False

            # Log action with delta for potential rollback later
            self._action_log.append({
                "action": atype,
                "sequence_id": seq,
                "start_token": start,
                "end_token": end,
                "delta_hbm_gb": delta_gb,
            })
            # Update internal estimate if NVML is not available
            if not self._nvml_memory_gb():
                self._est_hbm_used_gb = max(0.0, self._est_hbm_used_gb - delta_gb)
            return True
        except Exception:
            return False

    def _apply_quantize(self, sequence_id: str, start: int, end: int, factor: float) -> float:
        # Demo-only heuristic: quantizing reduces memory by a small amount
        # Factor indicates compression factor (e.g., 0.5 -> 50% of original)
        token_span = max(0, end - start)
        bytes_per_token = float(self.config.get("bytes_per_token") or 0.0002)
        saved_gb = token_span * bytes_per_token * (1.0 - factor)
        return float(saved_gb)

    def _apply_offload(self, sequence_id: str, start: int, end: int) -> float:
        # Demo heuristic + bandwidth governor per tick
        token_span = max(0, end - start)
        bytes_per_token_gb = float(self.config.get("bytes_per_token") or 0.0002)
        # Governor config: offload_bw_gbps from budgets; default 120 GB/s
        bw_gbps = float(self.config.get("offload_bw_gbps") or self.config.get("budgets", {}).get("offload_bw_gbps", 120.0))
        tick_ms = float(self.config.get("governor_tick_ms") or 200.0)
        # Enforce bytes-per-tick window regardless of NVML presence (best-effort pacing)
        max_bytes = max(0.0, bw_gbps) * 1e9 * (tick_ms / 1000.0)
        bpt_bytes = bytes_per_token_gb * (1024**3)
        now = time.time() * 1000.0
        # Reset window if tick has elapsed
        if now - self._bw_window_start >= tick_ms:
            self._bw_window_start = now
            self._bw_window_bytes = 0.0
        # Available budget in this tick
        remaining_bytes = max(0.0, max_bytes - self._bw_window_bytes)
        if bpt_bytes > 0 and remaining_bytes >= 0:
            max_tokens_this_tick = int(remaining_bytes / bpt_bytes)
            token_span = min(token_span, max_tokens_this_tick)
        # Account usage
        used_bytes = max(0, token_span) * bpt_bytes
        self._bw_window_bytes += used_bytes
        saved_gb = token_span * bytes_per_token_gb
        return float(saved_gb)

    def _apply_evict(self, sequence_id: str, start: int, end: int) -> float:
        # Demo-only heuristic: evicting tokens frees memory linearly (small impact)
        token_span = max(0, end - start)
        bytes_per_token = float(self.config.get("bytes_per_token") or 0.0002)
        saved_gb = 0.5 * token_span * bytes_per_token
        return float(saved_gb)

    def get_sequences(self) -> List[Dict[str, Any]]:
        # Return snapshot of current known sequences
        out: List[Dict[str, Any]] = []
        with self._seq_lock:
            for sid, s in self._sequences.items():
                out.append({
                    "sequence_id": sid,
                    "segments": [],  # vLLM hook TBD; flattened summary for now
                    "total_tokens": int(s.get("total_tokens", 0)),
                    "hbm_tokens": int(s.get("total_tokens", 0)),
                    "ddr_tokens": 0,
                    "last_accessed": float(s.get("last_accessed", 0.0)),
                    "bytes": float(s.get("bytes", 0.0)),
                })
        return out

    # --- Minimal event API (to be wired to real engine callbacks later) ---
    def register_engine_callbacks(self, engine: Any) -> None:
        """Register upstream engine to receive block/page events.

        Intended for in-process vLLM integration; not required for sidecar mode.
        """
        self._engine = engine

    def on_block_alloc(self, sequence_id: str, bytes_alloc: int) -> None:
        now = time.time()
        with self._seq_lock:
            s = self._sequences.setdefault(sequence_id, {
                "total_tokens": 0,
                "created_at": now,
                "last_accessed": now,
            })
            s["last_accessed"] = now
            s["bytes"] = float(s.get("bytes", 0.0)) + float(max(0, int(bytes_alloc)))
        # Push to event queue for potential undo derivation
        self._event_queue.append({"t": now, "ev": "alloc", "seq": sequence_id, "bytes": int(bytes_alloc)})
        try:
            engine_alloc_bytes.inc(max(0, int(bytes_alloc)))
        except Exception:
            pass

    def on_block_free(self, sequence_id: str, bytes_free: int) -> None:
        now = time.time()
        with self._seq_lock:
            if sequence_id in self._sequences:
                s = self._sequences[sequence_id]
                s["last_accessed"] = now
                s["bytes"] = max(0.0, float(s.get("bytes", 0.0)) - float(max(0, int(bytes_free))))
        self._event_queue.append({"t": now, "ev": "free", "seq": sequence_id, "bytes": int(bytes_free)})
        try:
            engine_free_bytes.inc(max(0, int(bytes_free)))
        except Exception:
            pass

    def on_page_move(self, sequence_id: str, bytes_moved: int, src: str, dst: str) -> None:
        now = time.time()
        # Accounting by tier is deferred; record the move for future metrics
        self._event_queue.append({"t": now, "ev": "move", "seq": sequence_id, "bytes": int(bytes_moved), "src": src, "dst": dst})
        try:
            engine_page_moves.inc()
            engine_page_moved_bytes.inc(max(0, int(bytes_moved)))
        except Exception:
            pass

    # --- Undo helpers for engine-driven rollbacks ---
    def record_undo_add_back(self, gb: float) -> None:
        """Record an undo entry indicating HBM should be added back by 'gb' on rollback.

        Engine integrations can compute this based on alloc/free/move events to provide
        exact rollback behavior.
        """
        try:
            val = float(gb)
        except Exception:
            return
        if val > 0:
            self._undo_log.append({"kind": "hbm_add_back", "gb": float(val)})
    def track_request_start(self, sequence_id: str, total_tokens: int) -> None:
        now = time.time()
        with self._seq_lock:
            self._sequences[sequence_id] = {
                "total_tokens": int(max(0, total_tokens)),
                "created_at": now,
                "last_accessed": now,
            }

    def track_request_update(self, sequence_id: str, delta_tokens: int) -> None:
        now = time.time()
        with self._seq_lock:
            s = self._sequences.get(sequence_id)
            if not s:
                return
            s["total_tokens"] = int(max(0, int(s.get("total_tokens", 0)) + int(delta_tokens)))
            s["last_accessed"] = now

    def track_request_finish(self, sequence_id: str) -> None:
        with self._seq_lock:
            self._sequences.pop(sequence_id, None)

    # --- Demo sequence generator ---
    def _start_demo_sequence_thread(self) -> None:
        def _runner():
            try:
                # Keep a small pool of sequences active, modify lengths over time
                rnd = random.Random(1234)
                while True:
                    with self._seq_lock:
                        # Randomly add sequences until 3-6 active
                        if len(self._sequences) < rnd.randint(3, 6):
                            sid = f"seq-{int(time.time()*1000)}-{rnd.randint(100,999)}"
                            self._sequences[sid] = {
                                "total_tokens": rnd.randint(256, 4096),
                                "created_at": time.time(),
                                "last_accessed": time.time(),
                            }
                        # Randomly grow/shrink some sequences
                        for sid, s in list(self._sequences.items()):
                            if rnd.random() < 0.7:
                                s["total_tokens"] = max(0, int(s["total_tokens"]) + rnd.randint(-128, 256))
                                s["last_accessed"] = time.time()
                            # Occasionally finish sequences
                            if s["total_tokens"] <= 0 or rnd.random() < 0.05:
                                self._sequences.pop(sid, None)
                    time.sleep(0.5)
            except Exception:
                # Silent exit on errors to avoid crashing the server
                return

        t = threading.Thread(target=_runner, name="vllm-demo-seq", daemon=True)
        t.start()

    # ---- Batch apply with transactional semantics ----
    def apply_plan(self, plan: Any, shadow_mode: bool = False) -> tuple[bool, Optional[str]]:
        """Apply a plan transactionally.

        - Iterates actions and applies via execute_action.
        - Records actions for rollback (undo implied by heuristics or engine hooks).
        - On failure and when not in shadow_mode, attempts rollback and returns error.
        - Shard-consistency: all-or-nothing semantics across the entire plan. If any
          action fails, we revert the entire plan's effects to keep shard groups
          consistent. Future versions may use a grouping key (e.g., 'shard_group') to
          coordinate subsets, but at L3 we keep plan-level atomicity.

        Returns: (ok: bool, error: Optional[str])
        """
        try:
            # Normalize actions list from Plan dataclass or dict
            actions = []
            if hasattr(plan, "actions"):
                # Plan dataclass with Action objects exposing .action_type/.target/.params
                for a in plan.actions or []:
                    actions.append({
                        "action_type": getattr(a.action_type, "value", str(getattr(a, "action_type", "")).upper()),
                        "sequence_id": getattr(getattr(a, "target", None), "sequence_id", ""),
                        "start_token": getattr(getattr(a, "target", None), "start_token", 0) or 0,
                        "end_token": getattr(getattr(a, "target", None), "end_token", 0) or 0,
                        **(getattr(a, "params", None) or {}),
                    })
            else:
                # Dict-like
                actions = list((plan or {}).get("actions", []))

            applied: List[Dict[str, Any]] = []
            for act in actions:
                ok = self.execute_action(act)
                applied.append(act)
                if not ok and not shadow_mode:
                    # rollback and report failure
                    self._rollback_applied(applied)
                    return False, f"Failed to apply action: {act.get('action_type')} on {act.get('sequence_id')}"

            return True, None
        except Exception as e:
            try:
                self._rollback_applied(actions)
            except Exception:
                pass
            return False, str(e)

    def _rollback_applied(self, applied_actions: List[Dict[str, Any]]) -> None:
        """Best-effort rollback using internal estimate when NVML is not present.

        For actions that reduced HBM usage internally, we add the delta back.
        """
        # If NVML is present, we cannot directly manipulate device memory, so we
        # just clear the internal log. When NVML is absent, restore estimate.
        if self._nvml_memory_gb():
            # Clear logged actions; real engine hooks would undo here in a later phase
            self._action_log.clear()
            return

        used_logs = False
        # Prefer undo_log derived from engine events if available
        if self._undo_log:
            try:
                for undo in reversed(self._undo_log):
                    if undo.get("kind") == "hbm_add_back":
                        self._est_hbm_used_gb = max(0.0, self._est_hbm_used_gb + float(undo.get("gb", 0.0)))
                        used_logs = True
            finally:
                self._undo_log.clear()

        # Next, prefer exact deltas from our action log (captures governor-limited spans)
        if self._action_log:
            try:
                for rec in reversed(self._action_log):
                    gb = float(rec.get("delta_hbm_gb", 0.0) or 0.0)
                    if gb > 0:
                        self._est_hbm_used_gb = max(0.0, self._est_hbm_used_gb + gb)
                        used_logs = True
            finally:
                self._action_log.clear()

        # Finally, reconstruct deltas heuristically if no logs were present
        if not used_logs:
            for act in reversed(applied_actions or []):
                atype = (act.get("action_type") or act.get("type") or "").upper()
                seq = str(act.get("sequence_id", ""))
                start = int(act.get("start_token", 0) or 0)
                end = int(act.get("end_token", 0) or 0)
                factor = float(act.get("factor", act.get("scale", 0.5)) or 0.5)
                delta = 0.0
                if atype == "QUANTIZE":
                    # Adding back the saved amount
                    token_span = max(0, end - start)
                    bytes_per_token = float(self.config.get("bytes_per_token") or 0.0002)
                    delta = token_span * bytes_per_token * (1.0 - factor)
                elif atype == "OFFLOAD":
                    token_span = max(0, end - start)
                    bytes_per_token = float(self.config.get("bytes_per_token") or 0.0002)
                    delta = token_span * bytes_per_token
                elif atype == "EVICT":
                    token_span = max(0, end - start)
                    bytes_per_token = float(self.config.get("bytes_per_token") or 0.0002)
                    delta = 0.5 * token_span * bytes_per_token

                if delta > 0:
                    self._est_hbm_used_gb = max(0.0, self._est_hbm_used_gb + delta)
        self._action_log.clear()
