"""
Action Executor for KV-OptKit.

This module provides the ActionExecutor class which is responsible for executing
actions against the KV cache in a transactional manner, with support for rollback.
"""
from typing import Dict, List, Optional, Any, Tuple, TypeVar, Generic, Type
from dataclasses import dataclass, field
import time
import logging

from ..adapters.base import BaseAdapter
from .actions import Action, ActionResult, Plan

logger = logging.getLogger(__name__)

# Type variable for the adapter type
A = TypeVar('A', bound=BaseAdapter)


@dataclass
class TransactionLogEntry:
    """Represents an entry in the transaction log."""
    action: Action
    timestamp: float = field(default_factory=time.time)
    success: bool = False
    result: Optional[Dict[str, Any]] = None
    pre_state: Optional[Dict[str, Any]] = None
    post_state: Optional[Dict[str, Any]] = None


class ActionExecutor(Generic[A]):
    """
    Executes actions against a KV cache adapter with transaction support.
    
    This class provides methods to execute individual actions or entire plans,
    with support for atomic transactions and rollback on failure.
    """
    
    def __init__(self, adapter: A):
        """
        Initialize the ActionExecutor with a KV cache adapter.
        
        Args:
            adapter: The adapter to use for executing actions
        """
        self.adapter = adapter
        self._transaction_log: List[TransactionLogEntry] = []
        self._in_transaction = False
        self._last_error: Optional[str] = None
    
    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message, if any."""
        return self._last_error
    
    def begin_transaction(self) -> bool:
        """
        Begin a new transaction.
        
        Returns:
            bool: True if a new transaction was started, False if a transaction is already in progress
        """
        if self._in_transaction:
            logger.warning("Transaction already in progress")
            return False
            
        self._transaction_log = []
        self._in_transaction = True
        self._last_error = None
        logger.debug("Transaction started")
        return True
    
    def commit(self) -> bool:
        """
        Commit the current transaction.
        
        Returns:
            bool: True if the transaction was committed, False if no transaction was active
        """
        if not self._in_transaction:
            logger.warning("No transaction in progress to commit")
            return False
            
        self._transaction_log = []
        self._in_transaction = False
        logger.debug("Transaction committed")
        return True
    
    def rollback(self) -> bool:
        """
        Roll back the current transaction.
        
        Returns:
            bool: True if the rollback was successful, False otherwise
        """
        if not self._in_transaction:
            logger.warning("No transaction in progress to roll back")
            return False
            
        logger.info(f"Rolling back {len(self._transaction_log)} actions")
        success = True
        
        # Roll back in reverse order
        for entry in reversed(self._transaction_log):
            if entry.success and entry.pre_state is not None:
                try:
                    self._restore_state(entry.action, entry.pre_state)
                    logger.debug(f"Rolled back action: {entry.action.kind}")
                except Exception as e:
                    success = False
                    logger.error(f"Error rolling back action {entry.action.id}: {e}")
                    self._last_error = f"Rollback failed: {str(e)}"
        
        self._in_transaction = False
        self._transaction_log = []
        
        if success:
            logger.debug("Rollback completed successfully")
        else:
            logger.error("Rollback completed with errors")
            
        return success
    
    def execute_plan(self, plan: Plan) -> ActionResult:
        """
        Execute a plan of actions within a transaction.
        
        Args:
            plan: The Plan containing actions to execute
            
        Returns:
            ActionResult: The result of the plan execution
        """
        if not plan.actions:
            return ActionResult(True, "No actions to execute")
            
        self.begin_transaction()
        logger.info(f"Executing plan with {len(plan.actions)} actions")
        
        results = []
        try:
            for action in plan.actions:
                result = self.execute_action(action)
                results.append((action, result))
                
                if not result.success:
                    self.rollback()
                    error_msg = f"Action {action.kind} failed: {result.message}"
                    logger.error(error_msg)
                    return ActionResult(False, error_msg, {
                        "failed_action": action.id,
                        "action_results": [r.dict() for _, r in results]
                    })
            
            self.commit()
            return ActionResult(
                True,
                f"Successfully executed {len(plan.actions)} actions",
                {"action_results": [r.dict() for _, r in results]}
            )
            
        except Exception as e:
            self.rollback()
            error_msg = f"Error executing plan: {str(e)}"
            logger.exception(error_msg)
            return ActionResult(False, error_msg)
    
    def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a single action.
        
        Args:
            action: The Action to execute
            
        Returns:
            ActionResult: The result of the action
        """
        if not self._in_transaction:
            self.begin_transaction()
            auto_commit = True
        else:
            auto_commit = False
            
        entry = TransactionLogEntry(action=action)
        
        try:
            # Capture pre-state
            entry.pre_state = self._capture_state(action)
            
            # Execute the action
            if action.kind == "EVICT":
                result = self.adapter.evict(
                    action.target.seq_id,
                    action.target.start_token,
                    action.target.end_token
                )
            elif action.kind == "OFFLOAD":
                result = self.adapter.offload(
                    action.target.seq_id,
                    action.target.start_token,
                    action.target.end_token
                )
            elif action.kind == "QUANTIZE":
                result = self.adapter.quantize(
                    action.target.seq_id,
                    action.target.start_token,
                    action.target.end_token,
                    action.params.get("factor", 0.5)
                )
            elif action.kind == "DEQUANTIZE":
                result = self.adapter.dequantize(
                    action.target.seq_id,
                    action.target.start_token,
                    action.target.end_token
                )
            else:
                raise ValueError(f"Unknown action type: {action.kind}")
            
            # Update entry with results
            entry.success = result.get("success", False)
            entry.result = result
            entry.post_state = self._capture_state(action)
            
            if not entry.success:
                raise RuntimeError(result.get("message", "Action failed with no error message"))
            
            # Log the action
            if self._in_transaction:
                self._transaction_log.append(entry)
            
            logger.debug(f"Executed {action.kind} on {action.target.seq_id} "
                       f"tokens {action.target.start_token}-{action.target.end_token}")
            
            return ActionResult(
                True,
                f"Successfully executed {action.kind}",
                result
            )
            
        except Exception as e:
            entry.success = False
            entry.result = {"error": str(e)}
            logger.error(f"Error executing {action.kind}: {str(e)}", exc_info=True)
            
            if self._in_transaction:
                self._transaction_log.append(entry)
                
            return ActionResult(
                False,
                f"Failed to execute {action.kind}: {str(e)}",
                {"error": str(e)}
            )
            
        finally:
            if auto_commit and self._in_transaction:
                if entry.success:
                    self.commit()
                else:
                    self.rollback()
    
    def _capture_state(self, action: Action) -> Dict[str, Any]:
        """
        Capture the current state of the target of an action.
        
        Args:
            action: The action to capture state for
            
        Returns:
            Dict containing the captured state
        """
        # For now, we'll just capture the sequence state
        # In a real implementation, this would capture more detailed state
        # needed for rollback
        return {
            "sequence_id": action.target.seq_id,
            "start_token": action.target.start_token,
            "end_token": action.target.end_token,
            "action_type": action.kind,
            "timestamp": time.time()
        }
    
    def _restore_state(self, action: Action, state: Dict[str, Any]) -> bool:
        """
        Restore the state of the target of an action.
        
        Args:
            action: The action to restore state for
            state: The state to restore
            
        Returns:
            bool: True if the state was restored successfully
        """
        # This is a simplified implementation
        # In a real system, this would restore the exact state including
        # quantization factors, tier assignments, etc.
        logger.debug(f"Restoring state for action {action.id}")
        return True
