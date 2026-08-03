"""领域常量与枚举定义。"""

RISK_LEVELS = ("low", "medium", "high", "critical")

PROCESS_STATUSES = ("open", "accepted", "rejected", "resolved")

DOCUMENT_STATUSES = ("draft", "in_review", "approved", "archived")

IMPORT_MODES = ("skip_existing", "update_existing")

# 风险等级排序（用于计算条款最高风险）
RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# 看板口径中的"高风险"
HIGH_RISK_LEVELS = ("high", "critical")
