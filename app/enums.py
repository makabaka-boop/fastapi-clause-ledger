import enum


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProcessStatus(str, enum.Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"


TERMINAL_PROCESS_STATUSES = frozenset(
    {ProcessStatus.REJECTED.value, ProcessStatus.RESOLVED.value}
)
UNRESOLVED_PROCESS_STATUSES = frozenset(
    {ProcessStatus.OPEN.value, ProcessStatus.ACCEPTED.value}
)


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ImportMode(str, enum.Enum):
    SKIP_EXISTING = "skip_existing"
    UPDATE_EXISTING = "update_existing"
