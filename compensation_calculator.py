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

import sys
import json
import datetime
from typing import Dict, List, Optional

class CompensationCalculator:
    """赔偿金计算器类"""

    def __init__(self):
        """初始化计算器"""
        # 基础数据（可配置）
        self.config = {
            '住院伙食补助费标准': 100,  # 元/天
            '营养费标准': 50,  # 元/天
            '交通费标准': 20,  # 元/天
            '护理费标准': 150,  # 元/天（普通护理）
            '上一年度城镇居民人均可支配收入': 50000,  # 元/年（示例数据）
            '上一年度农村居民人均纯收入': 20000,  # 元/年（示例数据）
        }

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

    def calculate_medical_expenses(self, medical_bills: List[float]) -> float:
        """计算医疗费"""
        return sum(medical_bills)

    def calculate_loss_of_income(self, daily_salary: float, days: int) -> float:
        """计算误工费"""
        return daily_salary * days

    def calculate_nursing_fee(self, nursing_days: int, nursing_level: str = '普通') -> float:
        """计算护理费"""
        base_rate = self.config['护理费标准']
        if nursing_level == '特级':
            base_rate *= 2
        elif nursing_level == '一级':
            base_rate *= 1.5
        return base_rate * nursing_days

    def calculate_transportation_fee(self, transportation_days: int) -> float:
        """计算交通费"""
        return self.config['交通费标准'] * transportation_days

    def calculate_hospital_meal_subsidy(self, hospitalization_days: int) -> float:
        """计算住院伙食补助费"""
        return self.config['住院伙食补助费标准'] * hospitalization_days

    def calculate_nutrition_fee(self, nutrition_days: int) -> float:
        """计算营养费"""
        return self.config['营养费标准'] * nutrition_days

    def calculate_disability_compensation(self,
                                         disability_level: int,
                                         age: int,
                                         urban_resident: bool = True) -> float:
        """计算残疾赔偿金"""
        if disability_level not in self.disability_coefficients:
            raise ValueError(f"伤残等级应为1-10级，当前输入：{disability_level}")

        # 计算年限：60岁以下按20年，60岁以上每增加1岁减少1年，75岁以上按5年
        if age < 60:
            years = 20
        elif age <= 75:
            years = 20 - (age - 60)
        else:
            years = 5

        # 选择收入标准
        if urban_resident:
            annual_income = self.config['上一年度城镇居民人均可支配收入']
        else:
            annual_income = self.config['上一年度农村居民人均纯收入']

        coefficient = self.disability_coefficients[disability_level]
        return annual_income * years * coefficient

    def calculate_mental_distress(self, disability_level: Optional[int] = None) -> float:
        """计算精神损害抚慰金"""
        if disability_level:
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
        """计算被扶养人生活费"""
        total = 0
        for dep in dependents:
            age = dep.get('age', 0)
            relationship = dep.get('relationship', '子女')

            # 计算扶养年限
            if age < 18:
                years = 18 - age
            elif age >= 60:
                years = 20  # 最长20年
            else:
                years = 20  # 成年人按20年计算

            # 年生活费标准
            if urban_resident:
                annual_living = self.config['上一年度城镇居民人均消费支出'] if '上一年度城镇居民人均消费支出' in self.config else 30000
            else:
                annual_living = self.config['上一年度农村居民人均消费支出'] if '上一年度农村居民人均消费支出' in self.config else 15000

            # 多人扶养时分摊
            supporters = dep.get('supporters', 1)
            total += (annual_living * years / supporters) * self.disability_coefficients.get(disability_level, 1.0)

        return total

    def calculate_total(self, input_data: Dict) -> Dict:
        """计算总赔偿金额"""
        results = {}

        # 医疗费
        if 'medical_bills' in input_data:
            results['医疗费'] = self.calculate_medical_expenses(input_data['medical_bills'])

        # 误工费
        if 'daily_salary' in input_data and 'loss_of_work_days' in input_data:
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
            age = input_data.get('age', 30)
            urban_resident = input_data.get('urban_resident', True)
            results['残疾赔偿金'] = self.calculate_disability_compensation(
                input_data['disability_level'], age, urban_resident
            )

        # 精神损害抚慰金
        disability_level = input_data.get('disability_level')
        results['精神损害抚慰金'] = self.calculate_mental_distress(disability_level)

        # 被扶养人生活费
        if 'dependents' in input_data and 'disability_level' in input_data:
            urban_resident = input_data.get('urban_resident', True)
            results['被扶养人生活费'] = self.calculate_dependent_support(
                input_data['dependents'], input_data['disability_level'], urban_resident
            )

        # 总计
        results['总计'] = sum(results.values())

        return results

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
        'urban_resident': True,  # 城镇居民
        'dependents': [
            {'age': 10, 'relationship': '子女', 'supporters': 2},
            {'age': 65, 'relationship': '父亲', 'supporters': 3}
        ]
    }

    print("\n使用示例数据计算...")
    results = calculator.calculate_total(example_data)

    print("\n赔偿金明细：")
    print("-" * 40)
    for item, amount in results.items():
        if item != '总计':
            print(f"{item:15}：{amount:12.2f} 元")

    print("-" * 40)
    print(f"{'总计':15}：{results['总计']:12.2f} 元")

    print("\n说明：")
    print("1. 以上计算仅供参考，实际赔偿金额以法院判决为准")
    print("2. 请根据实际情况修改代码中的配置参数")
    print("3. 具体标准请参考最新法律法规")

if __name__ == "__main__":
    main()