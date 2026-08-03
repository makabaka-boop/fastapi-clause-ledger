"""审阅意见处理状态机。

合法流转:
    open     -> accepted | rejected
    accepted -> resolved
其余流转一律禁止；resolved 为终态，不允许回退。
"""

from typing import Optional, Tuple

from .constants import PROCESS_STATUSES
from .exceptions import InvalidStatusTransitionError

_ALLOWED_TRANSITIONS = {
    "open": {"accepted", "rejected"},
    "accepted": {"resolved"},
    "rejected": set(),
    "resolved": set(),
}

# 必须写入处理记录的流转
_MANDATORY_RECORD_TRANSITIONS: Tuple[Tuple[str, str], ...] = (
    ("open", "accepted"),
    ("open", "rejected"),
    ("accepted", "resolved"),
)


def validate_transition(from_status: str, to_status: str) -> None:
    """校验状态流转是否合法，非法时抛出 InvalidStatusTransitionError。"""
    if to_status not in PROCESS_STATUSES:
        raise InvalidStatusTransitionError(
            f"非法的目标处理状态: {to_status}",
            details={"from_status": from_status, "to_status": to_status},
        )
    if to_status not in _ALLOWED_TRANSITIONS.get(from_status, set()):
        raise InvalidStatusTransitionError(
            f"不允许从 {from_status} 流转到 {to_status}",
            details={"from_status": from_status, "to_status": to_status},
        )


def requires_process_record(from_status: str, to_status: str) -> bool:
    """该流转是否强制要求写入处理记录。"""
    return (from_status, to_status) in _MANDATORY_RECORD_TRANSITIONS
