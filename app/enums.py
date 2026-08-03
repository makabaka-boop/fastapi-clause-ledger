"""Shared enumerations and controlled vocabularies.

Keeping these in one place means the Pydantic schemas, the state machine and the
repository layer all agree on the exact set of allowed string values.
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """Lifecycle of a compliance document."""

    draft = "draft"
    under_review = "under_review"
    approved = "approved"
    archived = "archived"


class ClauseType(str, Enum):
    """Category a clause belongs to."""

    obligation = "obligation"
    right = "right"
    prohibition = "prohibition"
    definition = "definition"
    other = "other"


class Importance(str, Enum):
    """How much attention a clause demands."""

    low = "low"
    normal = "normal"
    high = "high"


class RiskLevel(str, Enum):
    """Risk level attached to a review comment (spec-fixed set)."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ProcessStatus(str, Enum):
    """Handling status of a review comment (spec-fixed set)."""

    open = "open"
    accepted = "accepted"
    rejected = "rejected"
    resolved = "resolved"


class ImportMode(str, Enum):
    """Behaviour when an imported clause_no already exists in a document."""

    skip_existing = "skip_existing"
    update_existing = "update_existing"
