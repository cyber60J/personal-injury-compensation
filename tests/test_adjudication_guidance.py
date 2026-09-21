import unittest

from adjudication_guidance import apply_liability_ratio, review_compensation_claims
from compensation_calculator import CompensationCalculator


class DependentSupportTests(unittest.TestCase):
    def test_lower_disability_coefficient_does_not_shrink_statutory_cap(self):
        calculator = CompensationCalculator()
        calculator.config["上一年度城镇居民人均消费支出"] = 30000

        amount = calculator.calculate_dependent_support(
            dependents=[
                {"age": 0, "relationship": "子女", "supporters": 1},
                {"age": 0, "relationship": "子女", "supporters": 1},
            ],
            disability_level=10,
            urban_resident=True,
        )

        self.assertEqual(amount, 108000)

    def test_dependent_support_applies_full_annual_consumption_cap(self):
        calculator = CompensationCalculator()
        calculator.config["上一年度城镇居民人均消费支出"] = 30000

        amount = calculator.calculate_dependent_support(
            dependents=[
                {"age": 0, "supporters": 1},
                {"age": 0, "supporters": 1},
            ],
            disability_level=1,
        )

        self.assertEqual(amount, 540000)


class AdjudicationGuidanceTests(unittest.TestCase):
    def test_review_flags_missing_evidence_and_nursing_basis(self):
        amounts = {
            "护理费": 7200,
            "误工费": 30000,
            "总计": 37200,
        }
        review = review_compensation_claims(
            amounts,
            {
                "nursing_rate_basis": "居民服务业年平均工资",
                "income_type": "industry_average",
                "evidence": {
                    "护理费": ["护理期鉴定意见或医嘱"],
                    "误工费": ["医疗机构休假证明或司法鉴定意见"],
                },
            },
        )

        nursing = next(item for item in review["claim_reviews"] if item["item"] == "护理费")
        loss_of_income = next(item for item in review["claim_reviews"] if item["item"] == "误工费")

        self.assertIn("护理人员收入证明或护工合同/发票", nursing["missing_evidence"])
        self.assertTrue(any("居民服务" in flag for flag in nursing["risk_flags"]))
        self.assertTrue(any("相近行业平均工资" in flag for flag in loss_of_income["risk_flags"]))

    def test_apply_liability_ratio_keeps_total_consistent(self):
        adjusted = apply_liability_ratio({"医疗费": 1000, "护理费": 500, "总计": 1500}, 0.8)

        self.assertEqual(adjusted["医疗费"], 800)
        self.assertEqual(adjusted["护理费"], 400)
        self.assertEqual(adjusted["总计"], 1200)

    def test_apply_liability_ratio_rejects_out_of_range_value(self):
        with self.assertRaises(ValueError):
            apply_liability_ratio({"医疗费": 1000, "总计": 1000}, 1.2)

    def test_review_includes_new_traffic_interpretation_flags(self):
        review = review_compensation_claims(
            {"误工费": 1000, "医疗费": 2000, "总计": 3000},
            {
                "retired_or_over_retirement_age": True,
                "basic_medical_insurance_paid": 500,
            },
        )

        self.assertTrue(any("退休年龄" in flag for flag in review["global_flags"]))
        self.assertTrue(any("重复主张" in flag for flag in review["global_flags"]))
        self.assertIn("traffic_interpretation_ii", review["source_references"])

    def test_old_rule_does_not_leak_future_traffic_interpretation(self):
        review = review_compensation_claims(
            {"误工费": 1000, "总计": 1000},
            {"retired_or_over_retirement_age": True},
            active_rule_source_keys=("personal_injury_interpretation",),
        )

        self.assertFalse(any("退休年龄" in flag for flag in review["global_flags"]))
        self.assertNotIn("traffic_interpretation_ii", review["source_references"])


class CalculatorReviewTests(unittest.TestCase):
    def test_calculate_with_review_returns_three_sections(self):
        calculator = CompensationCalculator()

        report = calculator.calculate_with_review({
            "medical_bills": [1000],
            "liability_ratio": 0.5,
            "evidence": {"医疗费": ["医疗费票据", "病历", "诊断证明"]},
        })

        self.assertIn("损失金额", report)
        self.assertIn("责任比例后金额", report)
        self.assertIn("裁判审查提示", report)
        self.assertEqual(report["责任比例后金额"]["总计"], report["损失金额"]["总计"] * 0.5)

    def test_empty_input_does_not_invent_mental_distress_amount(self):
        calculator = CompensationCalculator()

        results = calculator.calculate_total({})

        self.assertEqual(results, {"总计": 0})

    def test_mental_distress_is_only_included_when_explicit(self):
        calculator = CompensationCalculator()

        results = calculator.calculate_total({"mental_distress_amount": 12000})

        self.assertEqual(results["精神损害抚慰金"], 12000)
        self.assertEqual(results["总计"], 12000)

    def test_disability_compensation_uses_unified_urban_standard(self):
        calculator = CompensationCalculator({"上一年度城镇居民人均可支配收入": 60000})

        urban = calculator.calculate_disability_compensation(10, 40, urban_resident=True)
        rural = calculator.calculate_disability_compensation(10, 40, urban_resident=False)

        self.assertEqual(urban, 120000)
        self.assertEqual(rural, urban)

    def test_calculator_rejects_partial_or_negative_inputs(self):
        calculator = CompensationCalculator()

        with self.assertRaises(ValueError):
            calculator.calculate_total({"daily_salary": 300})
        with self.assertRaises(ValueError):
            calculator.calculate_total({"medical_bills": [-1]})
        with self.assertRaises(ValueError):
            calculator.calculate_total({"disability_level": 10})


if __name__ == "__main__":
    unittest.main()
