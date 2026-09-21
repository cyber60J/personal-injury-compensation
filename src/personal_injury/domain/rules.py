from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, Optional

from .models import CaseType


@dataclass(frozen=True)
class RuleSet:
    """可审计的案由规则版本。规则对象只描述选择，不执行数据库或网络操作。"""

    case_type: CaseType
    version: str
    effective_from: date
    effective_to: Optional[date] = None
    source_keys: tuple[str, ...] = ()
    calculator_config: Dict[str, float] = field(default_factory=dict)
    features: frozenset[str] = frozenset()

    def applies_on(self, as_of: date) -> bool:
        return self.effective_from <= as_of and (
            self.effective_to is None or as_of <= self.effective_to
        )


DEFAULT_CALCULATOR_CONFIG = {
    "住院伙食补助费标准": 100.0,
    "营养费标准": 50.0,
    "交通费标准": 20.0,
    "护理费标准": 150.0,
    "上一年度城镇居民人均可支配收入": 50000.0,
    "上一年度城镇居民人均消费支出": 30000.0,
}


RULE_SETS: tuple[RuleSet, ...] = (
    RuleSet(
        case_type=CaseType.TRAFFIC_ACCIDENT,
        version="traffic-2026-ii",
        effective_from=date(2026, 6, 30),
        source_keys=("personal_injury_interpretation", "traffic_interpretation_ii"),
        calculator_config=DEFAULT_CALCULATOR_CONFIG,
        features=frozenset({"traffic_interpretation_ii"}),
    ),
    RuleSet(
        case_type=CaseType.TRAFFIC_ACCIDENT,
        version="traffic-2022",
        effective_from=date(2022, 5, 1),
        effective_to=date(2026, 6, 29),
        source_keys=("personal_injury_interpretation",),
        calculator_config=DEFAULT_CALCULATOR_CONFIG,
    ),
    RuleSet(
        case_type=CaseType.EMPLOYMENT_SERVICE,
        version="employment-service-2022",
        effective_from=date(2022, 5, 1),
        source_keys=("personal_injury_interpretation",),
        calculator_config=DEFAULT_CALCULATOR_CONFIG,
    ),
    RuleSet(
        case_type=CaseType.GENERAL_PERSONAL_INJURY,
        version="general-personal-injury-2022",
        effective_from=date(2022, 5, 1),
        source_keys=("personal_injury_interpretation",),
        calculator_config=DEFAULT_CALCULATOR_CONFIG,
    ),
)


def resolve_rule_set(
    case_type: CaseType,
    as_of: Optional[date] = None,
    *,
    incident_date: Optional[date] = None,
    final_judgment_date: Optional[date] = None,
) -> RuleSet:
    """Resolve the supported rule version for a case.

    ``as_of`` is the date on which the legal assessment is made.  It is
    deliberately independent from the statistical year.  The 2026 traffic
    interpretation applies to cases that were not already final before its
    effective date, so a pre-effective final judgment keeps the earlier rule.
    """
    effective_date = as_of or date.today()
    base_rule_date = incident_date or effective_date
    if base_rule_date < date(2022, 5, 1):
        raise ValueError("当前版本尚未内置2022年5月1日前侵权行为的完整规则，请由律师选择历史规则")

    if case_type == CaseType.TRAFFIC_ACCIDENT:
        traffic_ii_date = date(2026, 6, 30)
        was_final_before_traffic_ii = (
            final_judgment_date is not None and final_judgment_date < traffic_ii_date
        )
        if effective_date >= traffic_ii_date and not was_final_before_traffic_ii:
            return next(rule for rule in RULE_SETS if rule.version == "traffic-2026-ii")
        return next(rule for rule in RULE_SETS if rule.version == "traffic-2022")

    candidates = [
        rule for rule in RULE_SETS
        if rule.case_type == case_type and rule.applies_on(effective_date)
    ]
    if not candidates:
        raise ValueError(f"没有找到{case_type.value}在{effective_date.isoformat()}适用的规则")
    return max(candidates, key=lambda rule: rule.effective_from)


def list_rule_sets(case_type: Optional[CaseType] = None) -> Iterable[RuleSet]:
    if case_type is None:
        return RULE_SETS
    return tuple(rule for rule in RULE_SETS if rule.case_type == case_type)
