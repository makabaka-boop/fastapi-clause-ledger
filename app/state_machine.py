from __future__ import annotations

from app.enums import ProcessStatus
from app.exceptions import StateTransitionError


ALLOWED_TRANSITIONS: dict[ProcessStatus, set[ProcessStatus]] = {
    ProcessStatus.OPEN: {ProcessStatus.ACCEPTED, ProcessStatus.REJECTED},
    ProcessStatus.ACCEPTED: {ProcessStatus.REJECTED, ProcessStatus.RESOLVED},
    ProcessStatus.REJECTED: {ProcessStatus.RESOLVED},
    ProcessStatus.RESOLVED: set(),
}


MANDATORY_RECORD_TRANSITIONS: set[tuple[ProcessStatus, ProcessStatus]] = {
    (ProcessStatus.OPEN, ProcessStatus.ACCEPTED),
    (ProcessStatus.OPEN, ProcessStatus.REJECTED),
    (ProcessStatus.ACCEPTED, ProcessStatus.RESOLVED),
}


def validate_transition(
    current: ProcessStatus,
    target: ProcessStatus,
) -> bool:
    if current == target:
        raise StateTransitionError(
            "Target status is the same as current status",
            details={"current_status": current.value, "target_status": target.value},
        )

    if current == ProcessStatus.RESOLVED:
        raise StateTransitionError(
            "Cannot transition away from resolved status",
            details={"current_status": current.value, "target_status": target.value},
        )

    if target == ProcessStatus.OPEN and current in (
        ProcessStatus.REJECTED,
        ProcessStatus.RESOLVED,
    ):
        raise StateTransitionError(
            "rejected/resolved comments cannot be moved back to open",
            details={"current_status": current.value, "target_status": target.value},
        )

    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise StateTransitionError(
            f"Invalid status transition from {current.value} to {target.value}",
            details={"current_status": current.value, "target_status": target.value},
        )

    return True


def requires_processing_record(current: ProcessStatus, target: ProcessStatus) -> bool:
    return (current, target) in MANDATORY_RECORD_TRANSITIONS
