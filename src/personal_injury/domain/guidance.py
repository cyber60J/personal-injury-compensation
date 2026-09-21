#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人身损害赔偿裁判思路提示领域模块

本模块不替代法律意见，作用是把公开司法解释和典型案例中反复出现的
审查要点转化为可程序化的证据提示、风险提示和计算口径说明。
"""

from dataclasses import dataclass, asdict
import math
from numbers import Real
from typing import Any, Dict, Iterable, List, Optional


SOURCE_REFERENCES = {
    "personal_injury_interpretation": {
        "title": "最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释",
        "url": "https://gongbao.court.gov.cn/Details/3b032047d8cb44a89a514777ce6dad.html",
        "takeaway": "2022年5月1日起，残疾赔偿金、死亡赔偿金和被扶养人生活费统一使用城镇居民指标；上一年度是指一审法庭辩论终结时的上一统计年度。",
    },
    "traffic_interpretation_ii": {
        "title": "最高人民法院关于审理道路交通事故损害赔偿案件适用法律若干问题的解释（二）",
        "url": "https://www.court.gov.cn/fabu/xiangqing/499051.html",
        "takeaway": "自2026年6月30日起施行，明确超龄劳动者误工损失、多个被扶养人年度上限、基金已支付费用避免重复受偿等规则。",
    },
    "mental_distress_interpretation": {
        "title": "最高人民法院关于确定民事侵权精神损害赔偿责任若干问题的解释",
        "url": "https://gongbao.court.gov.cn/Details/87b471350704bf50ce1f5e0f9a0e21.html",
        "takeaway": "精神损害赔偿数额需结合侵权过错、行为情节、损害后果、责任能力和受诉法院所在地平均生活水平等因素确定。",
    },
    "traffic_typical_cases": {
        "title": "最高人民法院发布交通事故责任纠纷典型案例",
        "url": "https://www.court.gov.cn/zixun/xiangqing/480081.html",
        "takeaway": "交通事故案件会结合事故责任、过错程度、鉴定意见和保险责任确定最终赔偿责任。",
    },
    "nursing_fee_gazette_case": {
        "title": "最高人民法院公报案例：尹瑞军诉颜礼奎健康权、身体权纠纷案",
        "url": "https://gongbao.court.gov.cn/Details/3e680f3a7ae2bde2aacfc0a168841a.html",
        "takeaway": "在护理人员收入状况无法证明时，公报案例曾参照当地居民服务业和其他服务业平均工资计算护理费；该口径仍需结合当地标准与个案证据。",
    },
}


@dataclass
class ClaimRule:
    item: str
    court_focus: str
    required_evidence: List[str]
    calculation_basis: str
    case_reasoning: str
    source_keys: List[str]


@dataclass
class ClaimReview:
    item: str
    amount: Optional[float]
    court_focus: str
    calculation_basis: str
    required_evidence: List[str]
    provided_evidence: List[str]
    missing_evidence: List[str]
    risk_level: str
    risk_flags: List[str]
    case_reasoning: str
    source_references: List[Dict[str, str]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CLAIM_RULES: Dict[str, ClaimRule] = {
    "医疗费": ClaimRule(
        item="医疗费",
        court_focus="医疗费通常审查票据、病历、诊断证明之间能否相互印证，以及治疗项目是否必要、合理。",
        required_evidence=["医疗费票据", "病历", "诊断证明"],
        calculation_basis="按一审法庭辩论终结前实际发生的医疗费用确定；必要且确定发生的后续治疗费可一并主张。",
        case_reasoning="司法解释明确医疗费以医疗机构收款凭证结合病历、诊断证明等证据确定；对必要性、合理性有异议的一方负相应举证责任。",
        source_keys=["personal_injury_interpretation"],
    ),
    "误工费": ClaimRule(
        item="误工费",
        court_focus="误工费通常审查误工时间和收入减少是否有证据支持；固定收入、最近三年平均收入、相近行业工资是递进口径。",
        required_evidence=["医疗机构休假证明或司法鉴定意见", "收入证明", "实际收入减少证明"],
        calculation_basis="有固定收入按实际减少收入；无固定收入按最近三年平均收入；不能证明的参照相同或相近行业上一年度职工平均工资。",
        case_reasoning="误工费以实际收入减少为核心；年龄本身不能替代收入和损失证据。",
        source_keys=["personal_injury_interpretation", "traffic_interpretation_ii", "traffic_typical_cases"],
    ),
    "护理费": ClaimRule(
        item="护理费",
        court_focus="护理费通常审查护理人数、护理期限、护理级别和护理人员收入；无收入或雇佣护工时要说明当地护工劳务报酬标准。",
        required_evidence=["护理期鉴定意见或医嘱", "护理人员收入证明或护工合同/发票", "护理依赖程度材料"],
        calculation_basis="护理人员有收入的参照误工费；无收入或雇佣护工的参照当地同等级护理劳务报酬标准；残后护理期限最长通常不超过二十年。",
        case_reasoning="公报案例曾在护理人员收入无法证明时参照居民服务业平均工资，但该行业工资不是全国统一或当然适用的护理费标准。",
        source_keys=["personal_injury_interpretation", "nursing_fee_gazette_case"],
    ),
    "交通费": ClaimRule(
        item="交通费",
        court_focus="交通费通常审查就医、转院、陪护的地点、时间、人数、次数与票据是否对应。",
        required_evidence=["交通费正式票据", "就医或转院记录", "陪护必要性材料"],
        calculation_basis="按受害人及必要陪护人员因就医或转院实际发生的费用计算。",
        case_reasoning="公开公报案例中，法院会结合就医过程的必然性和票据匹配程度，对交通、住宿等费用进行必要合理性审查。",
        source_keys=["personal_injury_interpretation"],
    ),
    "住院伙食补助费": ClaimRule(
        item="住院伙食补助费",
        court_focus="住院伙食补助费通常审查住院天数和当地国家机关一般工作人员出差伙食补助标准。",
        required_evidence=["住院病案首页或出入院记录", "当地出差伙食补助标准"],
        calculation_basis="可参照当地国家机关一般工作人员出差伙食补助标准。",
        case_reasoning="该项目裁判争点通常不是是否赔，而是住院天数和地区标准是否正确。",
        source_keys=["personal_injury_interpretation"],
    ),
    "营养费": ClaimRule(
        item="营养费",
        court_focus="营养费通常审查伤残情况、医嘱或司法鉴定意见，不能只凭主观估算。",
        required_evidence=["营养期鉴定意见或医嘱", "伤情或伤残材料"],
        calculation_basis="根据伤残情况参照医疗机构意见确定。",
        case_reasoning="交通事故典型案例中，营养期常由司法鉴定意见确定，法院再据此计算。",
        source_keys=["personal_injury_interpretation", "traffic_typical_cases"],
    ),
    "残疾赔偿金": ClaimRule(
        item="残疾赔偿金",
        court_focus="残疾赔偿金通常审查伤残等级、年龄、定残日、适用地区及上一统计年度城镇居民人均可支配收入。",
        required_evidence=["伤残等级鉴定意见", "年龄证明", "定残日材料", "统计数据来源"],
        calculation_basis="按受诉法院所在地上一年度城镇居民人均可支配收入，自定残日起按年限计算；60岁以上递减，75岁以上按5年。",
        case_reasoning="司法解释同时提示，实际收入未减少或职业妨害明显时，法院可能结合个案情况调整。",
        source_keys=["personal_injury_interpretation"],
    ),
    "被扶养人生活费": ClaimRule(
        item="被扶养人生活费",
        court_focus="被扶养人生活费通常审查法定扶养义务、被扶养人年龄/劳动能力/生活来源、其他扶养人数量，以及多人年度上限。",
        required_evidence=["亲属关系证明", "被扶养人年龄证明", "无劳动能力或无生活来源证明", "其他扶养人情况"],
        calculation_basis="按上一年度城镇居民人均消费支出和扶养年限计算；有其他扶养人的只赔受害人应负担部分；多人年赔偿总额不超过年度消费支出标准。",
        case_reasoning="存在多个被扶养人时，应逐人核对扶养年限、扶养义务人数量和年度总额上限。",
        source_keys=["personal_injury_interpretation", "traffic_interpretation_ii"],
    ),
    "精神损害抚慰金": ClaimRule(
        item="精神损害抚慰金",
        court_focus="精神损害抚慰金通常审查侵权过错、损害后果、伤残等级、地区裁判尺度和责任比例。",
        required_evidence=["伤残或严重损害后果材料", "侵权过错材料"],
        calculation_basis="适用精神损害赔偿司法解释并结合地区裁判尺度酌定。",
        case_reasoning="交通事故典型案例中精神损害项目常与伤残后果、责任比例一并评价。",
        source_keys=["personal_injury_interpretation", "mental_distress_interpretation", "traffic_typical_cases"],
    ),
}


EVIDENCE_ALIASES = {
    "medical_receipts": "医疗费票据",
    "medical_records": "病历",
    "diagnosis_certificate": "诊断证明",
    "appraisal_opinion": "司法鉴定意见",
    "doctor_rest_note": "医疗机构休假证明或司法鉴定意见",
    "income_certificate": "收入证明",
    "income_reduction": "实际收入减少证明",
    "nursing_appraisal": "护理期鉴定意见或医嘱",
    "nursing_invoice": "护理人员收入证明或护工合同/发票",
    "nursing_dependency": "护理依赖程度材料",
    "transport_tickets": "交通费正式票据",
    "hospitalization_record": "住院病案首页或出入院记录",
    "nutrition_appraisal": "营养期鉴定意见或医嘱",
    "disability_appraisal": "伤残等级鉴定意见",
    "statistics_source": "统计数据来源",
    "dependent_relationship": "亲属关系证明",
    "dependent_no_income": "无劳动能力或无生活来源证明",
    "fault_evidence": "侵权过错材料",
}


def normalize_evidence(evidence: Any) -> List[str]:
    """把输入证据统一为中文证据名列表"""
    if evidence is None:
        return []

    if isinstance(evidence, dict):
        names = []
        for key, value in evidence.items():
            if value:
                names.append(EVIDENCE_ALIASES.get(key, key))
        return names

    if isinstance(evidence, str):
        return [EVIDENCE_ALIASES.get(evidence, evidence)]

    names = []
    for item in evidence:
        names.append(EVIDENCE_ALIASES.get(item, item))
    return names


def _source_refs(
    source_keys: List[str],
    active_rule_source_keys: set[str],
) -> List[Dict[str, str]]:
    references = []
    for key in source_keys:
        if key == "traffic_interpretation_ii" and key not in active_rule_source_keys:
            continue
        if key in SOURCE_REFERENCES:
            references.append(SOURCE_REFERENCES[key])
    return references


def _risk_level(missing: List[str], amount: Optional[float]) -> str:
    if amount is None or amount <= 0:
        return "提示"
    if len(missing) >= 2:
        return "高"
    if missing:
        return "中"
    return "低"


def review_compensation_claims(
    amounts: Dict[str, float],
    input_data: Dict[str, Any],
    *,
    active_rule_source_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """根据计算结果和输入材料生成裁判审查提示"""
    active_sources = (
        set(SOURCE_REFERENCES)
        if active_rule_source_keys is None
        else set(active_rule_source_keys)
    )
    evidence_map = input_data.get("evidence", {})
    claim_reviews: List[ClaimReview] = []

    for item, rule in CLAIM_RULES.items():
        amount = amounts.get(item)
        item_evidence = normalize_evidence(evidence_map.get(item) or evidence_map.get(rule.item))
        missing = [name for name in rule.required_evidence if name not in item_evidence]
        risk_flags = []

        if amount is not None and amount > 0 and missing:
            risk_flags.append("证据不足，法院可能调低或不支持该项目")

        if item == "护理费" and input_data.get("nursing_rate_basis") == "居民服务业年平均工资":
            risk_flags.append("居民服务、修理和其他服务业工资只是护理费参考口径，应说明当地护工劳务报酬或类案依据")

        if item == "误工费" and input_data.get("income_type") == "industry_average":
            risk_flags.append("使用相近行业平均工资时，应说明无法证明固定收入或最近三年平均收入")

        if item == "被扶养人生活费" and len(input_data.get("dependents") or []) > 1:
            risk_flags.append("多个被扶养人应先逐人计算再相加，并适用年度总额上限")

        claim_reviews.append(
            ClaimReview(
                item=item,
                amount=amount,
                court_focus=rule.court_focus,
                calculation_basis=rule.calculation_basis,
                required_evidence=rule.required_evidence,
                provided_evidence=item_evidence,
                missing_evidence=missing,
                risk_level=_risk_level(missing, amount),
                risk_flags=risk_flags,
                case_reasoning=rule.case_reasoning,
                source_references=_source_refs(rule.source_keys, active_sources),
            )
        )

    global_flags = []
    liability_ratio = input_data.get("liability_ratio")
    if liability_ratio is not None and liability_ratio != 1:
        global_flags.append(f"已输入责任比例 {liability_ratio:g}，最终给付金额通常还需结合责任比例、保险责任或过错减轻规则调整。")

    if input_data.get("good_samaritan_ride"):
        global_flags.append("好意同乘场景下，法院会综合事故原因、重大过失和受害人自身过错判断是否减轻责任。")

    if input_data.get("continuing_care_claim"):
        global_flags.append("继续护理、辅助器具或残疾赔偿请求需说明损害持续或新发生，并避免重复赔偿。")

    if (
        input_data.get("retired_or_over_retirement_age")
        and "traffic_interpretation_ii" in active_sources
    ):
        global_flags.append("超过法定退休年龄不当然排除误工费，但必须证明交通事故造成了实际误工损失。")

    fund_paid_fields = (
        "fund_paid_medical_expenses",
        "basic_medical_insurance_paid",
        "work_injury_insurance_paid",
        "road_relief_fund_paid",
    )
    if (
        any(input_data.get(field) for field in fund_paid_fields)
        and "traffic_interpretation_ii" in active_sources
    ):
        global_flags.append("已由基本医保、工伤保险基金或道路交通事故救助基金支付/垫付的相应费用，不应在道路交通事故案件中重复主张。")

    if input_data.get("urban_resident") is False:
        global_flags.append("现行残疾赔偿金和被扶养人生活费已统一使用城镇居民指标；urban_resident=False不会降低计算标准。")

    if "mental_distress_amount" in input_data or input_data.get("estimate_mental_distress"):
        global_flags.append("精神损害抚慰金没有全国统一的伤残等级固定金额，应结合个案因素和受诉法院所在地裁判尺度复核。")

    used_source_keys = {
        key
        for rule in CLAIM_RULES.values()
        for key in rule.source_keys
        if key != "traffic_interpretation_ii" or key in active_sources
    }
    return {
        "claim_reviews": [review.to_dict() for review in claim_reviews],
        "global_flags": global_flags,
        "source_references": {
            key: SOURCE_REFERENCES[key]
            for key in used_source_keys
            if key in SOURCE_REFERENCES
        },
    }


def apply_liability_ratio(amounts: Dict[str, float], liability_ratio: Optional[float]) -> Dict[str, float]:
    """按责任比例生成给付金额，不改动原始损失金额"""
    if liability_ratio is None:
        return amounts.copy()

    if (
        isinstance(liability_ratio, bool)
        or not isinstance(liability_ratio, Real)
        or not math.isfinite(float(liability_ratio))
        or not 0 <= float(liability_ratio) <= 1
    ):
        raise ValueError("liability_ratio必须是0-1之间的有限数字")
    liability_ratio = float(liability_ratio)

    adjusted = {}
    for item, amount in amounts.items():
        if item == "总计":
            continue
        adjusted[item] = amount * liability_ratio
    adjusted["总计"] = sum(adjusted.values())
    return adjusted
