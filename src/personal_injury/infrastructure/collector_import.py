from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from personal_injury.infrastructure.database import StatisticalStandardModel


# 这些字段名与 data_collector.DataRecord 的属性保持一致。导入后统一进入
# pending 状态，只有律师或管理员确认后，计算服务才会使用它们。
STANDARD_FIELDS = (
    "urban_disposable_income",
    "urban_consumption_expenditure",
    "urban_non_private_wage",
    "urban_private_wage",
    "service_industry_wage",
    "urban_on_duty_wage",
)

STANDARD_FIELD_ITEMS = {
    "urban_disposable_income": "城镇居民人均可支配收入",
    "urban_consumption_expenditure": "城镇居民人均消费支出",
    "urban_non_private_wage": "城镇非私营单位年平均工资",
    "urban_private_wage": "城镇私营单位年平均工资",
    "service_industry_wage": "居民服务业年平均工资",
    "urban_on_duty_wage": "城镇单位在岗职工年平均工资",
}


def import_collector_status(
    session: Session,
    status_path: str | Path,
) -> int:
    """Import data_collector's JSON status file as unconfirmed standards."""
    payload = json.loads(Path(status_path).read_text(encoding="utf-8"))
    imported = 0
    for record in payload.get("records", []):
        region = record.get("region")
        year = record.get("year")
        if not region or not isinstance(year, int) or isinstance(year, bool):
            continue
        for field_name in STANDARD_FIELDS:
            value = record.get(field_name)
            existing = session.query(StatisticalStandardModel).filter(
                StatisticalStandardModel.region == region,
                StatisticalStandardModel.year == year,
                StatisticalStandardModel.field_name == field_name,
            ).first()
            if existing and existing.status == "approved":
                continue
            item_name = STANDARD_FIELD_ITEMS[field_name]
            evidence = record.get("evidence", {}).get(item_name, {})
            source_record = {
                "collector_status": record.get("status"),
                "collector_error": record.get("error_message"),
                "evidence": evidence,
                "extraction_version": record.get("extraction_version"),
                "extraction_warnings": record.get("extraction_warnings", []),
                "candidates": record.get("candidates", {}).get(item_name, []),
            }
            if value is None:
                # A new ambiguous observation must revoke the old pending
                # observation; otherwise reviewers can approve stale evidence.
                if existing and (evidence or source_record["candidates"]):
                    previous = existing.source_record or {}
                    source_record["previous_observation"] = (
                        previous.get("previous_observation") if existing.status == "invalidated"
                        else {"value": str(existing.value), "source_record": previous}
                    )
                    source_record["invalidated_reason"] = "最新采集未能唯一确认数值，原候选已失效"
                    existing.source_record = source_record
                    existing.status = "invalidated"
                    existing.confirmed_by_id = None
                    existing.confirmed_at = None
                    imported += 1
                continue
            try:
                amount = Decimal(str(value))
            except InvalidOperation:
                raise ValueError(f"{region} {year} {field_name}不是有效的正数") from None
            if isinstance(value, bool) or not amount.is_finite() or amount <= 0:
                raise ValueError(f"{region} {year} {field_name}不是有效的正数")
            if record.get("extraction_version"):
                if (evidence.get("validation_status") != "verified"
                        or evidence.get("region") != region
                        or evidence.get("statistical_year") != year
                        or evidence.get("unit") != "元"
                        or evidence.get("conflicts")):
                    raise ValueError(f"{region} {year} {field_name}尚未通过抽取维度校验")
            parsed_date = _parse_date(evidence.get("publish_date") or record.get("publish_date"))
            values: dict[str, Any] = {
                "region": region,
                "year": year,
                "field_name": field_name,
                "value": amount,
                "source_key": f"collector:{region}:{year}",
                "source_title": evidence.get("source_title") or record.get("bulletin_type"),
                "source_url": evidence.get("source_url") or record.get("source_url"),
                "publish_date": parsed_date,
                "status": "pending",
                "source_record": source_record,
            }
            if existing:
                for key, item in values.items():
                    setattr(existing, key, item)
            else:
                session.add(StatisticalStandardModel(**values))
            imported += 1
    session.commit()
    return imported


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
