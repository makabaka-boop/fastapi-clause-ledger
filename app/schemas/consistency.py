from typing import Any, Dict, List

from pydantic import BaseModel


class ConsistencyCheckItem(BaseModel):
    check_name: str
    passed: bool
    issue_count: int
    details: List[Dict[str, Any]] = []


class ConsistencyReport(BaseModel):
    all_passed: bool
    total_checks: int
    failed_checks: int
    checks: List[ConsistencyCheckItem]
