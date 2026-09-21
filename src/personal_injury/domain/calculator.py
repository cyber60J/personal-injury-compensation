#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人身伤害赔偿金计算器

根据《中华人民共和国民法典》及相关司法解释计算人身伤害赔偿金额。
主要计算项目：
1. 医疗费
2. 误工费
3. 护理费
4. 交通费
5. 住院伙食补助费
6. 营养费
7. 残疾赔偿金（如有伤残）
8. 精神损害抚慰金
9. 被扶养人生活费（如有需要抚养的人）
"""

import math
from numbers import Real
from typing import Dict, Iterable, List, Mapping, Optional

from personal_injury.domain.guidance import apply_liability_ratio, review_compensation_claims

class CompensationCalculator:
    """赔偿金计算器类"""

    ALGORITHM_VERSION = "2026.1"

    DEFAULT_CONFIG = {
        '住院伙食补助费标准': 100,  # 元/天
        '营养费标准': 50,  # 元/天
        '交通费标准': 20,  # 元/天
        '护理费标准': 150,  # 元/天（普通护理）
        '上一年度城镇居民人均可支配收入': 50000,  # 元/年（示例数据）
        '上一年度城镇居民人均消费支出': 30000,  # 元/年（示例数据）
    }

    NURSING_LEVEL_MULTIPLIERS = {
        '普通': 1.0,
        '一级': 1.5,
        '特级': 2.0,
    }

    def __init__(
        self,
        config: Optional[Mapping[str, float]] = None,
        *,
        active_rule_source_keys: Optional[Iterable[str]] = None,
    ):
        """初始化计算器，并允许覆盖示例标准。"""
        self.active_rule_source_keys = (
            None if active_rule_source_keys is None else tuple(active_rule_source_keys)
        )
        self.config = self.DEFAULT_CONFIG.copy()
        if config:
            unknown_keys = set(config) - set(self.DEFAULT_CONFIG)
            if unknown_keys:
                raise ValueError(f"未知配置项：{', '.join(sorted(unknown_keys))}")
            self.config.update(config)

        for name, value in self.config.items():
            self.config[name] = self._positive_number(value, name)

        # 伤残等级赔偿系数（1-10级）
        self.disability_coefficients = {
            1: 1.0,   # 一级伤残
            2: 0.9,   # 二级伤残
            3: 0.8,   # 三级伤残
            4: 0.7,   # 四级伤残
            5: 0.6,   # 五级伤残
            6: 0.5,   # 六级伤残
            7: 0.4,   # 七级伤残
            8: 0.3,   # 八级伤残
            9: 0.2,   # 九级伤残
            10: 0.1,  # 十级伤残
        }

    @staticmethod
    def _non_negative_number(value: Real, field_name: str) -> float:
        """校验有限的非负数，避免负数、布尔值和无穷值进入金额计算。"""
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{field_name}必须是数字")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{field_name}必须是有限的非负数")
        return number

    @classmethod
    def _positive_number(cls, value: Real, field_name: str) -> float:
        number = cls._non_negative_number(value, field_name)
        if number == 0:
            raise ValueError(f"{field_name}必须大于0")
        return number

    @staticmethod
    def _age(value: int, field_name: str = "年龄") -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 150:
            raise ValueError(f"{field_name}必须是0-150之间的整数")
        return value

    def _disability_level(self, value: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value not in self.disability_coefficients
        ):
            raise ValueError(f"伤残等级应为1-10级，当前输入：{value}")
        return value

    def _dependent_support_years(self, age: int) -> int:
        """计算被扶养人生活费年限"""
        age = self._age(age, "被扶养人年龄")
        if age < 18:
            return 18 - age
        if age >= 75:
            return 5
        if age >= 60:
            return 20 - (age - 60)
        return 20

    def calculate_medical_expenses(self, medical_bills: List[float]) -> float:
        """计算医疗费"""
        if isinstance(medical_bills, (str, bytes)) or not isinstance(medical_bills, (list, tuple)):
            raise ValueError("医疗费票据必须是金额列表")
        return sum(
            self._non_negative_number(amount, f"第{index}笔医疗费")
            for index, amount in enumerate(medical_bills, start=1)
        )

    def calculate_loss_of_income(self, daily_salary: float, days: int) -> float:
        """计算误工费"""
        return (
            self._non_negative_number(daily_salary, "日收入")
            * self._non_negative_number(days, "误工天数")
        )

    def calculate_nursing_fee(self, nursing_days: int, nursing_level: str = '普通') -> float:
        """计算护理费"""
        if nursing_level not in self.NURSING_LEVEL_MULTIPLIERS:
            raise ValueError(
                f"护理等级必须是{', '.join(self.NURSING_LEVEL_MULTIPLIERS)}之一"
            )
        return (
            self.config['护理费标准']
            * self.NURSING_LEVEL_MULTIPLIERS[nursing_level]
            * self._non_negative_number(nursing_days, "护理天数")
        )

    def calculate_transportation_fee(self, transportation_days: int) -> float:
        """计算交通费"""
        return self.config['交通费标准'] * self._non_negative_number(
            transportation_days, "交通天数"
        )

    def calculate_hospital_meal_subsidy(self, hospitalization_days: int) -> float:
        """计算住院伙食补助费"""
        return self.config['住院伙食补助费标准'] * self._non_negative_number(
            hospitalization_days, "住院天数"
        )

    def calculate_nutrition_fee(self, nutrition_days: int) -> float:
        """计算营养费"""
        return self.config['营养费标准'] * self._non_negative_number(
            nutrition_days, "营养天数"
        )

    def calculate_disability_compensation(self,
                                         disability_level: int,
                                         age: int,
                                         urban_resident: bool = True) -> float:
        """按现行统一城镇居民标准计算残疾赔偿金。

        ``urban_resident`` 仅为兼容旧调用保留，不再影响计算结果。
        """
        disability_level = self._disability_level(disability_level)
        age = self._age(age)

        # 计算年限：60岁以下按20年，60岁以上每增加1岁减少1年，75岁以上按5年
        if age < 60:
            years = 20
        elif age <= 75:
            years = 20 - (age - 60)
        else:
            years = 5

        # 2022年5月1日起，残疾赔偿金不再区分城乡居民标准。
        _ = urban_resident
        annual_income = self.config['上一年度城镇居民人均可支配收入']

        coefficient = self.disability_coefficients[disability_level]
        return annual_income * years * coefficient

    def calculate_mental_distress(self, disability_level: Optional[int] = None) -> float:
        """生成精神损害抚慰金粗略估值，仅应在调用方明确要求时使用。"""
        if disability_level is not None:
            disability_level = self._disability_level(disability_level)
            # 根据伤残等级确定
            if disability_level <= 2:
                return 50000  # 一、二级伤残
            elif disability_level <= 4:
                return 30000  # 三、四级伤残
            elif disability_level <= 6:
                return 20000  # 五、六级伤残
            else:
                return 10000  # 七至十级伤残
        else:
            # 无伤残情况
            return 5000

    def calculate_dependent_support(self,
                                   dependents: List[Dict],
                                   disability_level: int,
                                   urban_resident: bool = True) -> float:
        """按统一城镇标准和多人年度上限计算被扶养人生活费。

        调用方应先确认成年被扶养人同时符合“无劳动能力且无其他生活来源”。
        ``urban_resident`` 仅为兼容旧调用保留。
        """
        if not dependents:
            return 0.0
        if isinstance(dependents, (str, bytes)) or not isinstance(dependents, (list, tuple)):
            raise ValueError("被扶养人必须是对象列表")

        _ = urban_resident
        annual_living = self.config['上一年度城镇居民人均消费支出']

        disability_level = self._disability_level(disability_level)
        coefficient = self.disability_coefficients[disability_level]
        dependent_items = []
        for index, dep in enumerate(dependents, start=1):
            if not isinstance(dep, Mapping):
                raise ValueError(f"第{index}名被扶养人必须是对象")
            if 'age' not in dep:
                raise ValueError(f"第{index}名被扶养人缺少年龄")
            age = self._age(dep['age'], f"第{index}名被扶养人年龄")
            years = self._dependent_support_years(age)
            supporters = dep.get('supporters', 1)
            if isinstance(supporters, bool) or not isinstance(supporters, int) or supporters < 1:
                raise ValueError(f"第{index}名被扶养义务人人数必须是正整数")
            dependent_items.append({
                'years': years,
                'annual_share': annual_living * coefficient / supporters
            })

        total = 0
        max_years = max(item['years'] for item in dependent_items)
        # 先按丧失劳动能力程度计算单个被扶养人，再将各项相加；
        # 多人年赔偿总额上限是完整的年度消费支出额，不再乘伤残系数。
        annual_cap = annual_living
        for year_index in range(max_years):
            annual_total = sum(
                item['annual_share']
                for item in dependent_items
                if year_index < item['years']
            )
            total += min(annual_total, annual_cap)

        return total

    def calculate_total(self, input_data: Dict) -> Dict:
        """计算总赔偿金额"""
        if not isinstance(input_data, Mapping):
            raise ValueError("计算输入必须是对象")
        results = {}

        # 医疗费
        if 'medical_bills' in input_data:
            results['医疗费'] = self.calculate_medical_expenses(input_data['medical_bills'])

        # 误工费
        income_fields = {'daily_salary', 'loss_of_work_days'}
        if income_fields & input_data.keys() and not income_fields <= input_data.keys():
            raise ValueError("误工费必须同时提供daily_salary和loss_of_work_days")
        if income_fields <= input_data.keys():
            results['误工费'] = self.calculate_loss_of_income(
                input_data['daily_salary'], input_data['loss_of_work_days']
            )

        # 护理费
        if 'nursing_days' in input_data:
            nursing_level = input_data.get('nursing_level', '普通')
            results['护理费'] = self.calculate_nursing_fee(
                input_data['nursing_days'], nursing_level
            )

        # 交通费
        if 'transportation_days' in input_data:
            results['交通费'] = self.calculate_transportation_fee(
                input_data['transportation_days']
            )

        # 住院伙食补助费
        if 'hospitalization_days' in input_data:
            results['住院伙食补助费'] = self.calculate_hospital_meal_subsidy(
                input_data['hospitalization_days']
            )

        # 营养费
        if 'nutrition_days' in input_data:
            results['营养费'] = self.calculate_nutrition_fee(
                input_data['nutrition_days']
            )

        # 残疾赔偿金
        if 'disability_level' in input_data:
            if 'age' not in input_data:
                raise ValueError("计算残疾赔偿金必须提供age")
            age = input_data['age']
            urban_resident = input_data.get('urban_resident', True)
            results['残疾赔偿金'] = self.calculate_disability_compensation(
                input_data['disability_level'], age, urban_resident
            )

        # 精神损害抚慰金具有个案裁量性：默认不自动计入。
        estimate_mental_distress = input_data.get('estimate_mental_distress', False)
        if not isinstance(estimate_mental_distress, bool):
            raise ValueError("estimate_mental_distress必须是布尔值")
        if 'mental_distress_amount' in input_data:
            results['精神损害抚慰金'] = self._non_negative_number(
                input_data['mental_distress_amount'], "精神损害抚慰金"
            )
        elif estimate_mental_distress:
            results['精神损害抚慰金'] = self.calculate_mental_distress(
                input_data.get('disability_level')
            )

        # 被扶养人生活费
        dependents = input_data.get('dependents')
        if dependents and 'disability_level' not in input_data:
            raise ValueError("计算被扶养人生活费必须提供disability_level")
        if dependents:
            urban_resident = input_data.get('urban_resident', True)
            results['被扶养人生活费'] = self.calculate_dependent_support(
                dependents, input_data['disability_level'], urban_resident
            )

        # 总计
        results['总计'] = sum(results.values())

        return results

    def calculate_with_review(self, input_data: Dict) -> Dict:
        """计算赔偿金额，并生成裁判审查提示"""
        raw_results = self.calculate_total(input_data)
        liability_ratio = input_data.get('liability_ratio')
        payable_results = apply_liability_ratio(raw_results, liability_ratio)
        return {
            '损失金额': raw_results,
            '责任比例后金额': payable_results,
            '裁判审查提示': review_compensation_claims(
                raw_results,
                input_data,
                active_rule_source_keys=self.active_rule_source_keys,
            )
        }

def main():
    """主函数：命令行交互界面"""
    print("=" * 60)
    print("人身伤害赔偿金计算器")
    print("=" * 60)

    calculator = CompensationCalculator()

    # 示例数据
    example_data = {
        'medical_bills': [5000, 3000, 2000],  # 医疗费账单
        'daily_salary': 300,  # 日工资
        'loss_of_work_days': 90,  # 误工天数
        'nursing_days': 30,  # 护理天数
        'nursing_level': '普通',  # 护理等级
        'transportation_days': 20,  # 交通天数
        'hospitalization_days': 15,  # 住院天数
        'nutrition_days': 60,  # 营养天数
        'disability_level': 8,  # 伤残等级（8级）
        'age': 35,  # 年龄
        'dependents': [
            {'age': 10, 'relationship': '子女', 'supporters': 2},
            {'age': 65, 'relationship': '父亲', 'supporters': 3}
        ],
        'liability_ratio': 0.8,
        'nursing_rate_basis': '居民服务业年平均工资',
        'evidence': {
            '医疗费': ['医疗费票据', '病历', '诊断证明'],
            '误工费': ['医疗机构休假证明或司法鉴定意见', '收入证明'],
            '护理费': ['护理期鉴定意见或医嘱'],
            '残疾赔偿金': ['伤残等级鉴定意见', '年龄证明', '统计数据来源'],
        }
    }

    print("\n使用示例数据计算...")
    report = calculator.calculate_with_review(example_data)
    results = report['损失金额']

    print("\n赔偿金明细：")
    print("-" * 40)
    for item, amount in results.items():
        if item != '总计':
            print(f"{item:15}：{amount:12.2f} 元")

    print("-" * 40)
    print(f"{'总计':15}：{results['总计']:12.2f} 元")
    print(f"{'责任比例后总计':15}：{report['责任比例后金额']['总计']:12.2f} 元")

    print("\n裁判审查提示（示例）：")
    for review in report['裁判审查提示']['claim_reviews']:
        if review['amount'] is not None and review['risk_flags']:
            print(f"- {review['item']}：{review['risk_level']}风险；{'；'.join(review['risk_flags'])}")

    print("\n说明：")
    print("1. 以上计算仅供参考，实际赔偿金额以法院判决为准")
    print("2. 示例统计标准必须替换为案件适用地区、适用年度的官方数据")
    print("3. 精神损害抚慰金默认不自动计入，责任比例结果也不含保险赔付顺序")

if __name__ == "__main__":
    main()
