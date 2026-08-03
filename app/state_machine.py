"""Review process-status state machine.

Rules from the spec:
  * open      -> accepted | rejected   (requires a process record)
  * accepted  -> resolved              (requires a process record)
  * rejected  is terminal: cannot go back to open
  * resolved  is terminal: cannot go back to open (no rollback)
  * transitions not listed here are rejected

The ``requires_record`` set marks transitions that MUST be accompanied by a
process record write. The router refuses a status change on those transitions
unless the caller also supplies operator/note details.
"""

from __future__ import annotations

from .enums import ProcessStatus
from .exceptions import StateTransitionError

# Allowed transitions: from -> set(to)
_ALLOWED: dict[ProcessStatus, set[ProcessStatus]] = {
    ProcessStatus.open: {ProcessStatus.accepted, ProcessStatus.rejected},
    ProcessStatus.accepted: {ProcessStatus.resolved},
    ProcessStatus.rejected: set(),
    ProcessStatus.resolved: set(),  # terminal — no rollback permitted
}

# Transitions that must be journaled in process_records.
_REQUIRES_RECORD: set[tuple[ProcessStatus, ProcessStatus]] = {
    (ProcessStatus.open, ProcessStatus.accepted),
    (ProcessStatus.open, ProcessStatus.rejected),
    (ProcessStatus.accepted, ProcessStatus.resolved),
}


def can_transition(current: ProcessStatus, target: ProcessStatus) -> bool:
    return target in _ALLOWED.get(current, set())


def requires_record(current: ProcessStatus, target: ProcessStatus) -> bool:
    return (current, target) in _REQUIRES_RECORD


def assert_transition(current: ProcessStatus, target: ProcessStatus) -> None:
    """Raise :class:`StateTransitionError` when ``current -> target`` is illegal."""
    if current == target:
        raise StateTransitionError(
            f"Comment is already in status '{current.value}'.",
            details={"from_status": current.value, "to_status": target.value},
        )
    if current == ProcessStatus.resolved:
        raise StateTransitionError(
            "A resolved comment cannot be rolled back.",
            details={"from_status": current.value, "to_status": target.value},
        )
    if not can_transition(current, target):
        raise StateTransitionError(
            f"Cannot move a comment from '{current.value}' to '{target.value}'.",
            details={"from_status": current.value, "to_status": target.value},
        )
