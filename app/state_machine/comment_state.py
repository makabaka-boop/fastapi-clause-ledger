from typing import Dict, Set, Tuple

from app.enums import ProcessStatus
from app.exceptions.app_exceptions import InvalidStateTransitionError


ALLOWED_TRANSITIONS: Dict[ProcessStatus, Set[ProcessStatus]] = {
    ProcessStatus.OPEN: {ProcessStatus.ACCEPTED, ProcessStatus.REJECTED},
    ProcessStatus.ACCEPTED: {ProcessStatus.RESOLVED},
    ProcessStatus.REJECTED: set(),
    ProcessStatus.RESOLVED: set(),
}

TRANSITIONS_REQUIRING_RECORD: Set[Tuple[ProcessStatus, ProcessStatus]] = {
    (ProcessStatus.OPEN, ProcessStatus.ACCEPTED),
    (ProcessStatus.OPEN, ProcessStatus.REJECTED),
    (ProcessStatus.ACCEPTED, ProcessStatus.RESOLVED),
}


TERMINAL_STATUSES = {ProcessStatus.RESOLVED, ProcessStatus.REJECTED}


def validate_transition(
    current: ProcessStatus, target: ProcessStatus
) -> None:
    if current in TERMINAL_STATUSES:
        raise InvalidStateTransitionError(
            message="Cannot transition away from a terminal status",
            details={
                "current_status": current.value,
                "target_status": target.value,
                "terminal": True,
            },
        )

    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            message="Invalid process status transition",
            details={
                "current_status": current.value,
                "target_status": target.value,
                "allowed_targets": [s.value for s in allowed],
            },
        )


def requires_record(current: ProcessStatus, target: ProcessStatus) -> bool:
    return (current, target) in TRANSITIONS_REQUIRING_RECORD
