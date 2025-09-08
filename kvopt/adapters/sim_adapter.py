"""
SIM Adapter for KV-OptKit.

This module provides a simulation of a KV cache that can be used for testing and development.
It tracks segments of sequences with different storage tiers and quantization levels.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set, Any
import time
import math
import json

from .base import Adapter
from kvopt.server.metrics import (
    governor_throttle_events,
    offload_governed_bytes,
    offload_tick_cap_bytes as _gauge_offload_tick_cap_bytes,
)


class StorageTier(str, Enum):
    """Storage tiers for KV cache segments."""
    HBM = "HBM"  # High Bandwidth Memory (fast, expensive)
    DDR = "DDR"  # System Memory (slower, cheaper)


@dataclass
class SimSegment:
    """Represents a segment of a sequence in the KV cache."""
    start_token: int
    end_token: int
    tier: StorageTier = StorageTier.HBM
    qscale: float = 1.0  # 1.0 = full precision, <1.0 = quantized
    last_accessed: float = field(default_factory=time.time)
    
    @property
    def num_tokens(self) -> int:
        """Number of tokens in this segment."""
        return self.end_token - self.start_token + 1
    
    def overlaps(self, other: 'SimSegment') -> bool:
        """Check if this segment overlaps with another."""
        return (self.start_token <= other.end_token and 
                self.end_token >= other.start_token)


class SimAdapter(Adapter):
    """
    SIM adapter that simulates a KV cache with different storage tiers.
    
    This adapter tracks sequences as collections of segments, where each segment
    can be in a different storage tier and have different quantization levels.
    """
    
    _instance = None
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the SIM adapter with configuration."""
        super().__init__()
        self.sequences: Dict[str, List[SimSegment]] = {}
        self.config = self._validate_config(config)
        self._hbm_capacity_gb = float(self.config.get("hbm_capacity_gb", 80.0))
        # Ensure bytes_per_token is a valid float defaulting to 0.0001 GB/token
        bpt = self.config.get("bytes_per_token", 0.0001)
        try:
            self._bytes_per_token = float(bpt if bpt is not None else 0.0001)
        except Exception:
            self._bytes_per_token = 0.0001
        self._hbm_used_gb = 0.0
        self._rollback_log: List[Dict] = []
        # Governor: per-tick cap (bytes) and window tracking
        # Env overrides (handy for demos)
        import os
        env_cap = os.getenv("KVOPT_OFFLOAD_TICK_CAP_BYTES")
        env_tick = os.getenv("KVOPT_OFFLOAD_TICK_MS")
        self._gov_cap_bytes: float = float(env_cap if env_cap else self.config.get("offload_tick_cap_bytes", 10 * 1024 * 1024))  # 10 MB/tick default
        self._gov_tick_ms: int = int(env_tick if env_tick else self.config.get("offload_tick_ms", 1000))  # 1s tick
        self._gov_window_start_ms: float = time.time() * 1000.0
        self._gov_used_bytes_this_window: float = 0.0
        try:
            _gauge_offload_tick_cap_bytes.set(self._gov_cap_bytes)
        except Exception:
            pass
        
        # Set this instance as the singleton for both SimAdapter and base Adapter
        SimAdapter._instance = self
        Adapter._instance = self
        
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and set default configuration values."""
        defaults = {
            "hbm_capacity_gb": 80.0,
            "bytes_per_token": 0.0001,  # GB per token
            "keep_recent_tokens": 1024,
            "quantization_factor": 0.5,
            # Governor defaults
            "offload_tick_cap_bytes": 10 * 1024 * 1024,  # 10 MB per tick
            "offload_tick_ms": 1000,
        }
        # Only override defaults with values that are not None
        sanitized = {k: v for k, v in (config or {}).items() if v is not None}
        return {**defaults, **sanitized}

    def capabilities(self) -> set:
        """SIM supports full capability set for testing (L3)."""
        return {"EVICT", "OFFLOAD", "QUANTIZE", "REUSE"}
    
    def _calculate_hbm_usage(self) -> float:
        """Calculate current HBM usage in GB."""
        total = 0.0
        bpt = float(self._bytes_per_token if self._bytes_per_token else 0.0001)
        for segments in self.sequences.values():
            for seg in segments:
                if seg.tier == StorageTier.HBM:
                    q = float(seg.qscale if seg.qscale else 1.0)
                    total += seg.num_tokens * bpt * q
        return total
    
    def _find_segment(self, seq_id: str, token_idx: int) -> Optional[Tuple[int, SimSegment]]:
        """Find the segment containing the given token index, if any."""
        if seq_id not in self.sequences:
            return None
            
        for i, seg in enumerate(self.sequences[seq_id]):
            if seg.start_token <= token_idx <= seg.end_token:
                return i, seg
        return None
    
    def _split_segment(self, seq_id: str, seg_idx: int, at_token: int) -> None:
        """Split a segment at the given token index."""
        if seq_id not in self.sequences:
            return
            
        seg = self.sequences[seq_id][seg_idx]
        if seg.start_token < at_token < seg.end_token:
            # Create a new segment for the right part
            right_seg = SimSegment(
                start_token=at_token + 1,
                end_token=seg.end_token,
                tier=seg.tier,
                qscale=seg.qscale,
                last_accessed=seg.last_accessed
            )
            # Update the original segment
            seg.end_token = at_token
            # Insert the new segment
            self.sequences[seq_id].insert(seg_idx + 1, right_seg)
    
    def _merge_adjacent_segments(self, seq_id: str) -> None:
        """Merge adjacent segments with the same tier and quantization."""
        if seq_id not in self.sequences or len(self.sequences[seq_id]) < 2:
            return
            
        i = 0
        while i < len(self.sequences[seq_id]) - 1:
            current = self.sequences[seq_id][i]
            next_seg = self.sequences[seq_id][i + 1]
            
            if (current.tier == next_seg.tier and 
                current.qscale == next_seg.qscale and
                current.end_token + 1 == next_seg.start_token):
                # Merge the segments
                current.end_token = next_seg.end_token
                current.last_accessed = max(current.last_accessed, next_seg.last_accessed)
                del self.sequences[seq_id][i + 1]
            else:
                i += 1
    
    def submit_sequence(self, seq_id: str, tokens: int) -> bool:
        """Submit a new sequence to the KV cache."""
        # Validate inputs
        if not isinstance(seq_id, str) or not seq_id:
            raise ValueError("seq_id must be a non-empty string")
        if not isinstance(tokens, int) or tokens <= 0:
            raise ValueError("tokens must be a positive integer")
        if seq_id in self.sequences:
            return False
            
        # Create a single segment for the new sequence
        segment = SimSegment(
            start_token=0,
            end_token=tokens - 1,
            tier=StorageTier.HBM,
            qscale=1.0
        )
        self.sequences[seq_id] = [segment]
        self._hbm_used_gb = self._calculate_hbm_usage()
        return True
    
    def finish_sequence(self, seq_id: str) -> bool:
        """Remove a sequence from the KV cache."""
        if seq_id not in self.sequences:
            return False
            
        del self.sequences[seq_id]
        self._hbm_used_gb = self._calculate_hbm_usage()
        return True
    
    def get_telemetry(self) -> Dict[str, Any]:
        """Get current telemetry data."""
        total_tokens = 0
        hbm_tokens = 0
        
        for segments in self.sequences.values():
            for seg in segments:
                total_tokens += seg.num_tokens
                if seg.tier == StorageTier.HBM:
                    hbm_tokens += seg.num_tokens * seg.qscale
        
        # Synthetic latency model for demo purposes: increases with sequences and utilization
        utilization = (self._hbm_used_gb / self._hbm_capacity_gb) if self._hbm_capacity_gb else 0.0
        seq_count = len(self.sequences)
        p95_latency_ms = float(min(2000.0, 10.0 + seq_count * 5.0 + utilization * 500.0))

        return {
            "hbm_used_gb": self._hbm_used_gb,
            "hbm_capacity_gb": self._hbm_capacity_gb,
            "hbm_utilization": utilization,
            "total_sequences": len(self.sequences),
            "total_tokens": total_tokens,
            "hbm_tokens": hbm_tokens,
            "p95_latency_ms": p95_latency_ms,
            "timestamp": time.time()
        }
        
    def execute_action(self, action: Dict[str, Any]) -> bool:
        """Execute an optimization action."""
        action_type = action.get("action_type")
        seq_id = action.get("sequence_id")
        
        if not action_type or not seq_id:
            return False
            
        start_token = action.get("start_token", 0)
        end_token = action.get("end_token", 0)
        
        try:
            if action_type == "EVICT":
                result = self.evict(seq_id, start_token, end_token)
                return result.get("success", False)
                
            elif action_type == "OFFLOAD":
                result = self.offload(seq_id, start_token, end_token)
                return result.get("success", False)
                
            elif action_type == "QUANTIZE":
                factor = action.get("factor", 0.5)
                result = self.quantize(seq_id, start_token, end_token, factor)
                return result.get("success", False)
                
            elif action_type == "DEQUANTIZE":
                result = self.dequantize(seq_id, start_token, end_token)
                return result.get("success", False)
            
            elif action_type == "REUSE":
                # No-op for simulator; treat as a successful hint
                return True
                
            return False
            
        except Exception as e:
            print(f"Error executing action {action_type}: {e}")
            return False
            
    def get_sequences(self) -> List[Dict[str, Any]]:
        """Get information about all sequences in the KV cache."""
        sequences = []
        
        for seq_id, segments in self.sequences.items():
            seq_info = {
                "sequence_id": seq_id,
                "segments": [],
                "total_tokens": 0,
                "hbm_tokens": 0,
                "ddr_tokens": 0
            }
            
            for seg in segments:
                seg_info = {
                    "start_token": seg.start_token,
                    "end_token": seg.end_token,
                    "tier": seg.tier.value,
                    "qscale": seg.qscale,
                    "last_accessed": seg.last_accessed
                }
                seq_info["segments"].append(seg_info)
                
                num_tokens = seg.num_tokens
                seq_info["total_tokens"] += num_tokens
                
                if seg.tier == StorageTier.HBM:
                    seq_info["hbm_tokens"] += num_tokens * seg.qscale
                else:
                    seq_info["ddr_tokens"] += num_tokens
            
            sequences.append(seq_info)
            
        return sequences
    
    # --- Phase 2 Methods ---
    
    # Transaction support: snapshot and restore the entire adapter state
    def snapshot_state(self) -> Dict[str, Any]:
        """Create a deep snapshot of the simulator state for rollback."""
        snap_sequences: Dict[str, List[Dict[str, Any]]] = {}
        for seq_id, segs in self.sequences.items():
            snap_sequences[seq_id] = [
                {
                    "start_token": seg.start_token,
                    "end_token": seg.end_token,
                    "tier": seg.tier.value,
                    "qscale": float(seg.qscale),
                    "last_accessed": float(seg.last_accessed),
                }
                for seg in segs
            ]
        return {
            "sequences": snap_sequences,
            "hbm_used_gb": float(self._hbm_used_gb),
        }

    def restore_state(self, snapshot: Dict[str, Any]) -> None:
        """Restore the simulator state from a snapshot."""
        seqs = snapshot.get("sequences", {})
        restored: Dict[str, List[SimSegment]] = {}
        for seq_id, segdicts in seqs.items():
            restored[seq_id] = []
            for sd in segdicts:
                restored[seq_id].append(
                    SimSegment(
                        start_token=int(sd["start_token"]),
                        end_token=int(sd["end_token"]),
                        tier=StorageTier(sd["tier"]),
                        qscale=float(sd.get("qscale", 1.0)),
                        last_accessed=float(sd.get("last_accessed", time.time())),
                    )
                )
        self.sequences = restored
        # Recompute to be safe
        self._hbm_used_gb = self._calculate_hbm_usage()
    
    def evict(self, seq_id: str, start_token: int, end_token: int) -> Dict[str, Any]:
        """Evict tokens from a sequence."""
        if seq_id not in self.sequences:
            return {"success": False, "message": f"Sequence {seq_id} not found"}
        
        # Split segments at the eviction boundaries
        self._split_segment(seq_id, 0, start_token - 1)
        self._split_segment(seq_id, 0, end_token)
        
        # Remove segments within the eviction range
        new_segments = []
        removed_tokens = 0
        
        for seg in self.sequences[seq_id]:
            if seg.end_token < start_token or seg.start_token > end_token:
                new_segments.append(seg)
            else:
                # This segment is being evicted
                if seg.tier == StorageTier.HBM:
                    removed_tokens += seg.num_tokens * seg.qscale
        
        self.sequences[seq_id] = new_segments
        self._hbm_used_gb = self._calculate_hbm_usage()
        
        return {
            "success": True,
            "removed_tokens": removed_tokens,
            "hbm_used_gb": self._hbm_used_gb
        }
    
    def offload(self, seq_id: str, start_token: int, end_token: int) -> Dict[str, Any]:
        """Offload tokens to DDR."""
        if seq_id not in self.sequences:
            return {"success": False, "message": f"Sequence {seq_id} not found"}

        # If end_token is 0 or not specified, default to the end of the sequence.
        if not end_token:
            end_token = max(seg.end_token for seg in self.sequences.get(seq_id, []))

        # Split segments at the offload boundaries
        self._split_segment(seq_id, 0, start_token - 1)
        self._split_segment(seq_id, 0, end_token)

        # Find and update segments within the offload range
        offloaded_tokens = 0
        governed_bytes = 0.0
        throttled = False

        # Governor window maintenance
        now_ms = time.time() * 1000.0
        if now_ms - self._gov_window_start_ms >= float(self._gov_tick_ms):
            # reset window
            self._gov_window_start_ms = now_ms
            self._gov_used_bytes_this_window = 0.0
        remaining_cap = max(0.0, float(self._gov_cap_bytes) - float(self._gov_used_bytes_this_window))
        
        for seg in self.sequences[seq_id]:
            if not (seg.start_token >= start_token and seg.end_token <= end_token):
                continue
            if seg.tier != StorageTier.HBM:
                continue
            # bytes for this whole segment at current scale
            seg_bytes = float(seg.num_tokens) * float(seg.qscale) * float(self._bytes_per_token) * (1024**3)
            if remaining_cap <= 0.0:
                # no capacity left: govern entire segment
                governed_bytes += seg_bytes
                throttled = True
                continue
            if seg_bytes <= remaining_cap:
                # fully offload
                seg.tier = StorageTier.DDR
                offloaded_tokens += seg.num_tokens * seg.qscale
                remaining_cap -= seg_bytes
                self._gov_used_bytes_this_window += seg_bytes
            else:
                # partial move within cap: split segment to match allowed bytes
                tokens_allowed = int(max(1, math.floor((remaining_cap / (1024**3)) / (float(self._bytes_per_token) * float(seg.qscale)))))
                # Edge case: ensure we don't exceed segment size
                tokens_allowed = min(tokens_allowed, seg.num_tokens)
                if tokens_allowed <= 0:
                    governed_bytes += seg_bytes
                    throttled = True
                    remaining_cap = 0.0
                else:
                    # split seg so that left part size == tokens_allowed
                    split_token = seg.start_token + tokens_allowed - 1
                    # Perform split at split_token
                    self._split_segment(seq_id, self.sequences[seq_id].index(seg), split_token)
                    # After split, current seg now ends at split_token, so we can offload it
                    seg.tier = StorageTier.DDR
                    moved_bytes = float(tokens_allowed) * float(seg.qscale) * float(self._bytes_per_token) * (1024**3)
                    offloaded_tokens += tokens_allowed * seg.qscale
                    self._gov_used_bytes_this_window += moved_bytes
                    remaining_cap = 0.0
                    # The remainder (next segment) will be considered governed in this window
                    throttled = True
                    # Calculate remainder bytes as governed
                    remainder_tokens = (end_token - split_token)
                    if remainder_tokens > 0:
                        governed_bytes += float(remainder_tokens) * float(seg.qscale) * float(self._bytes_per_token) * (1024**3)

        self._hbm_used_gb = self._calculate_hbm_usage()
        self._merge_adjacent_segments(seq_id)

        # Metrics: record governor activity
        try:
            _gauge_offload_tick_cap_bytes.set(self._gov_cap_bytes)
            if throttled:
                governor_throttle_events.inc()
            if governed_bytes > 0:
                offload_governed_bytes.inc(governed_bytes)
        except Exception:
            pass

        return {
            "success": True,
            "offloaded_tokens": offloaded_tokens,
            "hbm_used_gb": self._hbm_used_gb,
            "governed_bytes": governed_bytes,
            "throttled": throttled,
        }
    
    def quantize(self, seq_id: str, start_token: int, end_token: int, factor: float) -> Dict[str, Any]:
        """Quantize tokens to reduce memory usage."""
        if seq_id not in self.sequences:
            return {"success": False, "message": f"Sequence {seq_id} not found"}

        # If end_token is 0 or not specified, default to the end of the sequence.
        if not end_token:
            end_token = max(seg.end_token for seg in self.sequences.get(seq_id, []))
        
        if not (0 < factor < 1.0):
            return {"success": False, "message": f"Invalid quantization factor: {factor}"}
        
        # Split segments at the quantization boundaries
        self._split_segment(seq_id, 0, start_token - 1)
        self._split_segment(seq_id, 0, end_token)
        
        # Find and update segments within the quantization range
        quantized_tokens = 0
        
        for seg in self.sequences[seq_id]:
            if (seg.start_token >= start_token and seg.end_token <= end_token and 
                seg.tier == StorageTier.HBM):
                # Calculate the reduction in memory usage
                old_usage = seg.num_tokens * seg.qscale * self._bytes_per_token
                seg.qscale *= factor
                new_usage = seg.num_tokens * seg.qscale * self._bytes_per_token
                quantized_tokens += (old_usage - new_usage) / self._bytes_per_token
        
        self._hbm_used_gb = self._calculate_hbm_usage()
        self._merge_adjacent_segments(seq_id)
        
        return {
            "success": True,
            "quantized_tokens": quantized_tokens,
            "hbm_used_gb": self._hbm_used_gb,
            "new_qscale": factor
        }
    
    def dequantize(self, seq_id: str, start_token: int, end_token: int) -> Dict[str, Any]:
        """Revert quantization for tokens."""
        if seq_id not in self.sequences:
            return {"success": False, "message": f"Sequence {seq_id} not found"}
        
        # Split segments at the dequantization boundaries
        self._split_segment(seq_id, 0, start_token - 1)
        self._split_segment(seq_id, 0, end_token)
        
        # Find and update segments within the dequantization range
        dequantized_tokens = 0
        
        for seg in self.sequences[seq_id]:
            if (seg.start_token >= start_token and seg.end_token <= end_token and 
                seg.tier == StorageTier.HBM and seg.qscale < 1.0):
                # Calculate the increase in memory usage
                old_usage = seg.num_tokens * seg.qscale * self._bytes_per_token
                seg.qscale = 1.0  # Full precision
                new_usage = seg.num_tokens * seg.qscale * self._bytes_per_token
                dequantized_tokens += (new_usage - old_usage) / self._bytes_per_token
        
        self._hbm_used_gb = self._calculate_hbm_usage()
        self._merge_adjacent_segments(seq_id)
        
        return {
            "success": True,
            "dequantized_tokens": dequantized_tokens,
            "hbm_used_gb": self._hbm_used_gb
        }
    
    def reset(self) -> Dict[str, Any]:
        """Reset the simulator to its initial state."""
        self.sequences = {}
        self._hbm_used_gb = 0.0
        self._rollback_log = []
        return {"success": True, "message": "Simulator reset"}
    
    def get_sequence_state(self, seq_id: str) -> Dict[str, Any]:
        """Get detailed state of a sequence."""
        if seq_id not in self.sequences:
            return {"success": False, "message": f"Sequence {seq_id} not found"}
        
        segments = []
        for seg in self.sequences[seq_id]:
            segments.append({
                "start_token": seg.start_token,
                "end_token": seg.end_token,
                "tier": seg.tier.value,
                "qscale": seg.qscale,
                "last_accessed": seg.last_accessed
            })
        
        return {
            "success": True,
            "sequence_id": seq_id,
            "segments": segments,
            "total_tokens": sum(seg.num_tokens for seg in self.sequences[seq_id])
        }
